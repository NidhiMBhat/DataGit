import re
import math
from typing import Any
from datetime import datetime, timezone

from dagit.db.connection import get_db_cursor
from dagit.reports.report_service import get_commit_diff, get_reachable_commit_ids
from dagit.reports.merge_events import fetch_merge_history
from dagit.versioning.metadata import init_metadata_tables


def _normalize_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class CommitEvidenceDocument:
    def __init__(
        self,
        commit_id: int,
        timestamp: datetime,
        author: str,
        message: str,
        parents: list[int],
        tables: set[str],
        row_counts_by_table: dict[str, dict[str, int]],
        schema_ops: list[dict[str, str]],
        merge_info: dict[str, Any] | None = None,
    ):
        self.commit_id = commit_id
        self.timestamp = _normalize_dt(timestamp)
        self.author = author
        self.message = message
        self.parents = parents
        self.first_parent_id = parents[0] if parents else None
        self.is_merge = len(parents) > 1
        self.tables = tables
        self.row_counts_by_table = row_counts_by_table
        self.schema_ops = schema_ops
        self.merge_info = merge_info

        # Searchable text tokens (EXCLUDING all raw row values and credentials)
        table_tokens = " ".join(tables)
        op_tokens = " ".join(
            f"{op.get('operation', '')} {op.get('table', '')} {op.get('details', '')}"
            for op in schema_ops
        )
        row_summary_tokens = " ".join(
            f"{tbl} inserts {counts['inserts']} updates {counts['updates']} deletes {counts['deletes']}"
            for tbl, counts in row_counts_by_table.items()
        )
        self.searchable_text = f"commit {commit_id} author {author} {message} {table_tokens} {op_tokens} {row_summary_tokens}".lower()
        self.tokens = self._tokenize(self.searchable_text)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [t for t in re.findall(r"[a-z0-9_#]+", text) if len(t) > 1]

    def to_dict(self) -> dict[str, Any]:
        """Convert to safe JSON-serializable evidence reference for clients and model context."""
        total_inserts = sum(c["inserts"] for c in self.row_counts_by_table.values())
        total_updates = sum(c["updates"] for c in self.row_counts_by_table.values())
        total_deletes = sum(c["deletes"] for c in self.row_counts_by_table.values())

        diff_from = self.first_parent_id if self.first_parent_id is not None else 0
        diff_link = f"/diff/{diff_from}/{self.commit_id}" if diff_from else f"/diff/{self.commit_id}/{self.commit_id}"

        return {
            "commit_id": self.commit_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "author": self.author,
            "message": self.message,
            "is_merge": self.is_merge,
            "parent_commits": self.parents,
            "impacted_tables": sorted(list(self.tables)),
            "row_changes_summary": {
                "inserts": total_inserts,
                "updates": total_updates,
                "deletes": total_deletes,
                "by_table": self.row_counts_by_table,
            },
            "schema_changes": self.schema_ops,
            "diff_link": diff_link,
            "merge_info": self.merge_info,
        }


class EvidenceIndexer:
    """Local semantic and exact-match index for DataGit repository history."""

    def __init__(self):
        self._documents: dict[int, CommitEvidenceDocument] = {}
        self._last_max_commit_id: int = 0
        self._doc_count: int = 0
        self._last_state_hash: str = ""
        self._term_frequencies: dict[str, dict[int, int]] = {}
        self._doc_frequencies: dict[str, int] = {}

    def refresh_if_needed(self) -> None:
        """Check for newly created commits and rebuild or update index when necessary."""
        init_metadata_tables()
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT COALESCE(MAX(commit_id), 0) AS max_id,
                       COUNT(*) AS cnt,
                       COALESCE(MD5(STRING_AGG(state_id, ',' ORDER BY commit_id)), '') AS state_hash
                FROM datagit_commits;
            """)
            row = cursor.fetchone()
            curr_max = row["max_id"] if row else 0
            curr_cnt = row["cnt"] if row else 0
            curr_hash = row["state_hash"] if row else ""

        if curr_max != self._last_max_commit_id or curr_cnt != self._doc_count or curr_hash != self._last_state_hash:
            self._last_state_hash = curr_hash
            self._rebuild_index()

    def _rebuild_index(self) -> None:
        """Build evidence from commit metadata, row-change counts, and schema diffs."""
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT c.commit_id, c.parent_commit, c.state_id, c.message, c.author, c.timestamp,
                       ARRAY(
                           SELECT p.parent_commit_id
                           FROM datagit_commit_parents p
                           WHERE p.commit_id = c.commit_id
                           ORDER BY p.parent_order
                       ) AS parents
                FROM datagit_commits c
                ORDER BY c.commit_id ASC;
            """)
            commits = [dict(row) for row in cursor.fetchall()]

        merge_events = fetch_merge_history()
        merge_map = {ev.get("merge_commit_id"): ev for ev in merge_events if ev.get("merge_commit_id")}

        docs: dict[int, CommitEvidenceDocument] = {}
        tf: dict[str, dict[int, int]] = {}
        df: dict[str, int] = {}

        for c in commits:
            cid = c["commit_id"]
            parents = c["parents"] or []
            diff_res = get_commit_diff(c)
            row_changes = diff_res.get("row_changes", [])
            schema_changes = diff_res.get("schema_changes", [])

            tables: set[str] = set()
            row_counts: dict[str, dict[str, int]] = {}

            # Count row operations per table (WITHOUT raw column values)
            for r in row_changes:
                tbl = r.get("table", "unknown")
                tables.add(tbl)
                if tbl not in row_counts:
                    row_counts[tbl] = {"inserts": 0, "updates": 0, "deletes": 0}
                op = r.get("operation")
                if op == "INSERT":
                    row_counts[tbl]["inserts"] += 1
                elif op == "UPDATE":
                    row_counts[tbl]["updates"] += 1
                elif op == "DELETE":
                    row_counts[tbl]["deletes"] += 1

            # Sanitize schema changes: only operation, table name, column/constraint names
            sanitized_schema_ops = []
            for s in schema_changes:
                tbl = s.get("table", "unknown")
                tables.add(tbl)
                sanitized_schema_ops.append({
                    "table": tbl,
                    "operation": s.get("operation", ""),
                    "details": f"{s.get('column') or ''} {s.get('kind') or ''}".strip(),
                })

            merge_info = merge_map.get(cid)

            doc = CommitEvidenceDocument(
                commit_id=cid,
                timestamp=c["timestamp"],
                author=c["author"],
                message=c["message"],
                parents=parents,
                tables=tables,
                row_counts_by_table=row_counts,
                schema_ops=sanitized_schema_ops,
                merge_info=merge_info,
            )
            docs[cid] = doc

            # Index terms
            term_counts: dict[str, int] = {}
            for token in doc.tokens:
                term_counts[token] = term_counts.get(token, 0) + 1
            for term, count in term_counts.items():
                if term not in tf:
                    tf[term] = {}
                tf[term][cid] = count
                df[term] = df.get(term, 0) + 1

        self._documents = docs
        self._term_frequencies = tf
        self._doc_frequencies = df
        self._doc_count = len(docs)
        self._last_max_commit_id = max(docs.keys()) if docs else 0

    def search(
        self,
        query: str,
        branch: str | None = None,
        table: str | None = None,
        start_dt: datetime | None = None,
        end_dt: datetime | None = None,
        commit_ids: list[int] | None = None,
        limit: int = 5,
    ) -> list[CommitEvidenceDocument]:
        """
        Retrieve evidence combining exact matches (branch, table, commit ID)
        and BM25/TF-IDF lexical relevance.
        """
        self.refresh_if_needed()
        if not self._documents:
            return []

        # Scope filter by reachable commits on branch
        allowed_cids: set[int] | None = None
        if branch and branch.strip():
            allowed_cids = get_reachable_commit_ids(branch.strip())

        candidates = list(self._documents.values())

        # Filter by branch scope
        if allowed_cids is not None:
            candidates = [d for d in candidates if d.commit_id in allowed_cids]

        # Filter by date boundaries
        if start_dt is not None:
            norm_start = _normalize_dt(start_dt)
            candidates = [d for d in candidates if d.timestamp is not None and d.timestamp >= norm_start]
        if end_dt is not None:
            norm_end = _normalize_dt(end_dt)
            candidates = [d for d in candidates if d.timestamp is not None and d.timestamp <= norm_end]

        # Filter by table if specified
        if table and table.strip():
            tbl_norm = table.strip().lower()
            candidates = [d for d in candidates if tbl_norm in {t.lower() for t in d.tables}]

        if not candidates:
            return []

        # Exact match boost for requested commit IDs
        exact_cids = set(commit_ids or [])
        query_tokens = CommitEvidenceDocument._tokenize(query.lower())

        scores: list[tuple[float, CommitEvidenceDocument]] = []
        n_docs = max(1, self._doc_count)

        for doc in candidates:
            score = 0.0
            # Strong exact match bonus for commit ID
            if doc.commit_id in exact_cids:
                score += 100.0

            # Exact table mention bonus
            for tbl in doc.tables:
                if tbl.lower() in query.lower():
                    score += 25.0

            # Lexical BM25-like scoring
            doc_len = len(doc.tokens) or 1
            for term in query_tokens:
                if term in self._term_frequencies and doc.commit_id in self._term_frequencies[term]:
                    term_freq = self._term_frequencies[term][doc.commit_id]
                    doc_freq = self._doc_frequencies.get(term, 1)
                    idf = math.log(1.0 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
                    tf = (term_freq * 2.2) / (term_freq + 1.2 * (0.25 + 0.75 * (doc_len / 30.0)))
                    score += max(0.0, idf * tf)

            scores.append((score, doc))

        # Sort descending by score, then newest timestamp
        scores.sort(key=lambda item: (item[0], item[1].commit_id), reverse=True)
        return [doc for score, doc in scores[:limit]]


# Singleton indexer instance
GLOBAL_INDEXER = EvidenceIndexer()

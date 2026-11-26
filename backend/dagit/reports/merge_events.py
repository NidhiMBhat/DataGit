import json
from datetime import datetime, timezone
from typing import Any

from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables


def get_tracking_metadata() -> dict[str, str]:
    """Retrieve metadata about system tracking timestamps and capabilities."""
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT key, value FROM datagit_tracking_meta;")
        rows = cursor.fetchall()
        return {row["key"]: row["value"] for row in rows}


def get_tracking_start_date() -> str:
    """Return the date/time from which outcome tracking is complete."""
    meta = get_tracking_metadata()
    return meta.get("merge_outcome_tracking_started_at", "2026-11-26T00:00:00Z")


def record_merge_event(
    actor: str,
    source_commit_id: int | None,
    target_commit_id: int | None,
    outcome: str,
    source_branch: str | None = None,
    target_branch: str | None = None,
    conflict_details: list[dict[str, Any]] | None = None,
    error_message: str | None = None,
    merge_commit_id: int | None = None,
    workspace_id: str = "default",
    is_preview: bool = False,
) -> int | None:
    """
    Persist an actual merge attempt.
    Excludes previews.
    Distinguishes conflicts ('conflict') from other rejections ('rejected').
    """
    if is_preview:
        return None

    init_metadata_tables()
    try:
        conflict_json = (
            json.dumps(conflict_details, default=str)
            if conflict_details is not None
            else None
        )
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO datagit_merge_events (
                    workspace_id, actor, source_branch, source_commit_id,
                    target_branch, target_commit_id, outcome, conflict_details,
                    error_message, merge_commit_id, is_preview
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                workspace_id,
                actor,
                source_branch,
                source_commit_id,
                target_branch,
                target_commit_id,
                outcome,
                conflict_json,
                error_message,
                merge_commit_id,
                False,
            ))
            row = cursor.fetchone()
            return row["id"] if row else None
    except Exception:
        # Logging merge event must not fail the surrounding workflow
        return None


def fetch_merge_history(
    workspace_id: str = "default",
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
    branch: str | None = None,
    reachable_commit_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch merge events in range.
    Includes persisted merge events and combines historical successful merge commits
    from commit history that predate the tracking start timestamp.
    """
    init_metadata_tables()
    tracking_started_at = get_tracking_start_date()

    query = """
        SELECT id, workspace_id, actor, source_branch, source_commit_id,
               target_branch, target_commit_id, outcome, conflict_details,
               error_message, merge_commit_id, is_preview, attempted_at
        FROM datagit_merge_events
        WHERE is_preview = FALSE AND workspace_id = %s
    """
    params: list[Any] = [workspace_id]

    if start_dt is not None:
        query += " AND attempted_at >= %s"
        params.append(start_dt)
    if end_dt is not None:
        query += " AND attempted_at <= %s"
        params.append(end_dt)

    query += " ORDER BY attempted_at ASC, id ASC;"

    events: list[dict[str, Any]] = []
    recorded_commit_ids = set()

    with get_db_cursor() as cursor:
        cursor.execute(query, tuple(params))
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("merge_commit_id"):
                recorded_commit_ids.add(item["merge_commit_id"])
            if isinstance(item.get("conflict_details"), str):
                try:
                    item["conflict_details"] = json.loads(item["conflict_details"])
                except Exception:
                    pass
            events.append(item)

        # Reconstruct historical successful merges from datagit_commits that are not in recorded_commit_ids
        # Multi-parent commits have at least 2 entries in datagit_commit_parents
        historical_query = """
            SELECT c.commit_id, c.message, c.author, c.timestamp,
                   ARRAY(
                       SELECT p.parent_commit_id
                       FROM datagit_commit_parents p
                       WHERE p.commit_id = c.commit_id
                       ORDER BY p.parent_order
                   ) AS parents
            FROM datagit_commits c
            WHERE (
                SELECT COUNT(*) FROM datagit_commit_parents p WHERE p.commit_id = c.commit_id
            ) >= 2
        """
        h_params: list[Any] = []
        if start_dt is not None:
            historical_query += " AND c.timestamp >= %s"
            h_params.append(start_dt)
        if end_dt is not None:
            historical_query += " AND c.timestamp <= %s"
            h_params.append(end_dt)

        historical_query += " ORDER BY c.timestamp ASC, c.commit_id ASC;"
        cursor.execute(historical_query, tuple(h_params))
        for row in cursor.fetchall():
            cid = row["commit_id"]
            if cid not in recorded_commit_ids:
                parents = row["parents"] or []
                p1 = parents[0] if len(parents) > 0 else None
                p2 = parents[1] if len(parents) > 1 else None
                events.append({
                    "id": f"hist_{cid}",
                    "workspace_id": workspace_id,
                    "actor": row["author"],
                    "source_branch": None,
                    "source_commit_id": p2,
                    "target_branch": None,
                    "target_commit_id": p1,
                    "outcome": "success",
                    "conflict_details": None,
                    "error_message": None,
                    "merge_commit_id": cid,
                    "is_preview": False,
                    "attempted_at": row["timestamp"],
                    "is_historical_reconstruction": True,
                })

    # Filter by reachable commits if branch filter is supplied
    if reachable_commit_ids is not None:
        filtered = []
        for ev in events:
            # Matches if merge commit is reachable or source/target commit is reachable or branch matches
            ev_cid = ev.get("merge_commit_id")
            s_cid = ev.get("source_commit_id")
            t_cid = ev.get("target_commit_id")
            if (
                (ev_cid and ev_cid in reachable_commit_ids)
                or (s_cid and s_cid in reachable_commit_ids)
                or (t_cid and t_cid in reachable_commit_ids)
                or (branch and (ev.get("target_branch") == branch or ev.get("source_branch") == branch))
            ):
                filtered.append(ev)
        events = filtered

    # Sort final events chronologically
    events.sort(key=lambda x: str(x.get("attempted_at") or ""))
    return events

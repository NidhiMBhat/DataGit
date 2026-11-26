import re
from typing import Any
from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables


def get_known_schema_elements() -> tuple[list[str], list[str]]:
    """Retrieve known branch names and user table names for entity extraction."""
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("SELECT name FROM datagit_branches ORDER BY name;")
        branches = [row["name"] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name NOT LIKE 'datagit_%'
            ORDER BY table_name;
        """)
        tables = [row["table_name"] for row in cursor.fetchall()]

    return branches, tables


class ParsedQuestion:
    def __init__(
        self,
        raw_question: str,
        question_type: str,
        branch: str | None,
        table: str | None,
        date_range: str,
        start_date: str | None,
        end_date: str | None,
        metric: str,
        commit_ids: list[int],
        clarification_needed: str | None = None,
    ):
        self.raw_question = raw_question
        self.question_type = question_type
        self.branch = branch
        self.table = table
        self.date_range = date_range
        self.start_date = start_date
        self.end_date = end_date
        self.metric = metric
        self.commit_ids = commit_ids
        self.clarification_needed = clarification_needed

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_type": self.question_type,
            "branch": self.branch,
            "table": self.table,
            "date_range": self.date_range,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "metric": self.metric,
            "commit_ids": self.commit_ids,
            "clarification_needed": self.clarification_needed,
        }


def parse_question(question: str, context_filters: dict[str, Any] | None = None) -> ParsedQuestion:
    """
    Classify question into exact_statistics, evidence_discovery, or explanation,
    and extract branch, table, date range, and metric filters.
    """
    q_lower = question.lower().strip()
    context = context_filters or {}
    known_branches, known_tables = get_known_schema_elements()

    # 1. Question Type Classification
    # Explanation patterns: "spike in", "contributed most", "why did", "explain", "cause of", "driver of"
    if re.search(r"\b(contributed most|spike|why did|explain|cause|driver|reasons? for)\b", q_lower):
        question_type = "explanation"
    # Exact statistics patterns: "how many", "total count", "number of", "count of", "sum of", "total"
    elif re.search(r"\b(how many|count of|number of|total|how much)\b", q_lower):
        question_type = "exact_statistics"
    # Evidence discovery patterns: "which commits", "what commits", "who changed", "find commits", "show commits", "list commits"
    elif re.search(r"\b(which commits?|what commits?|who changed|find commits?|show commits?|list commits?|which changes?)\b", q_lower):
        question_type = "evidence_discovery"
    else:
        # Default heuristic based on question terms
        if "?" in q_lower and any(w in q_lower for w in ["which", "who", "where", "what"]):
            question_type = "evidence_discovery"
        else:
            question_type = "exact_statistics"

    # 2. Extract Commit IDs (e.g. #3, commit 3)
    commit_ids = []
    for match in re.finditer(r"(?:commit|#)\s*(\d+)", q_lower):
        commit_ids.append(int(match.group(1)))

    # 3. Extract Branch
    matched_branches = []
    for b in known_branches:
        # check whole word or exact substring
        pattern = r"\b" + re.escape(b.lower()) + r"\b"
        if re.search(pattern, q_lower):
            matched_branches.append(b)

    branch = None
    clarification_needed = None
    if len(matched_branches) == 1:
        branch = matched_branches[0]
    elif len(matched_branches) > 1:
        # Ambiguous multiple branches mentioned
        clarification_needed = f"Multiple branches ({', '.join(matched_branches)}) were detected. Please specify which branch ancestry to analyze."
        branch = matched_branches[0]
    elif context.get("branch"):
        branch = context["branch"]

    # 4. Extract Table
    matched_tables = []
    for t in known_tables:
        pattern = r"\b" + re.escape(t.lower()) + r"\b"
        if re.search(pattern, q_lower):
            matched_tables.append(t)
        # Check singular/plural variants (e.g. order -> orders)
        elif t.endswith("s") and re.search(r"\b" + re.escape(t[:-1].lower()) + r"\b", q_lower):
            matched_tables.append(t)

    table = None
    if len(matched_tables) == 1:
        table = matched_tables[0]
    elif len(matched_tables) > 1:
        # Choose the most specific or first
        table = matched_tables[0]
    elif context.get("table"):
        table = context["table"]
    else:
        # Check for explicit table mention that may not exist in current schema
        tbl_match = re.search(r"\b(?:table|changed|on|for|in|from|modifying)\s+(?:the\s+)?([a-z0-9_]+)\b", q_lower)
        if tbl_match:
            cand = tbl_match.group(1)
            stop_words = {"the", "a", "an", "all", "schema", "commits", "main", "last", "month", "week"}
            if cand not in stop_words and not cand.isdigit():
                table = cand

    # 5. Extract Date Range
    date_range = context.get("date_range", "monthly")
    start_date = context.get("start_date")
    end_date = context.get("end_date")

    if re.search(r"\b(last week|this week|weekly|past 7 days|7 days)\b", q_lower):
        date_range = "weekly"
    elif re.search(r"\b(last month|this month|monthly|past 30 days|30 days)\b", q_lower):
        date_range = "monthly"

    # Check for explicit ISO dates YYYY-MM-DD in the text
    iso_dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", q_lower)
    if len(iso_dates) >= 2:
        date_range = "custom"
        start_date = iso_dates[0]
        end_date = iso_dates[1]
    elif len(iso_dates) == 1:
        date_range = "custom"
        start_date = iso_dates[0]
        end_date = None

    # 6. Extract Operation / Metric
    metric = "all"
    if re.search(r"\b(insert(?:ed|s)?|additions?)\b", q_lower):
        metric = "inserts"
    elif re.search(r"\b(updat(?:ed|es)?|modifications?)\b", q_lower):
        metric = "updates"
    elif re.search(r"\b(delet(?:ed|es)?|remov(?:ed|als?))\b", q_lower):
        metric = "deletes"
    elif re.search(r"\b(schema|ddl|columns?|tables? created|alter(?:ed|ations?))\b", q_lower):
        metric = "schema"
    elif re.search(r"\b(merges?|conflicts?)\b", q_lower):
        metric = "merges"
    elif re.search(r"\b(commits?)\b", q_lower):
        metric = "commits"

    return ParsedQuestion(
        raw_question=question,
        question_type=question_type,
        branch=branch,
        table=table,
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
        metric=metric,
        commit_ids=commit_ids,
        clarification_needed=clarification_needed,
    )

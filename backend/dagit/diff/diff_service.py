from typing import Any

from dagit.db.connection import get_db_cursor
from dagit.diff.row_diff import diff_rows
from dagit.diff.schema_diff import diff_schema
from dagit.versioning.storage import load_snapshot_from_storage


def compare_snapshots(old_snapshot: dict[str, Any], new_snapshot: dict[str, Any]) -> dict[str, Any]:
    old_tables = old_snapshot.get("tables", {})
    new_tables = new_snapshot.get("tables", {})
    row_changes = []

    for table_name in sorted(old_tables.keys() | new_tables.keys()):
        old_table = old_tables.get(table_name, {"rows": []})
        new_table = new_tables.get(table_name, {"rows": []})
        for change in diff_rows(old_table, new_table):
            row_changes.append({"table": table_name, **change})

    return {
        "schema_changes": diff_schema(old_snapshot, new_snapshot),
        "row_changes": row_changes,
    }


def compare_commits(from_commit_id: int, to_commit_id: int) -> dict[str, Any]:
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT commit_id, state_id FROM datagit_commits WHERE commit_id IN (%s, %s);",
            (from_commit_id, to_commit_id),
        )
        commits = {row["commit_id"]: row["state_id"] for row in cursor.fetchall()}

    missing = {from_commit_id, to_commit_id} - commits.keys()
    if missing:
        raise ValueError(f"Unknown commit ID(s): {', '.join(map(str, sorted(missing)))}")

    result = compare_snapshots(
        load_snapshot_from_storage(commits[from_commit_id]),
        load_snapshot_from_storage(commits[to_commit_id]),
    )
    return {"from_commit_id": from_commit_id, "to_commit_id": to_commit_id, **result}

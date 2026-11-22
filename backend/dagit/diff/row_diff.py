import json
from collections import Counter
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _row_key(row: dict[str, Any], primary_keys: list[str]) -> str:
    return _canonical([row.get(column) for column in primary_keys])


def diff_rows(old_table: dict[str, Any], new_table: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic INSERT, UPDATE, and DELETE operations for two table snapshots."""
    old_rows = old_table.get("rows", [])
    new_rows = new_table.get("rows", [])
    primary_keys = old_table.get("primary_keys") or new_table.get("primary_keys") or []

    if primary_keys:
        old_by_key = {_row_key(row, primary_keys): row for row in old_rows}
        new_by_key = {_row_key(row, primary_keys): row for row in new_rows}
        if len(old_by_key) != len(old_rows) or len(new_by_key) != len(new_rows):
            raise ValueError("Snapshot contains duplicate primary-key values")

        changes: list[dict[str, Any]] = []
        for key in sorted(old_by_key.keys() - new_by_key.keys()):
            changes.append({"operation": "DELETE", "key": {name: old_by_key[key].get(name) for name in primary_keys},
                            "before": old_by_key[key]})
        for key in sorted(new_by_key.keys() - old_by_key.keys()):
            changes.append({"operation": "INSERT", "key": {name: new_by_key[key].get(name) for name in primary_keys},
                            "after": new_by_key[key]})
        for key in sorted(old_by_key.keys() & new_by_key.keys()):
            before, after = old_by_key[key], new_by_key[key]
            changed_columns = {
                column for column in before.keys() | after.keys()
                if before.get(column) != after.get(column)
            }
            if changed_columns:
                changes.append({
                    "operation": "UPDATE",
                    "key": {name: after.get(name) for name in primary_keys},
                    "before": before,
                    "after": after,
                    "changed_columns": sorted(changed_columns),
                })
        return changes

    old_counts = Counter(_canonical(row) for row in old_rows)
    new_counts = Counter(_canonical(row) for row in new_rows)
    changes = []
    for operation, source, target in (
        ("DELETE", old_counts, new_counts),
        ("INSERT", new_counts, old_counts),
    ):
        for row_key in sorted(source.keys()):
            difference = source[row_key] - target[row_key]
            row = json.loads(row_key)
            changes.extend({
                "operation": operation,
                "key": None,
                "after" if operation == "INSERT" else "before": row,
            } for _ in range(max(difference, 0)))
    return changes

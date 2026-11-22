from typing import Any


_CONSTRAINTS = ("primary_keys", "foreign_keys", "unique_constraints", "check_constraints")


def _column_map(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {column["name"]: column for column in table.get("columns", [])}


def diff_schema(old_snapshot: dict[str, Any], new_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe table, column, and constraint changes between two snapshots."""
    old_tables = old_snapshot.get("tables", {})
    new_tables = new_snapshot.get("tables", {})
    changes: list[dict[str, Any]] = []

    for table_name in sorted(old_tables.keys() - new_tables.keys()):
        changes.append({"operation": "DROP_TABLE", "table": table_name,
                        "before": old_tables[table_name]})
    for table_name in sorted(new_tables.keys() - old_tables.keys()):
        changes.append({"operation": "CREATE_TABLE", "table": table_name,
                        "after": new_tables[table_name]})

    for table_name in sorted(old_tables.keys() & new_tables.keys()):
        old_table, new_table = old_tables[table_name], new_tables[table_name]
        old_columns, new_columns = _column_map(old_table), _column_map(new_table)

        for name in sorted(old_columns.keys() - new_columns.keys()):
            changes.append({"operation": "DROP_COLUMN", "table": table_name, "column": name,
                            "before": old_columns[name]})
        for name in sorted(new_columns.keys() - old_columns.keys()):
            changes.append({"operation": "ADD_COLUMN", "table": table_name, "column": name,
                            "after": new_columns[name]})
        for name in sorted(old_columns.keys() & new_columns.keys()):
            if old_columns[name] != new_columns[name]:
                changes.append({"operation": "ALTER_COLUMN", "table": table_name, "column": name,
                                "before": old_columns[name], "after": new_columns[name]})

        constraint_fields = (
            ("constraints",)
            if "constraints" in old_table or "constraints" in new_table
            else _CONSTRAINTS
        )
        for constraint in constraint_fields:
            old_value, new_value = old_table.get(constraint, []), new_table.get(constraint, [])
            if old_value != new_value:
                changes.append({"operation": "ALTER_CONSTRAINT", "table": table_name,
                                "constraint": constraint, "before": old_value, "after": new_value})

    return changes

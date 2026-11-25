from typing import Any


_CONSTRAINTS = ("primary_keys", "foreign_keys", "unique_constraints", "check_constraints")
_TABLE_METADATA = ("indexes", "triggers", "privileges")


def _column_map(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {column["name"]: column for column in table.get("columns", [])}


def _diff_named_objects(
    old_map: dict[str, Any],
    new_map: dict[str, Any],
    kind: str,
    drop_op: str,
    create_op: str,
    alter_op: str,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for name in sorted(old_map.keys() - new_map.keys()):
        changes.append({"operation": drop_op, kind: name, "before": old_map[name]})
    for name in sorted(new_map.keys() - old_map.keys()):
        changes.append({"operation": create_op, kind: name, "after": new_map[name]})
    for name in sorted(old_map.keys() & new_map.keys()):
        if old_map[name] != new_map[name]:
            changes.append({
                "operation": alter_op,
                kind: name,
                "before": old_map[name],
                "after": new_map[name],
            })
    return changes


def diff_schema(old_snapshot: dict[str, Any], new_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe table, column, constraint, index, trigger, privilege, view, and sequence changes."""
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

        for field in _TABLE_METADATA:
            old_value, new_value = old_table.get(field, []), new_table.get(field, [])
            if old_value != new_value:
                changes.append({
                    "operation": "ALTER_TABLE_METADATA",
                    "table": table_name,
                    "field": field,
                    "before": old_value,
                    "after": new_value,
                })

    changes.extend(_diff_named_objects(
        old_snapshot.get("views") or {},
        new_snapshot.get("views") or {},
        "view",
        "DROP_VIEW",
        "CREATE_VIEW",
        "ALTER_VIEW",
    ))
    changes.extend(_diff_named_objects(
        old_snapshot.get("sequences") or {},
        new_snapshot.get("sequences") or {},
        "sequence",
        "DROP_SEQUENCE",
        "CREATE_SEQUENCE",
        "ALTER_SEQUENCE",
    ))

    return changes

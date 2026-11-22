import json
from typing import Any

from psycopg2 import sql
from dagit.db.connection import get_db_cursor
from dagit.versioning.commit import record_commit_in_cursor
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.snapshot import compute_snapshot_hash, generate_database_snapshot
from dagit.versioning.storage import load_snapshot_from_storage


_MISSING = object()
_INTERNAL_TABLES = (
    "datagit_states",
    "datagit_commits",
    "datagit_branches",
    "datagit_workspace",
    "datagit_commit_parents",
)
_NAMED_COLLECTIONS = {
    "columns": "name",
    "constraints": "name",
    "foreign_keys": "name",
    "unique_constraints": "name",
    "check_constraints": "name",
}


class MergeConflictError(ValueError):
    def __init__(self, conflicts: list[dict[str, Any]]):
        self.conflicts = conflicts
        super().__init__(f"Merge has {len(conflicts)} conflict(s)")


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _merge_value(base, ours, theirs):
    if ours == theirs:
        return ours, False
    if ours == base:
        return theirs, False
    if theirs == base:
        return ours, False
    return _MISSING, True


def _merge_collection(base, ours, theirs, identity: str):
    base_map = {item[identity]: item for item in base}
    ours_map = {item[identity]: item for item in ours}
    theirs_map = {item[identity]: item for item in theirs}
    merged = []
    conflicts = []

    for name in sorted(base_map.keys() | ours_map.keys() | theirs_map.keys()):
        value, conflict = _merge_value(
            base_map.get(name, _MISSING),
            ours_map.get(name, _MISSING),
            theirs_map.get(name, _MISSING),
        )
        if conflict:
            conflicts.append(name)
        elif value is not _MISSING:
            merged.append(value)
    if identity == "name" and merged and all("ordinal_position" in item for item in merged):
        merged.sort(key=lambda item: (item["ordinal_position"], item[identity]))
    return merged, conflicts


def _merge_schema(base: dict, ours: dict, theirs: dict):
    merged = {}
    conflicts = []
    fields = base.keys() | ours.keys() | theirs.keys()
    for field in sorted(fields - {"rows"}):
        base_value = base.get(field, [] if field in _NAMED_COLLECTIONS or field == "primary_keys" else _MISSING)
        ours_value = ours.get(field, [] if field in _NAMED_COLLECTIONS or field == "primary_keys" else _MISSING)
        theirs_value = theirs.get(field, [] if field in _NAMED_COLLECTIONS or field == "primary_keys" else _MISSING)

        if field in _NAMED_COLLECTIONS:
            value, field_conflicts = _merge_collection(
                base_value, ours_value, theirs_value, _NAMED_COLLECTIONS[field]
            )
            conflicts.extend(
                {"field": field, "name": name} for name in field_conflicts
            )
        else:
            value, has_conflict = _merge_value(base_value, ours_value, theirs_value)
            if has_conflict:
                conflicts.append({"field": field})
        if value is not _MISSING:
            merged[field] = value
    return merged, conflicts


def _key(row: dict, primary_keys: list[str]) -> str:
    return _canonical([row.get(name) for name in primary_keys])


def _row_map(rows: list[dict], primary_keys: list[str]):
    result = {_key(row, primary_keys): row for row in rows}
    if len(result) != len(rows):
        raise ValueError("Snapshot has duplicate primary-key values")
    return result


def _merge_rows(table_name: str, base_table: dict, ours_table: dict, theirs_table: dict,
                primary_keys: list[str]):
    base_rows = base_table.get("rows", [])
    ours_rows = ours_table.get("rows", [])
    theirs_rows = theirs_table.get("rows", [])
    if not primary_keys:
        if ours_rows == theirs_rows:
            return ours_rows, []
        if ours_rows == base_rows:
            return theirs_rows, []
        if theirs_rows == base_rows:
            return ours_rows, []
        return [], [{"type": "row", "table": table_name, "key": None,
                     "reason": "Concurrent changes to a table without a primary key"}]

    base_map = _row_map(base_rows, primary_keys)
    ours_map = _row_map(ours_rows, primary_keys)
    theirs_map = _row_map(theirs_rows, primary_keys)
    merged_rows = []
    conflicts = []

    for key in sorted(base_map.keys() | ours_map.keys() | theirs_map.keys()):
        base_row = base_map.get(key, _MISSING)
        ours_row = ours_map.get(key, _MISSING)
        theirs_row = theirs_map.get(key, _MISSING)
        if ours_row == theirs_row:
            value = ours_row
        elif ours_row == base_row:
            value = theirs_row
        elif theirs_row == base_row:
            value = ours_row
        elif all(isinstance(row, dict) for row in (base_row, ours_row, theirs_row)):
            value = {}
            row_conflict = False
            columns = base_row.keys() | ours_row.keys() | theirs_row.keys()
            for column in columns:
                column_value, conflict = _merge_value(
                    base_row.get(column, _MISSING),
                    ours_row.get(column, _MISSING),
                    theirs_row.get(column, _MISSING),
                )
                if conflict:
                    row_conflict = True
                    break
                if column_value is not _MISSING:
                    value[column] = column_value
            if row_conflict:
                conflicts.append({"type": "row", "table": table_name,
                                  "key": {name: ours_row.get(name) for name in primary_keys},
                                  "reason": "Both branches changed the same row incompatibly"})
                continue
        else:
            if base_row is _MISSING:
                reason = "Both branches inserted different values for the same primary key"
            else:
                reason = "One branch deleted a row changed by the other"
            conflicts.append({"type": "row", "table": table_name,
                              "key": {name: (base_row if isinstance(base_row, dict) else
                                             ours_row if isinstance(ours_row, dict) else
                                             theirs_row).get(name)
                                      for name in primary_keys},
                              "reason": reason})
            continue
        if value is not _MISSING:
            merged_rows.append(value)

    merged_rows.sort(key=lambda row: _key(row, primary_keys))
    return merged_rows, conflicts


def _merge_table(table_name: str, base: dict, ours: dict, theirs: dict):
    if ours == theirs:
        return ours, []
    if ours == base:
        return theirs, []
    if theirs == base:
        return ours, []

    base_schema = {} if base is _MISSING else base
    ours_schema = {} if ours is _MISSING else ours
    theirs_schema = {} if theirs is _MISSING else theirs
    schema, schema_conflicts = _merge_schema(base_schema, ours_schema, theirs_schema)
    if schema_conflicts:
        return None, [
            {"type": "schema", "table": table_name, **conflict}
            for conflict in schema_conflicts
        ]
    if base is _MISSING:
        base_table = {"rows": []}
    else:
        base_table = base
    primary_keys = schema.get("primary_keys", [])

    if base is not _MISSING and (
        ours_schema.get("primary_keys", []) != base_schema.get("primary_keys", [])
        and theirs.get("rows", []) != base.get("rows", [])
    ):
        return None, [{"type": "schema", "table": table_name,
                       "field": "primary_keys",
                       "reason": "A primary-key change conflicts with row changes"}]
    if base is not _MISSING and (
        theirs_schema.get("primary_keys", []) != base_schema.get("primary_keys", [])
        and ours.get("rows", []) != base.get("rows", [])
    ):
        return None, [{"type": "schema", "table": table_name,
                       "field": "primary_keys",
                       "reason": "A primary-key change conflicts with row changes"}]

    rows, row_conflicts = _merge_rows(
        table_name,
        base_table,
        ours_schema,
        theirs_schema,
        primary_keys,
    )
    valid_columns = {column["name"] for column in schema.get("columns", [])}
    rows = [
        {name: value for name, value in row.items() if name in valid_columns}
        for row in rows
    ]
    return {**schema, "rows": rows}, row_conflicts


def _validate_relations(snapshot: dict) -> list[dict[str, Any]]:
    tables = snapshot.get("tables", {})
    conflicts = []
    for table_name, table in tables.items():
        rows = table.get("rows", [])
        primary_keys = table.get("primary_keys", [])
        unique_constraints = table.get("unique_constraints")
        foreign_keys = table.get("foreign_keys")
        if unique_constraints is None:
            unique_constraints = [
                constraint for constraint in table.get("constraints", [])
                if constraint.get("type") == "u"
            ]
        if foreign_keys is None:
            foreign_keys = [
                constraint for constraint in table.get("constraints", [])
                if constraint.get("type") == "f"
            ]

        constraints_to_check = [("PRIMARY KEY", primary_keys, True)] + [
            (constraint.get("name", "UNIQUE"), constraint.get("columns", []), False)
            for constraint in unique_constraints
        ]
        for constraint_name, columns, is_primary_key in constraints_to_check:
            seen = set()
            for row in rows:
                values = tuple(_canonical(row.get(column)) for column in columns)
                if is_primary_key and any(
                    row.get(column) is None for column in columns
                ):
                    conflicts.append({
                        "type": "constraint",
                        "table": table_name,
                        "constraint": constraint_name,
                        "key": {column: row.get(column) for column in columns},
                        "reason": "Primary-key columns cannot be null",
                    })
                    break
                if not is_primary_key and any(
                    row.get(column) is None for column in columns
                ):
                    continue
                if values in seen:
                    conflicts.append({
                        "type": "constraint",
                        "table": table_name,
                        "constraint": constraint_name,
                        "key": {column: row.get(column) for column in columns},
                        "reason": "Duplicate key violates a primary-key or unique constraint",
                    })
                    break
                seen.add(values)

        constraints = table.get("constraints", [])
        columns = {column.get("name") for column in table.get("columns", [])}
        for constraint in constraints:
            missing = set(constraint.get("columns") or []) - columns
            if missing:
                conflicts.append({
                    "type": "schema",
                    "table": table_name,
                    "constraint": constraint.get("name"),
                    "reason": f"Constraint references missing column(s): "
                              f"{', '.join(sorted(missing))}",
                })

        for constraint in foreign_keys:
            referenced_table = constraint.get("referenced_table")
            if not referenced_table:
                continue
            if constraint.get("referenced_schema") not in (None, "public"):
                continue
            referenced_table = referenced_table.split(".")[-1].strip('"')
            referenced = tables.get(referenced_table)
            columns = constraint.get("columns", [])
            referenced_columns = constraint.get("referenced_columns", [])
            if referenced is None:
                conflicts.append({
                    "type": "constraint",
                    "table": table_name,
                    "constraint": constraint.get("name"),
                    "reason": f"Referenced table {referenced_table!r} is missing",
                })
                continue
            if (
                len(columns) != len(referenced_columns)
                or set(referenced_columns)
                - {column.get("name") for column in referenced.get("columns", [])}
            ):
                conflicts.append({
                    "type": "schema",
                    "table": table_name,
                    "constraint": constraint.get("name"),
                    "reason": "Foreign-key columns do not match the referenced table schema",
                })
                continue
            referenced_keys = {
                tuple(_canonical(row.get(column)) for column in referenced_columns)
                for row in referenced.get("rows", [])
            }
            for row in rows:
                values = tuple(_canonical(row.get(column)) for column in columns)
                if any(row.get(column) is None for column in columns):
                    continue
                if values not in referenced_keys:
                    conflicts.append({
                        "type": "constraint",
                        "table": table_name,
                        "constraint": constraint.get("name"),
                        "key": {column: row.get(column) for column in columns},
                        "reason": "Foreign-key value has no matching referenced row",
                    })
                    break
    return conflicts


def merge_snapshots(base: dict, ours: dict, theirs: dict) -> dict[str, Any]:
    """Three-way merge snapshots; report conflicts instead of choosing a winner."""
    base_tables = base.get("tables", {})
    ours_tables = ours.get("tables", {})
    theirs_tables = theirs.get("tables", {})
    merged_tables = {}
    conflicts = []

    for table_name in sorted(base_tables.keys() | ours_tables.keys() | theirs_tables.keys()):
        merged, table_conflicts = _merge_table(
            table_name,
            base_tables.get(table_name, _MISSING),
            ours_tables.get(table_name, _MISSING),
            theirs_tables.get(table_name, _MISSING),
        )
        conflicts.extend(table_conflicts)
        if merged is not None and merged is not _MISSING:
            merged_tables[table_name] = merged

    merged_snapshot = {"tables": merged_tables}
    conflicts.extend(_validate_relations(merged_snapshot))
    return {"snapshot": None if conflicts else merged_snapshot, "conflicts": conflicts}


def _ancestor_depths(cursor, commit_id: int) -> dict[int, int]:
    cursor.execute("""
        WITH RECURSIVE ancestors(commit_id, depth) AS (
            SELECT %s::INTEGER, 0
            UNION ALL
            SELECT p.parent_commit_id, a.depth + 1
            FROM datagit_commit_parents p
            JOIN ancestors a ON a.commit_id = p.commit_id
        )
        SELECT commit_id, MIN(depth) AS depth
        FROM ancestors
        GROUP BY commit_id;
    """, (commit_id,))
    return {row["commit_id"]: row["depth"] for row in cursor.fetchall()}


def merge_commits(
    source_commit_id: int,
    author: str = "DataGit",
    message: str | None = None,
) -> int:
    """Merge a commit into the active branch and atomically apply a conflict-free result."""
    init_metadata_tables()
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT w.active_branch, b.head_commit
            FROM datagit_workspace w
            LEFT JOIN datagit_branches b ON b.name = w.active_branch
            WHERE w.singleton = TRUE;
        """)
        workspace = cursor.fetchone()
        if workspace["active_branch"] is None or workspace["head_commit"] is None:
            raise ValueError("Merging requires an active branch with a commit")
        target_commit_id = workspace["head_commit"]
        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
            (source_commit_id,),
        )
        source = cursor.fetchone()
        if source is None:
            raise ValueError(f"Unknown source commit ID: {source_commit_id}")
        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
            (target_commit_id,),
        )
        target = cursor.fetchone()
        if target_commit_id == source_commit_id:
            raise ValueError("Cannot merge a commit into itself")

        target_ancestors = _ancestor_depths(cursor, target_commit_id)
        source_ancestors = _ancestor_depths(cursor, source_commit_id)
        common = target_ancestors.keys() & source_ancestors.keys()
        if not common:
            raise ValueError("Commits do not have a common ancestor")
        base_commit_id = min(
            common,
            key=lambda commit: (
                target_ancestors[commit] + source_ancestors[commit],
                -commit,
            ),
        )
        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
            (base_commit_id,),
        )
        base = cursor.fetchone()

    base_snapshot = load_snapshot_from_storage(base["state_id"])
    target_snapshot = load_snapshot_from_storage(target["state_id"])
    source_snapshot = load_snapshot_from_storage(source["state_id"])

    result = merge_snapshots(base_snapshot, target_snapshot, source_snapshot)
    if result["conflicts"]:
        raise MergeConflictError(result["conflicts"])
    merged_snapshot = result["snapshot"]

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            SELECT w.active_branch, b.head_commit
            FROM datagit_workspace w
            LEFT JOIN datagit_branches b ON b.name = w.active_branch
            WHERE w.singleton = TRUE
            FOR UPDATE OF w;
        """)
        latest_workspace = cursor.fetchone()
        if (
            latest_workspace["active_branch"] != workspace["active_branch"]
            or latest_workspace["head_commit"] != target_commit_id
        ):
            raise ValueError("Active branch changed while the merge was being prepared")

        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name <> ALL(%s)
            ORDER BY table_name;
        """, (list(_INTERNAL_TABLES),))
        for row in cursor.fetchall():
            cursor.execute(
                sql.SQL("LOCK TABLE {}.{} IN ACCESS EXCLUSIVE MODE").format(
                    sql.Identifier("public"), sql.Identifier(row["table_name"])
                )
            )
        current_snapshot = generate_database_snapshot(cursor=cursor)
        if compute_snapshot_hash(current_snapshot) != compute_snapshot_hash(target_snapshot):
            raise ValueError(
                "Working database has uncommitted changes; commit or restore before merging"
            )

        restore_snapshot_in_cursor(cursor, merged_snapshot)
        return record_commit_in_cursor(
            cursor,
            merged_snapshot,
            message or f"Merge commit {source_commit_id}",
            author,
            parent_commit_id=target_commit_id,
            second_parent_commit_id=source_commit_id,
        )


def merge_branch(name: str, author: str = "DataGit", message: str | None = None) -> int:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT head_commit FROM datagit_branches WHERE name = %s;", (name,))
        branch = cursor.fetchone()
    if branch is None or branch["head_commit"] is None:
        raise ValueError(f"Branch {name!r} does not have a commit to merge")
    return merge_commits(branch["head_commit"], author=author, message=message)

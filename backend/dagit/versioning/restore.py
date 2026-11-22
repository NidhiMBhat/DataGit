from typing import Any

from psycopg2 import sql
from psycopg2.extras import Json


_INTERNAL_TABLES = {
    "datagit_states",
    "datagit_commits",
    "datagit_branches",
    "datagit_workspace",
    "datagit_commit_parents",
}


def _column_type(column: dict[str, Any]) -> str:
    value = column.get("type")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid type for snapshot column {column.get('name')!r}")
    return value


def _constraints(table_name: str, table: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = table.get("constraints")
    if constraints is not None:
        return constraints
    primary_keys = table.get("primary_keys", [])
    if primary_keys:
        columns = ", ".join(
            '"' + column.replace('"', '""') + '"' for column in primary_keys
        )
        return [{
            "name": f"{table_name}_pkey",
            "type": "p",
            "definition": f"PRIMARY KEY ({columns})",
        }]
    return []


def restore_snapshot_in_cursor(cursor, snapshot: dict[str, Any]) -> None:
    """Replace public application tables from a snapshot inside the caller's transaction."""
    tables = snapshot.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Snapshot must contain a tables object")
    if any(not isinstance(name, str) or not name for name in tables):
        raise ValueError("Snapshot table names must be non-empty strings")
    if _INTERNAL_TABLES.intersection(tables):
        raise ValueError("Snapshot must not include DataGit metadata tables")

    cursor.execute("""
        SELECT t.relname AS table_name, c.conname AS constraint_name
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relkind IN ('r', 'p')
          AND c.contype = 'f'
          AND t.relname <> ALL(%s);
    """, (list(_INTERNAL_TABLES),))
    for row in cursor.fetchall():
        cursor.execute(
            sql.SQL("ALTER TABLE {}.{} DROP CONSTRAINT {}").format(
                sql.Identifier("public"),
                sql.Identifier(row["table_name"]),
                sql.Identifier(row["constraint_name"]),
            )
        )

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
            sql.SQL("DROP TABLE {}.{}").format(
                sql.Identifier("public"), sql.Identifier(row["table_name"])
            )
        )

    for table_name in sorted(tables):
        if not isinstance(table_name, str) or not table_name:
            raise ValueError("Snapshot table names must be non-empty strings")
        table = tables[table_name]
        columns = table.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ValueError(f"Snapshot table {table_name!r} must have columns")

        definitions = []
        identity_columns = []
        for column in columns:
            column_name = column.get("name")
            if not isinstance(column_name, str) or not column_name:
                raise ValueError(f"Snapshot table {table_name!r} has an invalid column name")
            definition = sql.SQL("{} {}").format(
                sql.Identifier(column_name), sql.SQL(_column_type(column))
            )
            identity = column.get("identity", "")
            default = column.get("default")
            sequence = column.get("sequence")
            is_serial = bool(sequence and isinstance(default, str)
                             and default.lstrip().startswith("nextval("))
            if identity or is_serial:
                generation = "ALWAYS" if identity == "a" else "BY DEFAULT"
                definition += sql.SQL(" GENERATED {} AS IDENTITY").format(
                    sql.SQL(generation)
                )
                identity_columns.append(column_name)
            elif default is not None:
                if not isinstance(default, str):
                    raise ValueError(f"Invalid default expression for {table_name}.{column_name}")
                definition += sql.SQL(" DEFAULT ") + sql.SQL(default)
            if column.get("nullable") is False:
                definition += sql.SQL(" NOT NULL")
            definitions.append(definition)

        cursor.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier("public"),
                sql.Identifier(table_name),
                sql.SQL(", ").join(definitions),
            )
        )

        rows = table.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"Snapshot rows for {table_name!r} must be a list")
        column_names = [column["name"] for column in columns]
        if rows:
            json_columns = {
                column["name"]
                for column in columns
                if column.get("type") in ("json", "jsonb")
            }
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Snapshot rows for {table_name!r} must be objects")
                extra_columns = row.keys() - set(column_names)
                if extra_columns:
                    raise ValueError(
                        f"Snapshot row in {table_name!r} has unknown columns: "
                        f"{', '.join(sorted(extra_columns))}"
                    )
                row_columns = [name for name in column_names if name in row]
                if not row_columns:
                    cursor.execute(
                        sql.SQL("INSERT INTO {}.{} DEFAULT VALUES").format(
                            sql.Identifier("public"), sql.Identifier(table_name)
                        )
                    )
                    continue
                placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in row_columns)
                identity_override = (
                    sql.SQL(" OVERRIDING SYSTEM VALUE") if identity_columns else sql.SQL("")
                )
                insert = sql.SQL("INSERT INTO {}.{} ({}){} VALUES ({})").format(
                    sql.Identifier("public"),
                    sql.Identifier(table_name),
                    sql.SQL(", ").join(sql.Identifier(name) for name in row_columns),
                    identity_override,
                    placeholders,
                )
                values = [
                    Json(row.get(name)) if name in json_columns and row.get(name) is not None
                    else row.get(name)
                    for name in row_columns
                ]
                cursor.execute(insert, values)

        for column_name in identity_columns:
            cursor.execute(
                "SELECT pg_get_serial_sequence(%s, %s) AS sequence_name;",
                (f"public.{table_name}", column_name),
            )
            sequence_row = cursor.fetchone()
            if sequence_row["sequence_name"] is not None and rows:
                cursor.execute(
                    sql.SQL("SELECT MAX({}) AS maximum FROM {}.{}").format(
                        sql.Identifier(column_name),
                        sql.Identifier("public"),
                        sql.Identifier(table_name),
                    )
                )
                maximum = cursor.fetchone()["maximum"]
                if maximum is not None:
                    cursor.execute(
                        "SELECT setval(%s::regclass, %s, TRUE);",
                        (sequence_row["sequence_name"], maximum),
                    )

    constraint_rows = []
    for table_name, table in tables.items():
        for constraint in _constraints(table_name, table):
            if not isinstance(constraint.get("name"), str) or not constraint.get("definition"):
                raise ValueError(f"Invalid constraint in snapshot table {table_name!r}")
            constraint_rows.append((table_name, constraint))

    constraint_rows.sort(key=lambda item: (
        item[1].get("type") == "f", item[0], item[1]["name"]
    ))
    for table_name, constraint in constraint_rows:
        cursor.execute(
            sql.SQL("ALTER TABLE {}.{} ADD CONSTRAINT {} {}").format(
                sql.Identifier("public"),
                sql.Identifier(table_name),
                sql.Identifier(constraint["name"]),
                sql.SQL(constraint["definition"]),
            )
        )

from typing import Any

from psycopg2 import sql
from psycopg2.extras import Json


_INTERNAL_TABLES = {
    "datagit_states",
    "datagit_commits",
    "datagit_branches",
    "datagit_workspace",
    "datagit_commit_parents",
    "datagit_merge_events",
    "datagit_tracking_meta",
}

_ALLOWED_PRIVILEGES = {
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
    "ALL",
    "ALL PRIVILEGES",
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


def _restore_sequences(cursor, sequences: dict[str, Any]) -> None:
    for seq_name in sorted(sequences):
        seq = sequences[seq_name]
        data_type = seq.get("data_type", "bigint")
        if data_type not in ("smallint", "integer", "bigint"):
            raise ValueError(f"Unsupported sequence data type {data_type!r} for {seq_name!r}")
        cycle_sql = sql.SQL("CYCLE") if seq.get("cycle") else sql.SQL("NO CYCLE")
        cursor.execute(
            sql.SQL(
                "CREATE SEQUENCE {}.{} AS {} INCREMENT BY {} MINVALUE {} "
                "MAXVALUE {} START WITH {} CACHE {} {}"
            ).format(
                sql.Identifier("public"),
                sql.Identifier(seq_name),
                sql.SQL(data_type),
                sql.Literal(int(seq.get("increment_by", 1))),
                sql.Literal(int(seq.get("min_value", 1))),
                sql.Literal(int(seq.get("max_value", 9223372036854775807))),
                sql.Literal(int(seq.get("start_value", 1))),
                sql.Literal(int(seq.get("cache_size", 1))),
                cycle_sql,
            )
        )
        last_value = seq.get("last_value")
        is_called = seq.get("is_called")
        if last_value is not None and is_called is not None:
            cursor.execute(
                "SELECT setval(%s::regclass, %s, %s);",
                (f'public."{seq_name.replace(chr(34), chr(34) * 2)}"', int(last_value), bool(is_called)),
            )


def _restore_views(cursor, views: dict[str, Any]) -> None:
    for view_name in sorted(views):
        view = views[view_name]
        definition = view.get("definition")
        if not isinstance(definition, str) or not definition.strip():
            raise ValueError(f"Invalid view definition for {view_name!r}")
        cleaned_definition = definition.strip().rstrip(";")
        cursor.execute(
            sql.SQL("CREATE OR REPLACE VIEW {}.{} AS {}").format(
                sql.Identifier("public"),
                sql.Identifier(view_name),
                sql.SQL(cleaned_definition),
            )
        )


def _restore_table_privileges(cursor, table_name: str, privileges: list[dict[str, Any]]) -> None:
    if not privileges:
        return
    cursor.execute("SELECT current_user AS current_role;")
    current_role = cursor.fetchone()["current_role"]
    for privilege in privileges:
        grantee = privilege.get("grantee")
        priv_type = (privilege.get("privilege_type") or "").upper()
        if not grantee or priv_type not in _ALLOWED_PRIVILEGES:
            raise ValueError(f"Invalid privilege entry for table {table_name!r}: {privilege!r}")
        if grantee == current_role:
            continue
        if grantee == "PUBLIC":
            grantee_sql = sql.SQL("PUBLIC")
        else:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s;", (grantee,))
            if cursor.fetchone() is None:
                continue
            grantee_sql = sql.Identifier(grantee)
        grant_option = (
            sql.SQL(" WITH GRANT OPTION")
            if str(privilege.get("is_grantable", "NO")).upper() == "YES"
            else sql.SQL("")
        )
        cursor.execute(
            sql.SQL("GRANT {} ON TABLE {}.{} TO {}{}").format(
                sql.SQL(priv_type),
                sql.Identifier("public"),
                sql.Identifier(table_name),
                grantee_sql,
                grant_option,
            )
        )


def restore_snapshot_in_cursor(cursor, snapshot: dict[str, Any]) -> None:
    """Replace public application objects from a snapshot inside the caller's transaction."""
    tables = snapshot.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Snapshot must contain a tables object")
    if any(not isinstance(name, str) or not name for name in tables):
        raise ValueError("Snapshot table names must be non-empty strings")
    if _INTERNAL_TABLES.intersection(tables):
        raise ValueError("Snapshot must not include DataGit metadata tables")

    views = snapshot.get("views") or {}
    sequences = snapshot.get("sequences") or {}
    if not isinstance(views, dict) or not isinstance(sequences, dict):
        raise ValueError("Snapshot views and sequences must be objects when provided")

    cursor.execute("""
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    for row in cursor.fetchall():
        cursor.execute(
            sql.SQL("DROP VIEW IF EXISTS {}.{} CASCADE").format(
                sql.Identifier("public"), sql.Identifier(row["table_name"])
            )
        )

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

    cursor.execute("""
        SELECT s.sequencename AS name
        FROM pg_sequences s
        JOIN pg_class seq_cls ON seq_cls.relname = s.sequencename
        JOIN pg_namespace n
          ON n.oid = seq_cls.relnamespace AND n.nspname = s.schemaname
        WHERE s.schemaname = 'public'
          AND seq_cls.relkind = 'S'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend d
              JOIN pg_class owner_cls ON owner_cls.oid = d.refobjid
              WHERE d.objid = seq_cls.oid
                AND d.deptype IN ('a', 'i')
                AND owner_cls.relnamespace = n.oid
          )
        ORDER BY s.sequencename;
    """)
    for row in cursor.fetchall():
        cursor.execute(
            sql.SQL("DROP SEQUENCE IF EXISTS {}.{} CASCADE").format(
                sql.Identifier("public"), sql.Identifier(row["name"])
            )
        )

    _restore_sequences(cursor, sequences)

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

    for table_name in sorted(tables):
        table = tables[table_name]
        for index in table.get("indexes", []):
            definition = index.get("definition")
            if not isinstance(definition, str) or not definition.strip():
                raise ValueError(f"Invalid index definition for table {table_name!r}")
            cursor.execute(sql.SQL(definition))

        for trigger in table.get("triggers", []):
            definition = trigger.get("definition")
            if not isinstance(definition, str) or not definition.strip():
                raise ValueError(f"Invalid trigger definition for table {table_name!r}")
            cursor.execute(sql.SQL(definition))

        _restore_table_privileges(cursor, table_name, table.get("privileges", []))

    _restore_views(cursor, views)

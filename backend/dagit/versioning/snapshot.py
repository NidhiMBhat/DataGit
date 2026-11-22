import hashlib
import json
from contextlib import nullcontext

from psycopg2 import sql
from dagit.db.connection import get_db_cursor


_INTERNAL_TABLES = (
    "datagit_states",
    "datagit_commits",
    "datagit_branches",
    "datagit_workspace",
    "datagit_commit_parents",
)


def _serialized(value) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def generate_database_snapshot(target_conn_params=None, cursor=None):
    """Capture public application tables, their supported constraints, and rows."""
    snapshot_data = {"tables": {}}

    cursor_context = get_db_cursor() if cursor is None else nullcontext(cursor)
    with cursor_context as cursor:
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name <> ALL(%s)
            ORDER BY table_name;
        """, (list(_INTERNAL_TABLES),))
        tables = [row["table_name"] for row in cursor.fetchall()]

        for table_name in tables:
            cursor.execute("""
                SELECT a.attname AS name,
                       format_type(a.atttypid, a.atttypmod) AS type,
                       NOT a.attnotnull AS nullable,
                       pg_get_expr(d.adbin, d.adrelid) AS default,
                       a.attidentity AS identity,
                       pg_get_serial_sequence(
                           format('%%I.%%I', n.nspname, c.relname), a.attname
                       ) AS sequence
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_attrdef d
                       ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE n.nspname = 'public'
                  AND c.relname = %s
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum;
            """, (table_name,))
            columns = [dict(column) for column in cursor.fetchall()]

            cursor.execute("""
                SELECT c.conname AS name,
                       c.contype AS type,
                       pg_get_constraintdef(c.oid, TRUE) AS definition,
                       ARRAY(
                           SELECT a.attname
                           FROM unnest(c.conkey) WITH ORDINALITY AS key(attnum, position)
                           JOIN pg_attribute a
                             ON a.attrelid = c.conrelid AND a.attnum = key.attnum
                           ORDER BY key.position
                       ) AS columns,
                       CASE WHEN c.contype = 'f' THEN
                           (SELECT referenced.relname
                            FROM pg_class referenced WHERE referenced.oid = c.confrelid)
                       END AS referenced_table,
                       CASE WHEN c.contype = 'f' THEN
                           (SELECT referenced_schema.nspname
                            FROM pg_class referenced
                            JOIN pg_namespace referenced_schema
                              ON referenced_schema.oid = referenced.relnamespace
                            WHERE referenced.oid = c.confrelid)
                       END AS referenced_schema,
                       CASE WHEN c.contype = 'f' THEN ARRAY(
                           SELECT a.attname
                           FROM unnest(c.confkey) WITH ORDINALITY AS key(attnum, position)
                           JOIN pg_attribute a
                             ON a.attrelid = c.confrelid AND a.attnum = key.attnum
                           ORDER BY key.position
                       ) END AS referenced_columns
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname = 'public'
                  AND t.relname = %s
                  AND c.contype IN ('p', 'f', 'u', 'c')
                ORDER BY c.contype, c.conname;
            """, (table_name,))
            constraints = [dict(constraint) for constraint in cursor.fetchall()]
            cursor.execute(
                sql.SQL("SELECT * FROM {}.{}").format(
                    sql.Identifier("public"), sql.Identifier(table_name)
                )
            )
            rows = [dict(row) for row in cursor.fetchall()]
            rows.sort(key=_serialized)

            snapshot_data["tables"][table_name] = {
                "columns": columns,
                "primary_keys": next(
                    (constraint["columns"] for constraint in constraints
                     if constraint["type"] == "p"),
                    [],
                ),
                "foreign_keys": [
                    constraint for constraint in constraints if constraint["type"] == "f"
                ],
                "unique_constraints": [
                    constraint for constraint in constraints if constraint["type"] == "u"
                ],
                "check_constraints": [
                    constraint for constraint in constraints if constraint["type"] == "c"
                ],
                "constraints": constraints,
                "rows": rows,
            }

    return snapshot_data


def compute_snapshot_hash(snapshot_dict):
    """Generate a SHA-256 content hash for a serialized snapshot."""
    serialized = json.dumps(snapshot_dict, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

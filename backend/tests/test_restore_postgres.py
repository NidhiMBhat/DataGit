from psycopg2.extras import RealDictCursor

from dagit.db.connection import get_db_connection
from dagit.versioning.restore import restore_snapshot_in_cursor


def test_restore_recreates_tables_constraints_and_identity_values_atomically():
    snapshot = {
        "tables": {
            "restore_parent_probe": {
                "columns": [
                    {"name": "id", "type": "integer", "identity": "d", "nullable": False},
                    {"name": "name", "type": "text", "nullable": False},
                    {"name": "score", "type": "integer", "default": "7", "nullable": True},
                ],
                "primary_keys": ["id"],
                "foreign_keys": [],
                "unique_constraints": [{
                    "name": "restore_parent_probe_name_key",
                    "type": "u",
                    "definition": "UNIQUE (name)",
                    "columns": ["name"],
                }],
                "check_constraints": [{
                    "name": "restore_parent_probe_score_check",
                    "type": "c",
                    "definition": "CHECK (score >= 0)",
                    "columns": ["score"],
                }],
                "constraints": [
                    {"name": "restore_parent_probe_pkey", "type": "p",
                     "definition": "PRIMARY KEY (id)", "columns": ["id"]},
                    {"name": "restore_parent_probe_name_key", "type": "u",
                     "definition": "UNIQUE (name)", "columns": ["name"]},
                    {"name": "restore_parent_probe_score_check", "type": "c",
                     "definition": "CHECK (score >= 0)", "columns": ["score"]},
                ],
                "rows": [{"id": 20, "name": "parent", "score": 8}],
            },
            "restore_child_probe": {
                "columns": [
                    {"name": "id", "type": "integer", "nullable": False},
                    {"name": "parent_id", "type": "integer", "nullable": False},
                ],
                "primary_keys": ["id"],
                "foreign_keys": [{
                    "name": "restore_child_probe_parent_fkey",
                    "type": "f",
                    "definition": "FOREIGN KEY (parent_id) REFERENCES restore_parent_probe(id)",
                    "columns": ["parent_id"],
                    "referenced_table": "restore_parent_probe",
                    "referenced_schema": "public",
                    "referenced_columns": ["id"],
                }],
                "unique_constraints": [],
                "check_constraints": [],
                "constraints": [
                    {"name": "restore_child_probe_pkey", "type": "p",
                     "definition": "PRIMARY KEY (id)", "columns": ["id"]},
                    {"name": "restore_child_probe_parent_fkey", "type": "f",
                     "definition": "FOREIGN KEY (parent_id) REFERENCES restore_parent_probe(id)",
                     "columns": ["parent_id"], "referenced_table": "restore_parent_probe",
                     "referenced_schema": "public", "referenced_columns": ["id"]},
                ],
                "rows": [{"id": 1, "parent_id": 20}],
            },
        }
    }

    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    try:
        restore_snapshot_in_cursor(cursor, snapshot)
        cursor.execute("""
            SELECT child.id, parent.name, parent.score
            FROM public.restore_child_probe child
            JOIN public.restore_parent_probe parent ON parent.id = child.parent_id;
        """)
        assert dict(cursor.fetchone()) == {"id": 1, "name": "parent", "score": 8}

        cursor.execute("""
            INSERT INTO public.restore_parent_probe (name)
            VALUES ('generated') RETURNING id, score;
        """)
        assert dict(cursor.fetchone()) == {"id": 21, "score": 7}
    finally:
        connection.rollback()
        cursor.close()
        connection.close()

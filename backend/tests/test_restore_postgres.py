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


def test_restore_recreates_views_indexes_triggers_sequences_and_privileges():
    connection = get_db_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("""
            CREATE OR REPLACE FUNCTION public.probe_touch_fn()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.label := upper(NEW.label);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        snapshot = {
            "tables": {
                "ext_probe": {
                    "columns": [
                        {"name": "id", "type": "integer", "nullable": False},
                        {"name": "label", "type": "text", "nullable": False},
                    ],
                    "primary_keys": ["id"],
                    "constraints": [
                        {
                            "name": "ext_probe_pkey",
                            "type": "p",
                            "definition": "PRIMARY KEY (id)",
                            "columns": ["id"],
                        }
                    ],
                    "indexes": [
                        {
                            "name": "idx_ext_probe_label",
                            "definition": "CREATE INDEX idx_ext_probe_label ON public.ext_probe USING btree (label)",
                        }
                    ],
                    "triggers": [
                        {
                            "name": "trg_ext_probe_upper",
                            "definition": "CREATE TRIGGER trg_ext_probe_upper BEFORE INSERT ON public.ext_probe FOR EACH ROW EXECUTE FUNCTION public.probe_touch_fn()",
                        }
                    ],
                    "privileges": [
                        {"grantee": "PUBLIC", "privilege_type": "SELECT", "is_grantable": "NO"}
                    ],
                    "rows": [{"id": 1, "label": "alpha"}],
                }
            },
            "views": {
                "ext_probe_view": {
                    "name": "ext_probe_view",
                    "definition": "SELECT id, label FROM public.ext_probe",
                }
            },
            "sequences": {
                "ext_standalone_seq": {
                    "name": "ext_standalone_seq",
                    "data_type": "bigint",
                    "start_value": 10,
                    "min_value": 1,
                    "max_value": 9223372036854775807,
                    "increment_by": 2,
                    "cycle": False,
                    "cache_size": 1,
                    "last_value": 14,
                    "is_called": True,
                }
            },
        }

        restore_snapshot_in_cursor(cursor, snapshot)

        cursor.execute("SELECT label FROM public.ext_probe_view WHERE id = 1;")
        assert cursor.fetchone()["label"] == "alpha"

        cursor.execute("INSERT INTO public.ext_probe (id, label) VALUES (2, 'beta') RETURNING label;")
        assert cursor.fetchone()["label"] == "BETA"

        cursor.execute("SELECT nextval('public.ext_standalone_seq') AS next_val;")
        assert cursor.fetchone()["next_val"] == 16

        cursor.execute("""
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'ext_probe' AND indexname = 'idx_ext_probe_label';
        """)
        assert cursor.fetchone()["indexname"] == "idx_ext_probe_label"
    finally:
        connection.rollback()
        cursor.close()
        connection.close()

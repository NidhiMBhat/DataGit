import json
import hashlib
from dagit.db.connection import get_db_cursor

def generate_database_snapshot(target_conn_params=None):
    """
    Extracts all user tables, columns, constraints, and rows, 
    sorting them deterministically to create a snapshot dictionary.
    """
    snapshot_data = {"tables": {}}

    with get_db_cursor() as cursor:
        # 1. Fetch all user tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = [row["table_name"] for row in cursor.fetchall()]

        for table in tables:
            # 2. Fetch columns for each table
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """, (table,))
            columns = [{"name": col["column_name"], "type": col["data_type"]} for col in cursor.fetchall()]

            # 3. Fetch primary key information
            cursor.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_schema = 'public' 
                  AND tc.table_name = %s 
                  AND tc.constraint_type = 'PRIMARY KEY';
            """, (table,))
            primary_keys = [row["column_name"] for row in cursor.fetchall()]

            # 4. Fetch all rows ordered by primary key (or fallback) to ensure determinism
            pk_order = ", ".join(primary_keys) if primary_keys else columns[0]["name"]
            cursor.execute(f"SELECT * FROM {table} ORDER BY {pk_order} ASC;")
            rows = [dict(row) for row in cursor.fetchall()]

            snapshot_data["tables"][table] = {
                "columns": columns,
                "primary_keys": primary_keys,
                "rows": rows
            }

    return snapshot_data

def compute_snapshot_hash(snapshot_dict):
    """Generates a secure SHA-256 content hash of the serialized snapshot."""
    serialized = json.dumps(snapshot_dict, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
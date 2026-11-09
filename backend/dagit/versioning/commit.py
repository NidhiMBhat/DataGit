import uuid
from dagit.versioning.snapshot import generate_database_snapshot, compute_snapshot_hash
from dagit.versioning.storage import save_snapshot_to_storage
from dagit.versioning.metadata import init_metadata_tables
from dagit.db.connection import get_db_cursor

def create_commit(message: str, author: str, parent_commit_id: int = None) -> int:
    """
    1. Initializes metadata schema if missing.
    2. Generates current database snapshot.
    3. Hashes and saves snapshot to storage.
    4. Records commit and state references in DB.
    """
    init_metadata_tables()

    # 1. Generate snapshot & compute state hash
    snapshot_data = generate_database_snapshot()
    state_id = compute_snapshot_hash(snapshot_data)

    # 2. Save payload to file storage
    storage_ref = save_snapshot_to_storage(state_id, snapshot_data)

    with get_db_cursor(commit=True) as cursor:
        # 3. Ensure state entry exists
        cursor.execute("""
            INSERT INTO datagit_states (state_id, storage_reference)
            VALUES (%s, %s)
            ON CONFLICT (state_id) DO NOTHING;
        """, (state_id, storage_ref))

        # 4. Insert commit record
        cursor.execute("""
            INSERT INTO datagit_commits (parent_commit, state_id, message, author)
            VALUES (%s, %s, %s, %s)
            RETURNING commit_id;
        """, (parent_commit_id, state_id, message, author))
        
        result = cursor.fetchone()
        commit_id = result["commit_id"] if isinstance(result, dict) else result[0]
        
    return commit_id
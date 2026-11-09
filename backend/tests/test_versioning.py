import pytest
from dagit.db.connection import get_db_cursor
from dagit.versioning.commit import create_commit
from dagit.versioning.storage import load_snapshot_from_storage

def test_full_commit_workflow():
    # 1. Setup a dummy test table in your target PostgreSQL database
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_users (
                id INT PRIMARY KEY,
                name VARCHAR(50)
            );
            INSERT INTO test_users (id, name) VALUES (1, 'Alice')
            ON CONFLICT (id) DO NOTHING;
        """)

    # 2. Perform a commit
    commit_id = create_commit(message="Initial commit with test_users", author="Nidhi")
    assert commit_id is not None
    print(f"Successfully created commit ID: {commit_id}")

    # 3. Verify database state retrieval
    with get_db_cursor() as cursor:
        cursor.execute("SELECT state_id FROM datagit_commits WHERE commit_id = %s;", (commit_id,))
        row = cursor.fetchone()
        state_id = row["state_id"] if isinstance(row, dict) else row[0]

    snapshot = load_snapshot_from_storage(state_id)
    assert "test_users" in snapshot["tables"]
    assert len(snapshot["tables"]["test_users"]["rows"]) >= 1
    print("Snapshot verified successfully from storage:", snapshot)
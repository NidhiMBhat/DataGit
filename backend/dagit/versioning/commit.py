from dagit.versioning.snapshot import generate_database_snapshot, compute_snapshot_hash
from dagit.versioning.storage import save_snapshot_to_storage
from dagit.versioning.metadata import init_metadata_tables
from dagit.db.connection import get_db_cursor


def record_commit_in_cursor(
    cursor,
    snapshot_data: dict,
    message: str,
    author: str,
    parent_commit_id: int | None = None,
    second_parent_commit_id: int | None = None,
) -> int:
    state_id = compute_snapshot_hash(snapshot_data)
    storage_ref = save_snapshot_to_storage(state_id, snapshot_data)

    cursor.execute("""
        SELECT active_branch, detached_commit
        FROM datagit_workspace
        WHERE singleton = TRUE
        FOR UPDATE;
    """)
    workspace = cursor.fetchone()
    active_branch = workspace["active_branch"]

    if active_branch is not None:
        cursor.execute(
            "SELECT head_commit FROM datagit_branches WHERE name = %s FOR UPDATE;",
            (active_branch,),
        )
        branch_head = cursor.fetchone()["head_commit"]
        if parent_commit_id is None:
            parent_commit_id = branch_head
        elif branch_head != parent_commit_id:
            raise ValueError("Commit parent must match the active branch head")
    elif parent_commit_id is None:
        parent_commit_id = workspace["detached_commit"]

    if second_parent_commit_id is not None:
        if second_parent_commit_id == parent_commit_id:
            raise ValueError("Merge parents must be different commits")
        cursor.execute(
            "SELECT 1 FROM datagit_commits WHERE commit_id = %s;",
            (second_parent_commit_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError(f"Unknown second parent commit ID: {second_parent_commit_id}")

    cursor.execute("""
        INSERT INTO datagit_states (state_id, storage_reference)
        VALUES (%s, %s)
        ON CONFLICT (state_id) DO NOTHING;
    """, (state_id, storage_ref))
    cursor.execute("""
        INSERT INTO datagit_commits (parent_commit, state_id, message, author)
        VALUES (%s, %s, %s, %s)
        RETURNING commit_id;
    """, (parent_commit_id, state_id, message, author))
    commit_id = cursor.fetchone()["commit_id"]

    if parent_commit_id is not None:
        cursor.execute("""
            INSERT INTO datagit_commit_parents (commit_id, parent_commit_id, parent_order)
            VALUES (%s, %s, 1)
            ON CONFLICT (commit_id, parent_order) DO NOTHING;
        """, (commit_id, parent_commit_id))
    if second_parent_commit_id is not None:
        cursor.execute("""
            INSERT INTO datagit_commit_parents (commit_id, parent_commit_id, parent_order)
            VALUES (%s, %s, 2);
        """, (commit_id, second_parent_commit_id))

    if active_branch is not None:
        cursor.execute(
            "UPDATE datagit_branches SET head_commit = %s WHERE name = %s;",
            (commit_id, active_branch),
        )
    else:
        cursor.execute(
            "UPDATE datagit_workspace SET detached_commit = %s WHERE singleton = TRUE;",
            (commit_id,),
        )
    return commit_id


def create_commit(message: str, author: str, parent_commit_id: int | None = None) -> int:
    """
    1. Initializes metadata schema if missing.
    2. Generates current database snapshot.
    3. Hashes and saves snapshot to storage.
    4. Records commit and state references in DB.
    """
    init_metadata_tables()

    # 1. Generate the current database snapshot
    snapshot_data = generate_database_snapshot()

    with get_db_cursor(commit=True) as cursor:
        return record_commit_in_cursor(
            cursor, snapshot_data, message, author, parent_commit_id
        )
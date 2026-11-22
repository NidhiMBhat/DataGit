from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.storage import load_snapshot_from_storage


def checkout_commit(commit_id: int) -> int:
    """Restore a commit and enter detached-HEAD mode."""
    init_metadata_tables()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT singleton FROM datagit_workspace WHERE singleton = TRUE FOR UPDATE;"
        )
        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s FOR SHARE;",
            (commit_id,),
        )
        commit = cursor.fetchone()
        if commit is None:
            raise ValueError(f"Unknown commit ID: {commit_id}")
        snapshot = load_snapshot_from_storage(commit["state_id"])
        restore_snapshot_in_cursor(cursor, snapshot)
        cursor.execute("""
            UPDATE datagit_workspace
            SET active_branch = NULL, detached_commit = %s
            WHERE singleton = TRUE;
        """, (commit_id,))
    return commit_id


def checkout_branch(name: str) -> int | None:
    """Restore a branch head and make that branch active."""
    init_metadata_tables()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT singleton FROM datagit_workspace WHERE singleton = TRUE FOR UPDATE;"
        )
        cursor.execute(
            "SELECT head_commit FROM datagit_branches WHERE name = %s FOR SHARE;",
            (name,),
        )
        branch = cursor.fetchone()
        if branch is None:
            raise ValueError(f"Unknown branch: {name}")

        head_commit = branch["head_commit"]
        if head_commit is not None:
            cursor.execute(
                "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
                (head_commit,),
            )
            commit = cursor.fetchone()
            snapshot = load_snapshot_from_storage(commit["state_id"])
            restore_snapshot_in_cursor(cursor, snapshot)

        cursor.execute("""
            UPDATE datagit_workspace
            SET active_branch = %s, detached_commit = NULL
            WHERE singleton = TRUE;
        """, (name,))
    return head_commit

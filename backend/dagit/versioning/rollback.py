from dagit.db.connection import get_db_cursor
from dagit.versioning.commit import record_commit_in_cursor
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.storage import load_snapshot_from_storage


def rollback(commit_id: int | None = None, author: str = "DataGit") -> int:
    """Restore a target state and record the rollback as a new commit."""
    init_metadata_tables()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            SELECT w.active_branch, w.detached_commit, b.head_commit
            FROM datagit_workspace w
            LEFT JOIN datagit_branches b ON b.name = w.active_branch
            WHERE w.singleton = TRUE
            FOR UPDATE OF w;
        """)
        workspace = cursor.fetchone()
        active_branch = workspace["active_branch"]
        current_head = (
            workspace["head_commit"]
            if active_branch is not None
            else workspace["detached_commit"]
        )

        if commit_id is None:
            if current_head is None:
                raise ValueError("There is no current commit to roll back")
            cursor.execute(
                "SELECT parent_commit FROM datagit_commits WHERE commit_id = %s;",
                (current_head,),
            )
            commit_id = cursor.fetchone()["parent_commit"]
            if commit_id is None:
                raise ValueError("The current commit has no parent to roll back to")

        cursor.execute(
            "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
            (commit_id,),
        )
        target = cursor.fetchone()
        if target is None:
            raise ValueError(f"Unknown commit ID: {commit_id}")

        snapshot = load_snapshot_from_storage(target["state_id"])
        restore_snapshot_in_cursor(cursor, snapshot)
        rollback_commit_id = record_commit_in_cursor(
            cursor,
            snapshot,
            f"Rollback to commit {commit_id}",
            author,
            parent_commit_id=current_head,
        )
    return rollback_commit_id

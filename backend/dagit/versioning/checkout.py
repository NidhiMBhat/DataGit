from dagit.api.security import DirtyWorkspaceError, is_dirty_protection_enabled
from dagit.db.connection import get_db_cursor
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.snapshot import compute_snapshot_hash, generate_database_snapshot
from dagit.versioning.storage import load_snapshot_from_storage


def _ensure_clean_workspace(cursor, allow_dirty: bool, require_clean: bool) -> None:
    if allow_dirty or not (require_clean or is_dirty_protection_enabled()):
        return
    cursor.execute("""
        SELECT w.active_branch, w.detached_commit, b.head_commit
        FROM datagit_workspace w
        LEFT JOIN datagit_branches b ON b.name = w.active_branch
        WHERE w.singleton = TRUE;
    """)
    workspace = cursor.fetchone()
    current_head = (
        workspace["head_commit"]
        if workspace["active_branch"] is not None
        else workspace["detached_commit"]
    )
    if current_head is None:
        return
    cursor.execute(
        "SELECT state_id FROM datagit_commits WHERE commit_id = %s;",
        (current_head,),
    )
    head_row = cursor.fetchone()
    if head_row is None:
        return
    head_snapshot = load_snapshot_from_storage(head_row["state_id"])
    current_snapshot = generate_database_snapshot(cursor=cursor)
    if compute_snapshot_hash(current_snapshot) != compute_snapshot_hash(head_snapshot):
        raise DirtyWorkspaceError(
            "Working database has uncommitted changes; commit or pass allow_dirty=True"
        )


def checkout_commit(
    commit_id: int,
    allow_dirty: bool = False,
    require_clean: bool = False,
) -> int:
    """Restore a commit and enter detached-HEAD mode."""
    init_metadata_tables()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT singleton FROM datagit_workspace WHERE singleton = TRUE FOR UPDATE;"
        )
        _ensure_clean_workspace(cursor, allow_dirty=allow_dirty, require_clean=require_clean)
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


def checkout_branch(
    name: str,
    allow_dirty: bool = False,
    require_clean: bool = False,
) -> int | None:
    """Restore a branch head and make that branch active."""
    init_metadata_tables()
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            "SELECT singleton FROM datagit_workspace WHERE singleton = TRUE FOR UPDATE;"
        )
        _ensure_clean_workspace(cursor, allow_dirty=allow_dirty, require_clean=require_clean)
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

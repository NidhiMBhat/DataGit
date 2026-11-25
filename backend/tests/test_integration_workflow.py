import uuid
import pytest

from dagit.api.security import DirtyWorkspaceError
from dagit.db.connection import get_db_cursor
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch, checkout_commit
from dagit.versioning.commit import create_commit
from dagit.versioning.history import get_commit, get_history
from dagit.versioning.merge import MergeConflictError, merge_branch
from dagit.versioning.metadata import init_metadata_tables
from dagit.versioning.restore import restore_snapshot_in_cursor
from dagit.versioning.rollback import rollback
from dagit.versioning.snapshot import compute_snapshot_hash, generate_database_snapshot
from dagit.versioning.storage_benchmark import (
    benchmark_commits,
    reconstruct_snapshots_from_deltas,
)
from dagit.versioning.storage import load_snapshot_from_storage
from dagit.diff.diff_service import compare_commits


@pytest.fixture
def isolated_postgres_workspace():
    """Preserve and restore any pre-existing database state around integration tests."""
    init_metadata_tables()
    with get_db_cursor() as cursor:
        baseline = generate_database_snapshot(cursor=cursor)

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            DROP VIEW IF EXISTS public.it_items_view CASCADE;
            DROP TABLE IF EXISTS public.it_items CASCADE;
            DROP SEQUENCE IF EXISTS public.it_seq CASCADE;
            CREATE SEQUENCE public.it_seq START 100 INCREMENT 5;
            CREATE TABLE public.it_items (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE INDEX idx_it_items_status ON public.it_items (status);
            CREATE VIEW public.it_items_view AS
                SELECT id, name, status FROM public.it_items WHERE status <> 'archived';
            INSERT INTO public.it_items (id, name, status) VALUES (1, 'alpha', 'open');
        """)
    try:
        yield
    finally:
        with get_db_cursor(commit=True) as cursor:
            restore_snapshot_in_cursor(cursor, baseline)


def test_end_to_end_branching_checkout_rollback_merge_and_tx_rollback(isolated_postgres_workspace):
    suffix = uuid.uuid4().hex[:8]
    feature_branch = f"feature/integration-{suffix}"
    conflict_branch = f"feature/conflict-{suffix}"

    # 1. Initial commit on main
    c1 = create_commit("Initial items", "IntegrationTester")

    # 2. Create feature branch and advance it
    branch_info = create_branch(feature_branch, from_commit_id=c1)
    assert branch_info["name"] == feature_branch
    checkout_branch(feature_branch)

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE public.it_items SET status = 'done' WHERE id = 1;")
        cursor.execute("INSERT INTO public.it_items (id, name, status) VALUES (2, 'beta', 'open');")
    c2 = create_commit("Update item 1 and insert item 2 on feature", "IntegrationTester")

    # 3. Switch back to main and verify exact restoration
    checkout_branch("main")
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, status FROM public.it_items ORDER BY id;")
        assert [dict(r) for r in cursor.fetchall()] == [
            {"id": 1, "name": "alpha", "status": "open"}
        ]

    # 4. Dirty workspace protection before checkout/rollback
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE public.it_items SET name = 'dirty-edit' WHERE id = 1;")
    with pytest.raises(DirtyWorkspaceError):
        checkout_branch(feature_branch, require_clean=True)
    # Explicit allow_dirty succeeds and restores clean target branch
    checkout_branch(feature_branch, allow_dirty=True, require_clean=True)
    checkout_branch("main")

    # 5. Advance main on a disjoint column/row so 3-way merge succeeds cleanly
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE public.it_items SET name = 'alpha-main' WHERE id = 1;")
    c3 = create_commit("Rename item 1 on main", "IntegrationTester")

    # 6. Merge feature branch into main -> two-parent merge commit
    merge_id = merge_branch(feature_branch, author="IntegrationTester")
    merge_meta = get_commit(merge_id)
    assert merge_meta["parents"] == [c3, c2]

    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, status FROM public.it_items ORDER BY id;")
        assert [dict(r) for r in cursor.fetchall()] == [
            {"id": 1, "name": "alpha-main", "status": "done"},
            {"id": 2, "name": "beta", "status": "open"},
        ]

    # 7. Merge conflict detection leaves DB untouched
    create_branch(conflict_branch, from_commit_id=c1)
    checkout_branch(conflict_branch)
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE public.it_items SET name = 'conflict-name' WHERE id = 1;")
    create_commit("Conflicting edit on item 1", "IntegrationTester")

    checkout_branch("main")
    with pytest.raises(MergeConflictError) as exc_info:
        merge_branch(conflict_branch, author="IntegrationTester")
    assert exc_info.value.conflicts

    # 8. Detached-HEAD checkout and rollback
    checkout_commit(c1)
    branches = list_branches()
    assert all(not branch["is_current"] for branch in branches)

    checkout_branch("main")
    rollback_id = rollback(commit_id=c1, author="IntegrationTester")
    history = get_history(branch="main", limit=3)
    assert history[0]["commit_id"] == rollback_id
    with get_db_cursor() as cursor:
        cursor.execute("SELECT id, name, status FROM public.it_items ORDER BY id;")
        assert [dict(r) for r in cursor.fetchall()] == [
            {"id": 1, "name": "alpha", "status": "open"}
        ]

    # 9. Transaction rollback on failed restoration preserves database state
    with pytest.raises(ValueError):
        with get_db_cursor(commit=True) as cursor:
            restore_snapshot_in_cursor(
                cursor,
                {"tables": {"broken": {"columns": [{"name": "id", "type": ""}]}}},
            )
    with get_db_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS cnt FROM public.it_items;")
        assert cursor.fetchone()["cnt"] == 1

    # 10. Storage benchmark and delta reconstruction on real commits
    bench = benchmark_commits([c1, merge_id], iterations=2)
    assert bench["measurements"]["delta"]["verified_reconstruction"] is True
    assert bench["measurements"]["shared_tables"]["verified_reconstruction"] is True
    diff_payload = compare_commits(c1, merge_id)
    assert diff_payload["row_changes"]
    snap_c1 = load_snapshot_from_storage(get_commit(c1)["state_id"])
    snap_merge = load_snapshot_from_storage(merge_meta["state_id"])
    reconstructed = reconstruct_snapshots_from_deltas([{"base_snapshot": snap_c1}, diff_payload])
    assert compute_snapshot_hash(reconstructed[1]) == compute_snapshot_hash(snap_merge)

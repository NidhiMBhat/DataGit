from datetime import datetime, timedelta, timezone
from io import StringIO
import csv
import pytest
from fastapi.testclient import TestClient

from dagit.api.app import app
from dagit.db.connection import get_db_cursor
from dagit.reports.merge_events import (
    fetch_merge_history,
    get_tracking_metadata,
    get_tracking_start_date,
    record_merge_event,
)
from dagit.reports.report_service import (
    generate_csv_report,
    generate_pdf_report,
    generate_report,
    get_reachable_commit_ids,
)
from dagit.versioning.branch import create_branch, list_branches
from dagit.versioning.checkout import checkout_branch
from dagit.versioning.commit import create_commit
from dagit.versioning.merge import MergeConflictError, merge_branch, merge_commits
from dagit.versioning.metadata import init_metadata_tables


@pytest.fixture
def clean_db():
    """Ensure metadata tables are clean and initialized."""
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            DROP TABLE IF EXISTS datagit_merge_events CASCADE;
            DROP TABLE IF EXISTS datagit_tracking_meta CASCADE;
            DROP TABLE IF EXISTS datagit_commit_parents CASCADE;
            DROP TABLE IF EXISTS datagit_workspace CASCADE;
            DROP TABLE IF EXISTS datagit_branches CASCADE;
            DROP TABLE IF EXISTS datagit_commits CASCADE;
            DROP TABLE IF EXISTS datagit_states CASCADE;
            DROP TABLE IF EXISTS report_test_items CASCADE;
        """)
        cursor.execute("""
            CREATE TABLE report_test_items (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                val INT DEFAULT 0
            );
        """)
    init_metadata_tables()
    yield
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DROP TABLE IF EXISTS report_test_items CASCADE;")


def test_tracking_metadata_initialization(clean_db):
    meta = get_tracking_metadata()
    assert "merge_outcome_tracking_started_at" in meta
    start_date = get_tracking_start_date()
    assert isinstance(start_date, str)
    assert len(start_date) > 0


def test_merge_event_recording_and_preview_exclusion(clean_db):
    # Preview should NOT be recorded
    eid_prev = record_merge_event(
        actor="Alice",
        source_commit_id=2,
        target_commit_id=1,
        outcome="conflict",
        is_preview=True,
    )
    assert eid_prev is None

    # Actual conflict attempt
    eid_conf = record_merge_event(
        actor="Bob",
        source_commit_id=2,
        target_commit_id=1,
        outcome="conflict",
        conflict_details=[{"table": "report_test_items", "type": "row"}],
        is_preview=False,
    )
    assert eid_conf is not None

    # Actual rejection (e.g. dirty workspace or validation)
    eid_rej = record_merge_event(
        actor="Charlie",
        source_commit_id=None,
        target_commit_id=None,
        outcome="rejected",
        error_message="Working database has uncommitted changes",
        is_preview=False,
    )
    assert eid_rej is not None

    # Successful merge
    eid_succ = record_merge_event(
        actor="David",
        source_commit_id=3,
        target_commit_id=1,
        outcome="success",
        merge_commit_id=None,
        is_preview=False,
    )
    assert eid_succ is not None

    events = fetch_merge_history()
    outcomes = [ev["outcome"] for ev in events]
    assert "conflict" in outcomes
    assert "rejected" in outcomes
    assert "success" in outcomes


def test_end_to_end_commits_branches_and_reporting(clean_db):
    # 1. Initial root commit on main
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO report_test_items (id, name, val) VALUES (1, 'item1', 10), (2, 'item2', 20);")
    c1 = create_commit(message="Initial commit", author="Admin")
    assert c1 is not None

    # 2. Branch feature-a from main
    create_branch("feature-a", from_commit_id=c1)
    checkout_branch("feature-a")
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO report_test_items (id, name, val) VALUES (3, 'item3_fa', 30);")
        cursor.execute("UPDATE report_test_items SET val = 15 WHERE id = 1;")
    c2 = create_commit(message="Feature A commit", author="Alice")

    # 3. Branch feature-b from main
    create_branch("feature-b", from_commit_id=c1)
    checkout_branch("feature-b")
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO report_test_items (id, name, val) VALUES (4, 'item4_fb', 40);")
    c3 = create_commit(message="Feature B commit", author="Bob")

    # 4. Switch back to main and checkout
    checkout_branch("main")
    # Reachability test:
    fa_commits = get_reachable_commit_ids("feature-a")
    fb_commits = get_reachable_commit_ids("feature-b")
    main_commits = get_reachable_commit_ids("main")

    # c1 is shared between feature-a and feature-b
    assert c1 in fa_commits
    assert c1 in fb_commits
    assert c1 in main_commits
    assert c2 in fa_commits
    assert c2 not in fb_commits
    assert c3 in fb_commits
    assert c3 not in fa_commits

    # 5. Advance main on non-conflicting row, then merge feature-b into main
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE report_test_items SET val = 25 WHERE id = 2;")
    c4 = create_commit(message="Update item2 on main", author="Admin")

    m1 = merge_branch("feature-b", author="Releaser", message="Merge feature-b into main")
    assert m1 is not None

    # Verify Activity report
    rep_activity = generate_report(mode="activity", date_range="monthly", branch="main")
    # c1, c3, c4, m1 are reachable from main
    assert rep_activity["summary"]["total_commits"] == 4
    assert rep_activity["summary"]["unique_authors"] >= 2
    assert any(c["is_merge"] for c in rep_activity["details"])
    assert "Reachable from branch: main" in rep_activity["filters"]["branch_label"]

    # Verify Data & Schema report
    rep_data = generate_report(mode="data_schema", date_range="monthly")
    assert rep_data["summary"]["rows_inserted"] >= 3
    assert len(rep_data["chart_series"]["table_row_changes"]) > 0

    # Table filter
    rep_tbl = generate_report(mode="data_schema", date_range="monthly", table="report_test_items")
    assert rep_tbl["filters"]["table"] == "report_test_items"
    assert all(row["table"] == "report_test_items" for row in rep_tbl["details"])

    # Verify Merge & Conflict report
    rep_merge = generate_report(mode="merge_conflict", date_range="monthly")
    assert rep_merge["summary"]["total_attempts"] >= 1
    assert rep_merge["summary"]["success_count"] >= 1


def test_conflict_recording_in_actual_merge(clean_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO report_test_items (id, name, val) VALUES (1, 'conflict_target', 100);")
    c1 = create_commit(message="Base commit", author="Setup")

    # Branch 1
    create_branch("br-1", from_commit_id=c1)
    checkout_branch("br-1")
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE report_test_items SET val = 200 WHERE id = 1;")
    c2 = create_commit(message="Branch 1 update", author="Worker 1")

    # Branch 2
    create_branch("br-2", from_commit_id=c1)
    checkout_branch("br-2")
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE report_test_items SET val = 300 WHERE id = 1;")
    c3 = create_commit(message="Branch 2 update", author="Worker 2")

    # Attempt to merge br-1 into br-2 (must conflict!)
    with pytest.raises(MergeConflictError) as exc_info:
        merge_branch("br-1", author="Merger")
    assert len(exc_info.value.conflicts) > 0

    # Check that merge event was recorded with outcome="conflict"
    events = fetch_merge_history()
    conflict_evs = [e for e in events if e["outcome"] == "conflict"]
    assert len(conflict_evs) >= 1
    assert conflict_evs[-1]["actor"] == "Merger"
    assert conflict_evs[-1]["conflict_details"] is not None


def test_empty_date_range_graceful_handling(clean_db):
    # Future dates with 0 records
    future_start = "2099-01-01"
    future_end = "2099-01-10"
    rep = generate_report(
        mode="activity",
        date_range="custom",
        start_date=future_start,
        end_date=future_end,
    )
    assert rep["summary"]["total_commits"] == 0
    assert len(rep["details"]) == 0
    assert len(rep["chart_series"]["commit_activity"]) >= 1
    assert all(p["count"] == 0 for p in rep["chart_series"]["commit_activity"])


def test_csv_and_pdf_reconciliation(clean_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO report_test_items (id, name, val) VALUES (1, 'alpha', 1);")
    create_commit(message="Commit 1", author="Dev")

    client = TestClient(app)
    auth_headers = {"X-API-Key": "admin-secret"}

    # 1. Fetch JSON dashboard report
    resp_json = client.get("/api/reports?mode=activity&date_range=monthly", headers=auth_headers)
    assert resp_json.status_code == 200
    json_data = resp_json.json()

    # 2. Fetch CSV export
    resp_csv = client.get("/api/reports/export/csv?mode=activity&date_range=monthly", headers=auth_headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "attachment; filename=" in resp_csv.headers["content-disposition"]
    csv_text = resp_csv.text
    assert "# Report Mode,ACTIVITY" in csv_text
    assert f"total_commits,{json_data['summary']['total_commits']}" in csv_text

    # 3. Fetch PDF export
    resp_pdf = client.get("/api/reports/export/pdf?mode=activity&date_range=monthly", headers=auth_headers)
    assert resp_pdf.status_code == 200
    assert "application/pdf" in resp_pdf.headers["content-type"]
    assert resp_pdf.content.startswith(b"%PDF-")


def test_reports_metadata_endpoint():
    client = TestClient(app)
    auth_headers = {"X-API-Key": "read-secret"}
    resp = client.get("/api/reports/meta", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "activity" in data["modes"]
    assert "data_schema" in data["modes"]
    assert "merge_conflict" in data["modes"]
    assert "merge_outcome_tracking_started_at" in data

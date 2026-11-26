import pytest
from fastapi.testclient import TestClient

from dagit.api.app import app
from dagit.assistant.assistant_service import ask_datagit, get_suggested_questions
from dagit.assistant.indexer import GLOBAL_INDEXER
from dagit.db.connection import get_db_cursor
from dagit.versioning.branch import create_branch
from dagit.versioning.checkout import checkout_branch
from dagit.versioning.commit import create_commit
from dagit.versioning.metadata import init_metadata_tables


@pytest.fixture
def clean_assistant_db():
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("""
            DROP TABLE IF EXISTS datagit_merge_events CASCADE;
            DROP TABLE IF EXISTS datagit_tracking_meta CASCADE;
            DROP TABLE IF EXISTS datagit_commit_parents CASCADE;
            DROP TABLE IF EXISTS datagit_workspace CASCADE;
            DROP TABLE IF EXISTS datagit_branches CASCADE;
            DROP TABLE IF EXISTS datagit_commits CASCADE;
            DROP TABLE IF EXISTS datagit_states CASCADE;
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS products CASCADE;
        """)
        cursor.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                order_number VARCHAR(32) NOT NULL,
                total NUMERIC(10, 2) DEFAULT 0.00
            );
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                sku VARCHAR(32) NOT NULL,
                price NUMERIC(10, 2) NOT NULL
            );
        """)
    init_metadata_tables()
    yield
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DROP TABLE IF EXISTS orders CASCADE; DROP TABLE IF EXISTS products CASCADE;")


def test_ask_datagit_exact_statistics(clean_assistant_db):
    # Seed commits on main
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO orders (id, order_number, total) VALUES (1, 'ORD-001', 50.00), (2, 'ORD-002', 75.00);")
    c1 = create_commit(message="Initial orders", author="Alice")

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE orders SET total = 90.00 WHERE id = 1;")
        cursor.execute("UPDATE orders SET total = 120.00 WHERE id = 2;")
    c2 = create_commit(message="Update 2 order rows", author="Bob")

    result = ask_datagit("How many order rows were updated on main last month?")
    assert result["question_type"] == "exact_statistics"
    assert result["applied_filters"]["branch"] == "main"
    assert result["applied_filters"]["table"] == "orders"
    assert "**2**" in result["answer"] and "row updates on table `orders`" in result["answer"]
    assert result["report_summary"]["rows_updated"] == 2


def test_ask_datagit_evidence_discovery(clean_assistant_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO orders (id, order_number) VALUES (1, 'ORD-001');")
    c1 = create_commit(message="Initial orders table", author="Alice")

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("ALTER TABLE orders ADD COLUMN notes TEXT;")
    c2 = create_commit(message="Add notes column to orders", author="Bob")

    result = ask_datagit("Which commits changed the orders schema last month?")
    assert result["question_type"] == "evidence_discovery"
    assert len(result["evidence"]) >= 1
    c2_ev = next(e for e in result["evidence"] if e["commit_id"] == c2)
    assert "orders" in c2_ev["impacted_tables"]
    assert any("notes" in s.get("details", "") or "orders" in s.get("table", "") for s in c2_ev["schema_changes"])
    assert f"[#{c2}]" in result["answer"]


def test_ask_datagit_explanation_and_spike_detection(clean_assistant_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO orders (id, order_number, total) VALUES (1, 'ORD-001', 10.00);")
    c1 = create_commit(message="Base orders", author="Admin")

    with get_db_cursor(commit=True) as cursor:
        cursor.execute("UPDATE orders SET total = 20.00 WHERE id = 1;")
    c2 = create_commit(message="Bulk update order totals during flash sale", author="Sales Lead")

    result = ask_datagit("Which commits contributed most to the spike in order updates?")
    assert result["question_type"] == "explanation"
    assert len(result["evidence"]) >= 1
    assert "Primary Contributing Commits" in result["answer"] or "Change Analysis" in result["answer"]
    assert str(c2) in result["answer"]


def test_ask_datagit_ambiguity_and_missing_evidence(clean_assistant_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO orders (id, order_number) VALUES (1, 'ORD-1');")
    c1 = create_commit(message="Base", author="Admin")
    create_branch("feature/one", from_commit_id=c1)
    create_branch("feature/two", from_commit_id=c1)

    # Ambiguous question with two conflicting branches mentioned
    result_ambig = ask_datagit("How many commits between feature/one and feature/two?")
    assert result_ambig["clarification_needed"] is not None
    assert "Multiple branches" in result_ambig["clarification_needed"]

    # Out of scope / missing evidence
    result_missing = ask_datagit("Which commits changed the nonexistent_table_xyz?")
    assert "No commits matching your query were found" in result_missing["answer"] or result_missing["evidence"] == []


def test_ask_datagit_index_refreshes_on_new_commits(clean_assistant_db):
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO products (id, sku, price) VALUES (1, 'TECH-A', 100.00);")
    c1 = create_commit(message="Initial product TECH-A", author="Catalog Lead")

    # Initial search
    res1 = ask_datagit("Which commits added product TECH-A?")
    assert any(e["commit_id"] == c1 for e in res1["evidence"])

    # Now create a brand new commit
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("INSERT INTO products (id, sku, price) VALUES (2, 'SUPER-DISCOVERABLE-SKU', 500.00);")
    c2 = create_commit(message="Add SUPER-DISCOVERABLE-SKU flagship", author="Innovator")

    # Ask DataGit should automatically refresh index and discover c2
    res2 = ask_datagit("Which commits added SUPER-DISCOVERABLE-SKU?")
    assert any(e["commit_id"] == c2 for e in res2["evidence"])
    assert "SUPER-DISCOVERABLE-SKU" in res2["answer"]


def test_assistant_api_endpoints():
    client = TestClient(app)
    headers = {"X-API-Key": "read-secret"}

    # Suggestions endpoint
    res_sug = client.get("/api/assistant/suggestions", headers=headers)
    assert res_sug.status_code == 200
    sugs = res_sug.json()["suggestions"]
    assert len(sugs) >= 3
    categories = {s["type"] for s in sugs}
    assert "exact_statistics" in categories
    assert "evidence_discovery" in categories
    assert "explanation" in categories

    # Ask endpoint
    res_ask = client.post(
        "/api/assistant/ask",
        json={"question": "How many commits on main?"},
        headers=headers,
    )
    assert res_ask.status_code == 200
    data = res_ask.json()
    assert "answer" in data
    assert "applied_filters" in data
    assert "evidence" in data

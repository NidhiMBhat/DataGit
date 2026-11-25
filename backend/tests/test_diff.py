import pytest

from dagit.diff.diff_service import compare_snapshots
from dagit.diff.row_diff import diff_rows
from dagit.diff.schema_diff import diff_schema


def test_diff_rows_reports_insert_update_delete_with_composite_key():
    old = {
        "primary_keys": ["tenant_id", "id"],
        "rows": [
            {"tenant_id": 1, "id": 10, "name": "Alice"},
            {"tenant_id": 1, "id": 11, "name": "Bob"},
        ],
    }
    new = {
        "primary_keys": ["tenant_id", "id"],
        "rows": [
            {"tenant_id": 1, "id": 10, "name": "Alicia"},
            {"tenant_id": 2, "id": 10, "name": "Casey"},
        ],
    }

    changes = diff_rows(old, new)

    assert [(change["operation"], change["key"]) for change in changes] == [
        ("DELETE", {"tenant_id": 1, "id": 11}),
        ("INSERT", {"tenant_id": 2, "id": 10}),
        ("UPDATE", {"tenant_id": 1, "id": 10}),
    ]
    assert changes[-1]["changed_columns"] == ["name"]


def test_diff_rows_handles_duplicate_keyless_rows_as_multisets():
    changes = diff_rows(
        {"rows": [{"value": "same"}, {"value": "same"}]},
        {"rows": [{"value": "same"}, {"value": "new"}]},
    )

    assert [change["operation"] for change in changes] == ["DELETE", "INSERT"]


def test_diff_rows_rejects_duplicate_primary_keys():
    table = {"primary_keys": ["id"], "rows": [{"id": 1}, {"id": 1}]}

    with pytest.raises(ValueError, match="duplicate primary-key"):
        diff_rows(table, {"primary_keys": ["id"], "rows": []})


def test_diff_schema_reports_table_column_type_and_constraint_changes():
    changes = diff_schema(
        {"tables": {"users": {
            "columns": [{"name": "id", "type": "integer"}],
            "primary_keys": ["id"],
        }}},
        {"tables": {"users": {
            "columns": [
                {"name": "id", "type": "bigint"},
                {"name": "email", "type": "text"},
            ],
            "primary_keys": [],
        }, "teams": {"columns": [], "rows": []}}},
    )

    assert [change["operation"] for change in changes] == [
        "CREATE_TABLE", "ADD_COLUMN", "ALTER_COLUMN", "ALTER_CONSTRAINT",
    ]


def test_compare_snapshots_combines_schema_and_row_changes():
    result = compare_snapshots(
        {"tables": {"items": {
            "columns": [{"name": "id", "type": "integer"}],
            "primary_keys": ["id"],
            "rows": [{"id": 1, "name": "old"}],
        }}},
        {"tables": {"items": {
            "columns": [{"name": "id", "type": "integer"}],
            "primary_keys": ["id"],
            "rows": [{"id": 1, "name": "new"}],
        }}},
    )

    assert result["schema_changes"] == []
    assert result["row_changes"][0]["operation"] == "UPDATE"


def test_diff_schema_reports_indexes_triggers_privileges_views_and_sequences():
    old_snapshot = {
        "tables": {
            "items": {
                "columns": [{"name": "id", "type": "integer"}],
                "primary_keys": ["id"],
                "indexes": [],
                "triggers": [],
                "privileges": [],
                "rows": [],
            }
        },
        "views": {"active_items": {"name": "active_items", "definition": "SELECT id FROM items"}},
        "sequences": {"order_seq": {"name": "order_seq", "last_value": 1, "is_called": True}},
    }
    new_snapshot = {
        "tables": {
            "items": {
                "columns": [{"name": "id", "type": "integer"}],
                "primary_keys": ["id"],
                "indexes": [{"name": "idx_items_id", "definition": "CREATE INDEX idx_items_id ON public.items (id)"}],
                "triggers": [{"name": "trg_items", "definition": "CREATE TRIGGER trg_items BEFORE INSERT ON public.items FOR EACH ROW EXECUTE FUNCTION noop()"}],
                "privileges": [{"grantee": "PUBLIC", "privilege_type": "SELECT", "is_grantable": "NO"}],
                "rows": [],
            }
        },
        "views": {
            "active_items": {"name": "active_items", "definition": "SELECT id, 1 AS flag FROM items"},
            "extra_view": {"name": "extra_view", "definition": "SELECT 1"},
        },
        "sequences": {},
    }

    changes = diff_schema(old_snapshot, new_snapshot)
    ops = [change["operation"] for change in changes]
    assert ops.count("ALTER_TABLE_METADATA") == 3
    assert "CREATE_VIEW" in ops
    assert "ALTER_VIEW" in ops
    assert "DROP_SEQUENCE" in ops

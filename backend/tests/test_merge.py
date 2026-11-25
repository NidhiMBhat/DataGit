from dagit.versioning.merge import merge_snapshots


def _snapshot(rows, columns=None, foreign_keys=None):
    return {
        "tables": {
            "items": {
                "columns": columns or [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "text"},
                    {"name": "status", "type": "text"},
                ],
                "primary_keys": ["id"],
                "foreign_keys": foreign_keys or [],
                "rows": rows,
            }
        }
    }


def test_merge_snapshots_combines_disjoint_changes_to_same_row():
    base = _snapshot([{"id": 1, "name": "one", "status": "new"}])
    ours = _snapshot([{"id": 1, "name": "renamed", "status": "new"}])
    theirs = _snapshot([{"id": 1, "name": "one", "status": "done"}])

    result = merge_snapshots(base, ours, theirs)

    assert result["conflicts"] == []
    assert result["snapshot"]["tables"]["items"]["rows"] == [
        {"id": 1, "name": "renamed", "status": "done"}
    ]


def test_merge_snapshots_reports_same_column_conflict():
    base = _snapshot([{"id": 1, "name": "one", "status": "new"}])
    ours = _snapshot([{"id": 1, "name": "ours", "status": "new"}])
    theirs = _snapshot([{"id": 1, "name": "theirs", "status": "new"}])

    result = merge_snapshots(base, ours, theirs)

    assert result["snapshot"] is None
    assert result["conflicts"][0]["type"] == "row"
    assert result["conflicts"][0]["table"] == "items"


def test_merge_snapshots_merges_independently_added_columns():
    base = _snapshot([{"id": 1, "name": "one", "status": "new"}])
    ours = _snapshot(
        [{"id": 1, "name": "one", "status": "new", "color": "blue"}],
        columns=[
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "text"},
            {"name": "status", "type": "text"},
            {"name": "color", "type": "text"},
        ],
    )
    theirs = _snapshot(
        [{"id": 1, "name": "one", "status": "new", "priority": 2}],
        columns=[
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "text"},
            {"name": "status", "type": "text"},
            {"name": "priority", "type": "integer"},
        ],
    )

    result = merge_snapshots(base, ours, theirs)

    assert result["conflicts"] == []
    table = result["snapshot"]["tables"]["items"]
    assert {column["name"] for column in table["columns"]} == {
        "id", "name", "status", "color", "priority"
    }
    assert table["rows"] == [
        {"id": 1, "name": "one", "status": "new", "color": "blue", "priority": 2}
    ]


def test_merge_snapshots_detects_foreign_key_conflict_after_row_merge():
    base = {
        "tables": {
            "parents": {
                "columns": [{"name": "id", "type": "integer"}],
                "primary_keys": ["id"],
                "rows": [{"id": 1}],
            },
            "children": {
                "columns": [{"name": "id", "type": "integer"},
                            {"name": "parent_id", "type": "integer"}],
                "primary_keys": ["id"],
                "foreign_keys": [{
                    "name": "children_parent_fk",
                    "columns": ["parent_id"],
                    "referenced_table": "parents",
                    "referenced_columns": ["id"],
                }],
                "rows": [],
            },
        }
    }
    ours = {
        "tables": {
            "parents": base["tables"]["parents"],
            "children": {
                **base["tables"]["children"],
                "rows": [{"id": 1, "parent_id": 99}],
            },
        }
    }
    theirs = base

    result = merge_snapshots(base, ours, theirs)

    assert result["snapshot"] is None
    assert result["conflicts"][0]["type"] == "constraint"
    assert "Foreign-key" in result["conflicts"][0]["reason"]


def test_merge_snapshots_merges_and_detects_conflicts_in_extended_objects():
    base = {
        "tables": {
            "items": {
                "columns": [{"name": "id", "type": "integer"}],
                "primary_keys": ["id"],
                "indexes": [{"name": "idx_a", "definition": "CREATE INDEX idx_a ON public.items (id)"}],
                "triggers": [],
                "privileges": [{"grantee": "postgres", "privilege_type": "SELECT", "is_grantable": "NO"}],
                "rows": [],
            }
        },
        "views": {"v1": {"name": "v1", "definition": "SELECT id FROM items"}},
        "sequences": {"s1": {"name": "s1", "last_value": 1, "is_called": True}},
    }
    ours = {
        "tables": {
            "items": {
                **base["tables"]["items"],
                "indexes": [
                    {"name": "idx_a", "definition": "CREATE INDEX idx_a ON public.items (id)"},
                    {"name": "idx_b", "definition": "CREATE INDEX idx_b ON public.items (id)"},
                ],
                "privileges": [
                    {"grantee": "postgres", "privilege_type": "SELECT", "is_grantable": "NO"},
                    {"grantee": "PUBLIC", "privilege_type": "SELECT", "is_grantable": "NO"},
                ],
            }
        },
        "views": {
            "v1": {"name": "v1", "definition": "SELECT id FROM items"},
            "v_ours": {"name": "v_ours", "definition": "SELECT 1"},
        },
        "sequences": base["sequences"],
    }
    theirs = {
        "tables": {
            "items": {
                **base["tables"]["items"],
                "triggers": [{"name": "trg_theirs", "definition": "CREATE TRIGGER trg_theirs BEFORE INSERT ON public.items FOR EACH ROW EXECUTE FUNCTION f()"}],
            }
        },
        "views": base["views"],
        "sequences": {
            "s1": {"name": "s1", "last_value": 5, "is_called": True},
        },
    }

    clean = merge_snapshots(base, ours, theirs)
    assert clean["conflicts"] == []
    assert len(clean["snapshot"]["tables"]["items"]["indexes"]) == 2
    assert len(clean["snapshot"]["tables"]["items"]["triggers"]) == 1
    assert len(clean["snapshot"]["tables"]["items"]["privileges"]) == 2
    assert set(clean["snapshot"]["views"]) == {"v1", "v_ours"}
    assert clean["snapshot"]["sequences"]["s1"]["last_value"] == 5

    theirs_conflict = {
        **theirs,
        "views": {"v1": {"name": "v1", "definition": "SELECT id + 1 FROM items"}},
    }
    ours_conflict = {
        **ours,
        "views": {"v1": {"name": "v1", "definition": "SELECT id + 2 FROM items"}},
    }
    conflicted = merge_snapshots(base, ours_conflict, theirs_conflict)
    assert conflicted["snapshot"] is None
    assert any(c.get("object_type") == "view" and c.get("name") == "v1" for c in conflicted["conflicts"])

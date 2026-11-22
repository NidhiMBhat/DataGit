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

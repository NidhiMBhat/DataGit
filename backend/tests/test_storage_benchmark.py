import pytest

from dagit.versioning.storage_benchmark import benchmark_snapshots


def _snapshot(name):
    return {
        "tables": {
            "items": {
                "columns": [{"name": "id", "type": "integer"},
                            {"name": "name", "type": "text"}],
                "primary_keys": ["id"],
                "rows": [{"id": 1, "name": name}],
            },
            "lookup": {
                "columns": [{"name": "code", "type": "text"}],
                "primary_keys": ["code"],
                "rows": [{"code": "fixed"}],
            },
        }
    }


def test_storage_benchmark_rejects_empty_input():
    with pytest.raises(ValueError, match="at least one snapshot"):
        benchmark_snapshots([])


def test_storage_benchmark_compares_jsonb_representations_in_postgresql():
    result = benchmark_snapshots([_snapshot("before"), _snapshot("after")])

    assert result["snapshot_count"] == 2
    assert result["shared_blob_count"] == 3
    assert set(result["measurements"]) == {
        "full_snapshot", "delta", "shared_tables",
    }
    assert all(
        measurement["payload_bytes"] > 0
        for measurement in result["measurements"].values()
    )

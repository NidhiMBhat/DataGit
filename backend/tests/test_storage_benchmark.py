import pytest

from dagit.diff.diff_service import compare_snapshots
from dagit.versioning.snapshot import compute_snapshot_hash
from dagit.versioning.storage_benchmark import (
    apply_diff_to_snapshot,
    benchmark_snapshots,
    generate_benchmark_workload,
    generate_synthetic_snapshots,
    reconstruct_snapshots_from_deltas,
    reconstruct_snapshots_from_shared_tables,
)


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


def test_storage_benchmark_rejects_invalid_iterations():
    with pytest.raises(ValueError, match="iterations"):
        benchmark_snapshots([_snapshot("a")], iterations=0)


def test_delta_and_shared_reconstruction_preserve_snapshot_hashes():
    s0 = {
        "tables": {
            "users": {
                "columns": [{"name": "id", "type": "integer"}, {"name": "name", "type": "text"}],
                "primary_keys": ["id"],
                "rows": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            },
            "logs": {
                "columns": [{"name": "msg", "type": "text"}],
                "primary_keys": [],
                "rows": [{"msg": "init"}, {"msg": "init"}],
            },
        },
        "views": {"user_view": {"name": "user_view", "definition": "SELECT id FROM users"}},
        "sequences": {"ext_seq": {"name": "ext_seq", "last_value": 1, "is_called": True}},
    }
    s1 = {
        "tables": {
            "users": {
                "columns": [
                    {"name": "id", "type": "integer"},
                    {"name": "name", "type": "text"},
                    {"name": "role", "type": "text"},
                ],
                "primary_keys": ["id"],
                "rows": [{"id": 1, "name": "Alicia", "role": None}, {"id": 3, "name": "Cara", "role": "admin"}],
            },
            "orders": {
                "columns": [{"name": "id", "type": "integer"}],
                "primary_keys": ["id"],
                "rows": [{"id": 100}],
            },
        },
        "views": {"user_view": {"name": "user_view", "definition": "SELECT id, name FROM users"}},
        "sequences": {},
    }

    diff_0_to_1 = compare_snapshots(s0, s1)
    reconstructed = reconstruct_snapshots_from_deltas([{"base_snapshot": s0}, diff_0_to_1])
    assert compute_snapshot_hash(reconstructed[0]) == compute_snapshot_hash(s0)
    assert compute_snapshot_hash(reconstructed[1]) == compute_snapshot_hash(s1)

    reconstructed_single = apply_diff_to_snapshot(s0, diff_0_to_1)
    assert compute_snapshot_hash(reconstructed_single) == compute_snapshot_hash(s1)

    blobs = {}
    manifests = []
    meta = []
    for idx, snap in enumerate((s0, s1)):
        meta.append({"views": snap["views"], "sequences": snap["sequences"]})
        for tname, tdata in sorted(snap["tables"].items()):
            bid = compute_snapshot_hash(tdata)
            blobs.setdefault(bid, tdata)
            manifests.append((idx, tname, bid))
    rebuilt_shared = reconstruct_snapshots_from_shared_tables(2, manifests, blobs, meta)
    assert [compute_snapshot_hash(item) for item in rebuilt_shared] == [
        compute_snapshot_hash(s0),
        compute_snapshot_hash(s1),
    ]


def test_synthetic_workload_generator_produces_deterministic_snapshots():
    workload_a = generate_synthetic_snapshots(table_count=3, rows_per_table=20, snapshot_count=5, change_ratio=0.2)
    workload_b = generate_benchmark_workload(table_count=3, rows_per_table=20, commit_count=5, change_ratio=0.2)
    assert len(workload_a) == 5
    assert [compute_snapshot_hash(s) for s in workload_a] == [compute_snapshot_hash(s) for s in workload_b]


def test_storage_benchmark_compares_jsonb_representations_in_postgresql():
    result = benchmark_snapshots([_snapshot("before"), _snapshot("after")], iterations=2)

    assert result["snapshot_count"] == 2
    assert result["iterations"] == 2
    assert result["shared_blob_count"] == 3
    assert set(result["measurements"]) == {
        "full_snapshot", "delta", "shared_tables",
    }
    assert all(
        measurement["payload_bytes"] > 0
        and measurement["total_relation_bytes"] > 0
        and measurement["verified_reconstruction"] is True
        for measurement in result["measurements"].values()
    )
    assert result["recommendation"]["recommended_strategy"] in {
        "full_snapshot", "delta", "shared_tables"
    }

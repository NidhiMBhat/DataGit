import copy
import json
import time
from typing import Any

from psycopg2.extras import Json

from dagit.db.connection import get_db_connection, get_db_cursor
from dagit.diff.diff_service import compare_snapshots
from dagit.versioning.snapshot import compute_snapshot_hash
from dagit.versioning.storage import load_snapshot_from_storage


def _json_adapter(value: Any) -> Json:
    return Json(value, dumps=lambda item: json.dumps(item, default=str))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _row_key(row: dict[str, Any], primary_keys: list[str]) -> str:
    return _canonical([row.get(column) for column in primary_keys])


def _measure_payload_bytes(cursor, query: str) -> int:
    cursor.execute(query)
    return cursor.fetchone()[0]


def apply_diff_to_snapshot(
    base_snapshot: dict[str, Any], diff_payload: dict[str, Any]
) -> dict[str, Any]:
    """Reconstruct a target snapshot by applying a compare_snapshots diff to a base snapshot."""
    snapshot = copy.deepcopy(base_snapshot)
    tables = snapshot.setdefault("tables", {})
    row_changes = diff_payload.get("row_changes", [])
    tables_with_row_changes = {change.get("table") for change in row_changes}

    for change in diff_payload.get("schema_changes", []):
        op = change.get("operation")
        if op == "DROP_TABLE":
            tables.pop(change["table"], None)
        elif op == "CREATE_TABLE":
            table_data = copy.deepcopy(change["after"])
            if change["table"] in tables_with_row_changes:
                table_data["rows"] = []
            tables[change["table"]] = table_data
        elif op == "DROP_COLUMN":
            table_data = tables[change["table"]]
            col_name = change["column"]
            table_data["columns"] = [
                col for col in table_data.get("columns", []) if col.get("name") != col_name
            ]
            for row in table_data.get("rows", []):
                row.pop(col_name, None)
        elif op == "ADD_COLUMN":
            table_data = tables[change["table"]]
            col_name = change["column"]
            table_data.setdefault("columns", []).append(copy.deepcopy(change["after"]))
            for row in table_data.get("rows", []):
                row.setdefault(col_name, None)
        elif op == "ALTER_COLUMN":
            table_data = tables[change["table"]]
            col_name = change["column"]
            table_data["columns"] = [
                copy.deepcopy(change["after"]) if col.get("name") == col_name else col
                for col in table_data.get("columns", [])
            ]
        elif op == "ALTER_CONSTRAINT":
            table_data = tables[change["table"]]
            table_data[change["constraint"]] = copy.deepcopy(change["after"])
        elif op == "ALTER_TABLE_METADATA":
            table_data = tables[change["table"]]
            field = change["field"]
            if change["after"] is None:
                table_data.pop(field, None)
            else:
                table_data[field] = copy.deepcopy(change["after"])
        elif op == "DROP_VIEW":
            views = snapshot.get("views")
            if isinstance(views, dict):
                views.pop(change["view"], None)
        elif op in ("CREATE_VIEW", "ALTER_VIEW"):
            snapshot.setdefault("views", {})[change["view"]] = copy.deepcopy(change["after"])
        elif op == "DROP_SEQUENCE":
            sequences = snapshot.get("sequences")
            if isinstance(sequences, dict):
                sequences.pop(change["sequence"], None)
        elif op in ("CREATE_SEQUENCE", "ALTER_SEQUENCE"):
            snapshot.setdefault("sequences", {})[change["sequence"]] = copy.deepcopy(change["after"])

    changes_by_table: dict[str, list[dict[str, Any]]] = {}
    for change in row_changes:
        changes_by_table.setdefault(change["table"], []).append(change)

    for table_name, table_changes in changes_by_table.items():
        table_data = tables.get(table_name)
        if table_data is None:
            continue
        rows = table_data.get("rows", [])
        primary_keys = table_data.get("primary_keys") or []
        if primary_keys:
            by_key = {_row_key(row, primary_keys): row for row in rows}
            for change in table_changes:
                op = change["operation"]
                if op == "DELETE":
                    key = _row_key(change["before"], primary_keys)
                    by_key.pop(key, None)
                elif op in ("INSERT", "UPDATE"):
                    after = copy.deepcopy(change["after"])
                    key = _row_key(after, primary_keys)
                    by_key[key] = after
            rebuilt_rows = list(by_key.values())
        else:
            rebuilt_rows = list(rows)
            for change in table_changes:
                op = change["operation"]
                if op == "DELETE":
                    target_canon = _canonical(change["before"])
                    for idx, row in enumerate(rebuilt_rows):
                        if _canonical(row) == target_canon:
                            rebuilt_rows.pop(idx)
                            break
                elif op == "INSERT":
                    rebuilt_rows.append(copy.deepcopy(change["after"]))
        rebuilt_rows.sort(key=_canonical)
        table_data["rows"] = rebuilt_rows

    return snapshot


def reconstruct_snapshots_from_deltas(
    delta_payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct an ordered list of full snapshots from a base snapshot plus diffs."""
    if not delta_payloads:
        raise ValueError("Provide at least one delta payload to reconstruct")
    first = delta_payloads[0]
    if "base_snapshot" not in first:
        raise ValueError("First delta payload must contain base_snapshot")

    reconstructed = [copy.deepcopy(first["base_snapshot"])]
    for diff_payload in delta_payloads[1:]:
        reconstructed.append(apply_diff_to_snapshot(reconstructed[-1], diff_payload))
    return reconstructed


def reconstruct_snapshots_from_shared_tables(
    snapshot_count: int,
    manifests: list[tuple[int, str, str]],
    blobs: dict[str, Any],
    top_level_metadata: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct full snapshots from shared per-table blobs and manifest mappings."""
    snapshots = [{"tables": {}} for _ in range(snapshot_count)]
    if top_level_metadata:
        for index, meta in enumerate(top_level_metadata):
            if index < snapshot_count:
                for key, value in meta.items():
                    snapshots[index][key] = copy.deepcopy(value)
    for snapshot_index, table_name, blob_id in manifests:
        snapshots[snapshot_index]["tables"][table_name] = copy.deepcopy(blobs[blob_id])
    return snapshots


def generate_synthetic_snapshots(
    table_count: int = 3,
    rows_per_table: int = 50,
    snapshot_count: int = 10,
    change_ratio: float = 0.1,
) -> list[dict[str, Any]]:
    """Generate deterministic snapshot sequences for repeatable storage benchmarking."""
    if table_count < 1 or rows_per_table < 1 or snapshot_count < 1:
        raise ValueError("table_count, rows_per_table, and snapshot_count must be positive")
    if not 0.0 <= change_ratio <= 1.0:
        raise ValueError("change_ratio must be between 0.0 and 1.0")

    base_tables: dict[str, dict[str, Any]] = {}
    for t_idx in range(table_count):
        table_name = "reference_lookup" if t_idx == 0 and table_count > 1 else f"records_{t_idx}"
        rows = [
            {
                "id": r_idx + 1,
                "label": f"{table_name}_row_{r_idx + 1}",
                "counter": 0,
                "active": (r_idx % 2 == 0),
            }
            for r_idx in range(rows_per_table)
        ]
        rows.sort(key=_canonical)
        base_tables[table_name] = {
            "columns": [
                {"name": "id", "type": "integer", "nullable": False, "default": None, "identity": "", "sequence": None},
                {"name": "label", "type": "text", "nullable": False, "default": None, "identity": "", "sequence": None},
                {"name": "counter", "type": "integer", "nullable": False, "default": "0", "identity": "", "sequence": None},
                {"name": "active", "type": "boolean", "nullable": False, "default": "true", "identity": "", "sequence": None},
            ],
            "primary_keys": ["id"],
            "foreign_keys": [],
            "unique_constraints": [],
            "check_constraints": [],
            "constraints": [
                {"name": f"{table_name}_pkey", "type": "p", "definition": "PRIMARY KEY (id)", "columns": ["id"]},
            ],
            "rows": rows,
        }

    snapshots = [{"tables": copy.deepcopy(base_tables)}]
    changes_per_step = max(1, int(round(rows_per_table * change_ratio))) if change_ratio > 0 else 0
    mutable_tables = [name for name in sorted(base_tables) if name != "reference_lookup"]
    if not mutable_tables:
        mutable_tables = sorted(base_tables)

    for step in range(1, snapshot_count):
        prev = copy.deepcopy(snapshots[-1])
        for table_name in mutable_tables:
            rows = prev["tables"][table_name]["rows"]
            by_id = {row["id"]: row for row in rows}
            for offset in range(changes_per_step):
                target_id = ((step * changes_per_step + offset) % rows_per_table) + 1
                if target_id in by_id:
                    by_id[target_id]["counter"] += 1
                    by_id[target_id]["label"] = f"{table_name}_row_{target_id}_v{step}"
            rebuilt = list(by_id.values())
            rebuilt.sort(key=_canonical)
            prev["tables"][table_name]["rows"] = rebuilt
        snapshots.append(prev)
    return snapshots


def generate_benchmark_workload(
    table_count: int = 3,
    rows_per_table: int = 50,
    commit_count: int = 10,
    change_ratio: float = 0.1,
) -> list[dict[str, Any]]:
    """Alias for generate_synthetic_snapshots using commit_count terminology."""
    return generate_synthetic_snapshots(
        table_count=table_count,
        rows_per_table=rows_per_table,
        snapshot_count=commit_count,
        change_ratio=change_ratio,
    )


def _build_recommendation(measurements: dict[str, dict[str, Any]], snapshot_count: int) -> dict[str, Any]:
    full_bytes = measurements["full_snapshot"]["total_relation_bytes"] or measurements["full_snapshot"]["payload_bytes"]
    delta_bytes = measurements["delta"]["total_relation_bytes"] or measurements["delta"]["payload_bytes"]
    shared_bytes = measurements["shared_tables"]["total_relation_bytes"] or measurements["shared_tables"]["payload_bytes"]

    compression_ratios = {
        "full_snapshot": 1.0,
        "delta": round(full_bytes / delta_bytes, 3) if delta_bytes > 0 else 1.0,
        "shared_tables": round(full_bytes / shared_bytes, 3) if shared_bytes > 0 else 1.0,
    }

    if snapshot_count == 1:
        recommended = "full_snapshot"
        rationale = "Single snapshot workloads do not benefit from delta chains or shared-table manifests."
    elif delta_bytes <= shared_bytes and delta_bytes < full_bytes:
        recommended = "delta"
        rationale = (
            f"Delta storage achieves {compression_ratios['delta']}x total relation compression "
            f"with {measurements['delta']['reconstruct_seconds']:.6f}s chain reconstruction."
        )
    elif shared_bytes < full_bytes:
        recommended = "shared_tables"
        rationale = (
            f"Shared-table deduplication achieves {compression_ratios['shared_tables']}x compression "
            f"when unchanged tables dominate across commits."
        )
    else:
        recommended = "full_snapshot"
        rationale = "Full snapshots avoid reconstruction overhead without exceeding delta/shared storage size."

    return {
        "recommended_strategy": recommended,
        "rationale": rationale,
        "compression_ratios": compression_ratios,
    }


def benchmark_snapshots(snapshots: list[dict[str, Any]], iterations: int = 1) -> dict[str, Any]:
    """Compare PostgreSQL JSONB payload sizes, relation overhead, and reconstruction times."""
    if not snapshots:
        raise ValueError("Provide at least one snapshot to benchmark")
    if type(iterations) is not int or not (1 <= iterations <= 20):
        raise ValueError("iterations must be an integer between 1 and 20")
    if any(
        not isinstance(snapshot, dict) or not isinstance(snapshot.get("tables"), dict)
        for snapshot in snapshots
    ):
        raise ValueError("Every snapshot must contain a tables object")

    snapshot_records = [
        (index, _json_adapter(snapshot))
        for index, snapshot in enumerate(snapshots)
    ]
    delta_records = []
    for index, snapshot in enumerate(snapshots):
        payload = (
            {"base_snapshot": snapshot}
            if index == 0
            else compare_snapshots(snapshots[index - 1], snapshot)
        )
        delta_records.append((index, _json_adapter(payload)))

    blobs: dict[str, dict[str, Any]] = {}
    manifests = []
    top_level_meta: list[dict[str, Any]] = []
    for index, snapshot in enumerate(snapshots):
        meta = {
            key: snapshot[key]
            for key in ("views", "sequences")
            if key in snapshot
        }
        top_level_meta.append(meta)
        for table_name, table_data in sorted(snapshot["tables"].items()):
            blob_id = compute_snapshot_hash(table_data)
            blobs.setdefault(blob_id, table_data)
            manifests.append((index, table_name, blob_id))

    expected_hashes = [compute_snapshot_hash(snapshot) for snapshot in snapshots]

    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            CREATE TEMP TABLE datagit_eval_snapshots (
                snapshot_index INTEGER PRIMARY KEY,
                payload JSONB NOT NULL
            );
            CREATE TEMP TABLE datagit_eval_deltas (
                snapshot_index INTEGER PRIMARY KEY,
                payload JSONB NOT NULL
            );
            CREATE TEMP TABLE datagit_eval_blobs (
                blob_id VARCHAR(64) PRIMARY KEY,
                payload JSONB NOT NULL
            );
            CREATE TEMP TABLE datagit_eval_manifests (
                snapshot_index INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                blob_id VARCHAR(64) NOT NULL,
                PRIMARY KEY (snapshot_index, table_name)
            );
        """)

        snapshot_write_total = 0.0
        delta_write_total = 0.0
        shared_write_total = 0.0
        snapshot_read_total = 0.0
        delta_read_total = 0.0
        shared_read_total = 0.0
        delta_reconstruct_total = 0.0
        shared_reconstruct_total = 0.0
        delta_verified = False
        shared_verified = False

        for iteration in range(iterations):
            if iteration > 0:
                cursor.execute(
                    "TRUNCATE datagit_eval_snapshots, datagit_eval_deltas, "
                    "datagit_eval_manifests, datagit_eval_blobs;"
                )

            started = time.perf_counter()
            cursor.executemany(
                "INSERT INTO datagit_eval_snapshots (snapshot_index, payload) VALUES (%s, %s);",
                snapshot_records,
            )
            snapshot_write_total += time.perf_counter() - started

            started = time.perf_counter()
            cursor.executemany(
                "INSERT INTO datagit_eval_deltas (snapshot_index, payload) VALUES (%s, %s);",
                delta_records,
            )
            delta_write_total += time.perf_counter() - started

            started = time.perf_counter()
            cursor.executemany(
                "INSERT INTO datagit_eval_blobs (blob_id, payload) VALUES (%s, %s);",
                [(blob_id, _json_adapter(payload)) for blob_id, payload in blobs.items()],
            )
            cursor.executemany(
                "INSERT INTO datagit_eval_manifests (snapshot_index, table_name, blob_id) "
                "VALUES (%s, %s, %s);",
                manifests,
            )
            shared_write_total += time.perf_counter() - started

            started = time.perf_counter()
            cursor.execute(
                "SELECT snapshot_index, payload FROM datagit_eval_snapshots "
                "ORDER BY snapshot_index;"
            )
            cursor.fetchall()
            snapshot_read_total += time.perf_counter() - started

            started = time.perf_counter()
            cursor.execute(
                "SELECT snapshot_index, payload FROM datagit_eval_deltas "
                "ORDER BY snapshot_index;"
            )
            fetched_deltas = [row[1] for row in cursor.fetchall()]
            delta_read_total += time.perf_counter() - started

            started = time.perf_counter()
            reconstructed_deltas = reconstruct_snapshots_from_deltas(fetched_deltas)
            delta_reconstruct_total += time.perf_counter() - started
            if iteration == 0:
                delta_verified = (
                    [compute_snapshot_hash(item) for item in reconstructed_deltas] == expected_hashes
                )

            started = time.perf_counter()
            cursor.execute("""
                SELECT m.snapshot_index, m.table_name, m.blob_id, b.payload
                FROM datagit_eval_manifests m
                JOIN datagit_eval_blobs b ON b.blob_id = m.blob_id
                ORDER BY m.snapshot_index, m.table_name;
            """)
            fetched_shared = cursor.fetchall()
            shared_read_total += time.perf_counter() - started

            started = time.perf_counter()
            fetched_manifests = [(row[0], row[1], row[2]) for row in fetched_shared]
            fetched_blobs = {row[2]: row[3] for row in fetched_shared}
            reconstructed_shared = reconstruct_snapshots_from_shared_tables(
                len(snapshots), fetched_manifests, fetched_blobs, top_level_meta
            )
            shared_reconstruct_total += time.perf_counter() - started
            if iteration == 0:
                shared_verified = (
                    [compute_snapshot_hash(item) for item in reconstructed_shared] == expected_hashes
                )

        cursor.execute(
            "ANALYZE datagit_eval_snapshots; ANALYZE datagit_eval_deltas; "
            "ANALYZE datagit_eval_blobs; ANALYZE datagit_eval_manifests;"
        )

        snapshot_bytes = _measure_payload_bytes(
            cursor, "SELECT COALESCE(SUM(pg_column_size(payload)), 0) "
                    "FROM datagit_eval_snapshots;"
        )
        delta_bytes = _measure_payload_bytes(
            cursor, "SELECT COALESCE(SUM(pg_column_size(payload)), 0) "
                    "FROM datagit_eval_deltas;"
        )
        shared_bytes = _measure_payload_bytes(
            cursor, """
                SELECT
                    COALESCE((SELECT SUM(pg_column_size(blob_id) + pg_column_size(payload))
                              FROM datagit_eval_blobs), 0)
                    + COALESCE((SELECT SUM(pg_column_size(snapshot_index)
                                           + pg_column_size(table_name)
                                           + pg_column_size(blob_id))
                                FROM datagit_eval_manifests), 0);
            """
        )

        snapshot_relation_bytes = _measure_payload_bytes(
            cursor, "SELECT pg_total_relation_size('datagit_eval_snapshots');"
        )
        delta_relation_bytes = _measure_payload_bytes(
            cursor, "SELECT pg_total_relation_size('datagit_eval_deltas');"
        )
        shared_relation_bytes = _measure_payload_bytes(
            cursor,
            "SELECT pg_total_relation_size('datagit_eval_blobs') "
            "+ pg_total_relation_size('datagit_eval_manifests');",
        )

        measurements = {
            "full_snapshot": {
                "payload_bytes": snapshot_bytes,
                "total_relation_bytes": snapshot_relation_bytes,
                "write_seconds": snapshot_write_total / iterations,
                "read_seconds": snapshot_read_total / iterations,
                "reconstruct_seconds": 0.0,
                "verified_reconstruction": True,
                "records": len(snapshot_records),
            },
            "delta": {
                "payload_bytes": delta_bytes,
                "total_relation_bytes": delta_relation_bytes,
                "write_seconds": delta_write_total / iterations,
                "read_seconds": delta_read_total / iterations,
                "reconstruct_seconds": delta_reconstruct_total / iterations,
                "verified_reconstruction": delta_verified,
                "records": len(delta_records),
            },
            "shared_tables": {
                "payload_bytes": shared_bytes,
                "total_relation_bytes": shared_relation_bytes,
                "write_seconds": shared_write_total / iterations,
                "read_seconds": shared_read_total / iterations,
                "reconstruct_seconds": shared_reconstruct_total / iterations,
                "verified_reconstruction": shared_verified,
                "records": len(blobs) + len(manifests),
            },
        }

        return {
            "snapshot_count": len(snapshots),
            "iterations": iterations,
            "shared_blob_count": len(blobs),
            "measurements": measurements,
            "recommendation": _build_recommendation(measurements, len(snapshots)),
            "measurement_notes": [
                "payload_bytes uses PostgreSQL pg_column_size; total_relation_bytes uses "
                "pg_total_relation_size (heap, TOAST, and primary-key index overhead).",
                "Write, read, and reconstruction timings are averaged across iterations on "
                "temporary PostgreSQL tables that are rolled back after benchmarking.",
                "Delta reconstruction replays schema and row diffs from the base snapshot and "
                "verifies SHA-256 hash equivalence against the original snapshots.",
            ],
        }
    finally:
        connection.rollback()
        cursor.close()
        connection.close()


def benchmark_commits(commit_ids: list[int], iterations: int = 1) -> dict[str, Any]:
    if not commit_ids:
        raise ValueError("Provide at least one commit ID to benchmark")
    if len(commit_ids) > 100:
        raise ValueError("Benchmark at most 100 commits per request")
    if any(type(commit_id) is not int or commit_id < 1 for commit_id in commit_ids):
        raise ValueError("Commit IDs must be positive integers")
    with get_db_cursor() as cursor:
        cursor.execute(
            "SELECT commit_id, state_id FROM datagit_commits WHERE commit_id = ANY(%s);",
            (commit_ids,),
        )
        states = {row["commit_id"]: row["state_id"] for row in cursor.fetchall()}
    missing = set(commit_ids) - states.keys()
    if missing:
        raise ValueError(f"Unknown commit ID(s): {', '.join(map(str, sorted(missing)))}")
    snapshots = [
        load_snapshot_from_storage(states[commit_id])
        for commit_id in commit_ids
    ]
    result = benchmark_snapshots(snapshots, iterations=iterations)
    return {"commit_ids": commit_ids, **result}

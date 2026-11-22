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


def _measure_payload_bytes(cursor, query: str) -> int:
    cursor.execute(query)
    return cursor.fetchone()[0]


def benchmark_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare PostgreSQL JSONB payload sizes and scan/write times for three layouts."""
    if not snapshots:
        raise ValueError("Provide at least one snapshot to benchmark")
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
    for index, snapshot in enumerate(snapshots):
        for table_name, table_data in sorted(snapshot["tables"].items()):
            blob_id = compute_snapshot_hash(table_data)
            blobs.setdefault(blob_id, table_data)
            manifests.append((index, table_name, blob_id))

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

        started = time.perf_counter()
        cursor.executemany(
            "INSERT INTO datagit_eval_snapshots (snapshot_index, payload) VALUES (%s, %s);",
            snapshot_records,
        )
        snapshot_write_seconds = time.perf_counter() - started

        started = time.perf_counter()
        cursor.executemany(
            "INSERT INTO datagit_eval_deltas (snapshot_index, payload) VALUES (%s, %s);",
            delta_records,
        )
        delta_write_seconds = time.perf_counter() - started

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
        shared_write_seconds = time.perf_counter() - started

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

        started = time.perf_counter()
        cursor.execute(
            "SELECT snapshot_index, payload FROM datagit_eval_snapshots "
            "ORDER BY snapshot_index;"
        )
        cursor.fetchall()
        snapshot_read_seconds = time.perf_counter() - started

        started = time.perf_counter()
        cursor.execute(
            "SELECT snapshot_index, payload FROM datagit_eval_deltas "
            "ORDER BY snapshot_index;"
        )
        cursor.fetchall()
        delta_read_seconds = time.perf_counter() - started

        started = time.perf_counter()
        cursor.execute("""
            SELECT m.snapshot_index, m.table_name, b.payload
            FROM datagit_eval_manifests m
            JOIN datagit_eval_blobs b ON b.blob_id = m.blob_id
            ORDER BY m.snapshot_index, m.table_name;
        """)
        cursor.fetchall()
        shared_read_seconds = time.perf_counter() - started

        return {
            "snapshot_count": len(snapshots),
            "shared_blob_count": len(blobs),
            "measurements": {
                "full_snapshot": {
                    "payload_bytes": snapshot_bytes,
                    "write_seconds": snapshot_write_seconds,
                    "read_seconds": snapshot_read_seconds,
                    "records": len(snapshot_records),
                },
                "delta": {
                    "payload_bytes": delta_bytes,
                    "write_seconds": delta_write_seconds,
                    "read_seconds": delta_read_seconds,
                    "records": len(delta_records),
                },
                "shared_tables": {
                    "payload_bytes": shared_bytes,
                    "write_seconds": shared_write_seconds,
                    "read_seconds": shared_read_seconds,
                    "records": len(blobs) + len(manifests),
                },
            },
            "measurement_notes": [
                "Sizes use PostgreSQL pg_column_size for JSONB payloads and shared manifests; "
                "they exclude relation and index overhead.",
                "Times are single-run write/scan measurements on temporary tables and are "
                "intended for relative experiments, not production capacity estimates.",
                "The delta representation stores a full base followed by row and schema changes.",
            ],
        }
    finally:
        connection.rollback()
        cursor.close()
        connection.close()


def benchmark_commits(commit_ids: list[int]) -> dict[str, Any]:
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
    result = benchmark_snapshots(snapshots)
    return {"commit_ids": commit_ids, **result}

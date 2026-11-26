import os
import json
import re
import tempfile

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.datagit_storage"))
_STATE_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_INTERNAL_TABLES = {
    "datagit_states",
    "datagit_commits",
    "datagit_branches",
    "datagit_workspace",
    "datagit_commit_parents",
    "datagit_merge_events",
    "datagit_tracking_meta",
}

def init_storage():
    """Ensure local object storage directory exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)

def save_snapshot_to_storage(state_id: str, snapshot_data: dict) -> str:
    """Saves snapshot content to a JSON file mapped by its state_id/hash."""
    if not _STATE_ID_PATTERN.fullmatch(state_id):
        raise ValueError("Snapshot state ID must be a SHA-256 hex digest")
    init_storage()
    file_path = os.path.join(STORAGE_DIR, f"{state_id}.json")
    file_descriptor, temporary_path = tempfile.mkstemp(dir=STORAGE_DIR, suffix=".tmp")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as snapshot_file:
            json.dump(snapshot_data, snapshot_file, indent=2, default=str)
            snapshot_file.flush()
            os.fsync(snapshot_file.fileno())
        os.replace(temporary_path, file_path)
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise
    return file_path

def load_snapshot_from_storage(state_id: str) -> dict:
    """Loads a snapshot JSON file given its state_id."""
    if not _STATE_ID_PATTERN.fullmatch(state_id):
        raise ValueError("Snapshot state ID must be a SHA-256 hex digest")
    file_path = os.path.join(STORAGE_DIR, f"{state_id}.json")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Snapshot state ID {state_id} not found in storage.")
    with open(file_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    from dagit.versioning.snapshot import compute_snapshot_hash

    if compute_snapshot_hash(snapshot) != state_id:
        raise ValueError(f"Snapshot state ID {state_id} failed its content hash check")
    tables = snapshot.get("tables")
    if isinstance(tables, dict):
        for table_name in _INTERNAL_TABLES:
            tables.pop(table_name, None)
    return snapshot
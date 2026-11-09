import os
import json

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.datagit_storage"))

def init_storage():
    """Ensure local object storage directory exists."""
    os.makedirs(STORAGE_DIR, exist_ok=True)

def save_snapshot_to_storage(state_id: str, snapshot_data: dict) -> str:
    """Saves snapshot content to a JSON file mapped by its state_id/hash."""
    init_storage()
    file_path = os.path.join(STORAGE_DIR, f"{state_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, default=str)
    return file_path

def load_snapshot_from_storage(state_id: str) -> dict:
    """Loads a snapshot JSON file given its state_id."""
    file_path = os.path.join(STORAGE_DIR, f"{state_id}.json")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Snapshot state ID {state_id} not found in storage.")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
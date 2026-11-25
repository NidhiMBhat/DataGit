from fastapi.testclient import TestClient

from dagit.api.app import app
from dagit.api.security import DirtyWorkspaceError


client = TestClient(app)


def test_api_exposes_backend_versioning_routes():
    paths = app.openapi()["paths"]

    assert "/api/commits" in paths
    assert "/api/branches" in paths
    assert "/api/history" in paths
    assert "/api/diff/{from_commit_id}/{to_commit_id}" in paths
    assert "/api/merge" in paths
    assert "/api/rollback" in paths
    assert "/api/storage/benchmark" in paths


def test_api_enforces_api_keys_and_role_permissions(monkeypatch):
    monkeypatch.setenv("DATAGIT_API_KEY", "write-secret")
    monkeypatch.setenv("DATAGIT_READ_API_KEY", "read-secret")
    monkeypatch.setattr("dagit.api.routes.list_branches", lambda: [{"name": "main", "is_current": True}])
    monkeypatch.setattr("dagit.api.routes.create_commit", lambda m, a, p=None: 42)

    assert client.get("/api/branches").status_code == 401
    assert client.get("/api/branches", headers={"X-API-Key": "wrong"}).status_code == 401

    read_resp = client.get("/api/branches", headers={"X-API-Key": "read-secret"})
    assert read_resp.status_code == 200
    assert read_resp.json()[0]["name"] == "main"

    bearer_resp = client.get(
        "/api/branches", headers={"Authorization": "Bearer write-secret"}
    )
    assert bearer_resp.status_code == 200

    forbidden = client.post(
        "/api/commits",
        json={"message": "m", "author": "a"},
        headers={"X-API-Key": "read-secret"},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/commits",
        json={"message": "m", "author": "a"},
        headers={"X-API-Key": "write-secret"},
    )
    assert created.status_code == 201
    assert created.json() == {"commit_id": 42}


def test_api_blocks_mutations_in_read_only_mode(monkeypatch):
    monkeypatch.setenv("DATAGIT_READ_ONLY", "true")
    monkeypatch.delenv("DATAGIT_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_READ_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_REQUIRE_AUTH", raising=False)
    monkeypatch.setattr("dagit.api.routes.list_branches", lambda: [])

    assert client.get("/api/branches").status_code == 200
    resp = client.post("/api/commits", json={"message": "m", "author": "a"})
    assert resp.status_code == 403
    assert "read-only" in resp.json()["detail"].lower()


def test_api_maps_dirty_workspace_to_conflict(monkeypatch):
    monkeypatch.delenv("DATAGIT_READ_ONLY", raising=False)
    monkeypatch.delenv("DATAGIT_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_READ_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_REQUIRE_AUTH", raising=False)

    def _raise_dirty(*args, **kwargs):
        raise DirtyWorkspaceError("Working database has uncommitted changes")

    monkeypatch.setattr("dagit.api.routes.checkout_branch", _raise_dirty)
    monkeypatch.setattr("dagit.api.routes.rollback", _raise_dirty)

    checkout_resp = client.post("/api/checkout/branches/main")
    assert checkout_resp.status_code == 409

    rollback_resp = client.post("/api/rollback", json={"commit_id": 1})
    assert rollback_resp.status_code == 409


def test_api_storage_benchmark_validates_and_runs_synthetic_workload(monkeypatch):
    monkeypatch.delenv("DATAGIT_READ_ONLY", raising=False)
    monkeypatch.delenv("DATAGIT_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_READ_API_KEY", raising=False)
    monkeypatch.delenv("DATAGIT_REQUIRE_AUTH", raising=False)

    assert client.post("/api/storage/benchmark", json={}).status_code == 422
    assert client.post(
        "/api/storage/benchmark",
        json={"commit_ids": [1], "synthetic_workload": {"table_count": 2}},
    ).status_code == 422

    monkeypatch.setattr(
        "dagit.api.routes.benchmark_snapshots",
        lambda snapshots, iterations=1: {
            "snapshot_count": len(snapshots),
            "iterations": iterations,
            "measurements": {},
        },
    )
    resp = client.post(
        "/api/storage/benchmark",
        json={
            "iterations": 2,
            "synthetic_workload": {
                "table_count": 2,
                "rows_per_table": 10,
                "snapshot_count": 3,
                "change_ratio": 0.2,
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["snapshot_count"] == 3
    assert resp.json()["iterations"] == 2


def test_frontend_is_served_at_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "DataGit" in response.text
    assert "PostgreSQL Version Control" in response.text
    assert "text/html" in response.headers.get("content-type", "")


def test_frontend_serves_static_assets():
    import re
    root_resp = client.get("/")
    assert root_resp.status_code == 200

    asset_paths = re.findall(r'(?:src|href)="([^"]+)"', root_resp.text)
    js_assets = [p for p in asset_paths if p.endswith(".js")]
    css_assets = [p for p in asset_paths if p.endswith(".css")]

    assert len(js_assets) > 0, "Expected at least one JS bundle linked in index.html"
    for js_path in js_assets:
        resp = client.get(js_path)
        assert resp.status_code == 200
        assert any(
            t in resp.headers.get("content-type", "")
            for t in ["javascript", "application/javascript", "text/javascript"]
        )

    for css_path in css_assets:
        resp = client.get(css_path)
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("content-type", "")



def test_api_cors_headers_are_present():
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    response = client.options("/api/branches", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in {"*", "http://localhost:5173"}


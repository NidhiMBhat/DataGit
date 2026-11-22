from dagit.api.app import app


def test_api_exposes_backend_versioning_routes():
    paths = app.openapi()["paths"]

    assert "/api/commits" in paths
    assert "/api/branches" in paths
    assert "/api/history" in paths
    assert "/api/diff/{from_commit_id}/{to_commit_id}" in paths
    assert "/api/merge" in paths
    assert "/api/rollback" in paths
    assert "/api/storage/benchmark" in paths

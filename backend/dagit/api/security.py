import hmac
import os

from fastapi import HTTPException, Request


_TRUTHY = {"1", "true", "yes", "on"}


class DirtyWorkspaceError(ValueError):
    """Raised when a destructive workspace operation is blocked by uncommitted DB changes."""


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUTHY


def is_read_only_mode() -> bool:
    return _is_truthy(os.getenv("DATAGIT_READ_ONLY"))


def is_dirty_protection_enabled() -> bool:
    return _is_truthy(os.getenv("DATAGIT_PROTECT_UNCOMMITTED"))


def _extract_token(request: Request) -> str | None:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _auth_config() -> tuple[bool, str | None, str | None]:
    write_key = os.getenv("DATAGIT_API_KEY") or None
    read_key = os.getenv("DATAGIT_READ_API_KEY") or None
    require_auth = _is_truthy(os.getenv("DATAGIT_REQUIRE_AUTH")) or bool(write_key or read_key)
    return require_auth, write_key, read_key


def _matches(token: str | None, expected: str | None) -> bool:
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


def verify_read_access(request: Request) -> None:
    """Allow read endpoints when auth is disabled or when a valid read/write API key is supplied."""
    require_auth, write_key, read_key = _auth_config()
    if not require_auth:
        return
    token = _extract_token(request)
    if _matches(token, write_key) or _matches(token, read_key):
        return
    raise HTTPException(status_code=401, detail="Invalid or missing API key")


def verify_write_access(request: Request) -> None:
    """Enforce read-only mode and admin/write API key checks on mutating endpoints."""
    if is_read_only_mode():
        raise HTTPException(status_code=403, detail="DataGit API is in read-only mode")
    require_auth, write_key, read_key = _auth_config()
    if not require_auth:
        return
    token = _extract_token(request)
    if _matches(token, write_key):
        return
    if _matches(token, read_key):
        raise HTTPException(status_code=403, detail="Write access requires an admin API key")
    raise HTTPException(status_code=401, detail="Invalid or missing API key")

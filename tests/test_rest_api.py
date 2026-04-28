"""
Tests for modules/rest_api.py — NetSentinel local REST API.
"""
from __future__ import annotations

import json
import time
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeStore:
    """Minimal MetricStore stub for REST API tests."""

    def _execute_read(self, sql: str, params: tuple = ()):
        return []

    def get_recent_alerts(self, hours: float = 24.0, limit: int = 200):
        return []

    def query_speed_test_history(self, hours: float = 168.0, limit: int = 200):
        return []


# ── Import guards ─────────────────────────────────────────────────────────────

def test_module_imports_without_flask(monkeypatch):
    """rest_api must import cleanly even when Flask is not installed."""
    import importlib, sys
    # Stash and restore both flask and modules.rest_api to avoid poisoning
    # subsequent tests in the same process.
    orig_flask     = sys.modules.get("flask",        ...)
    orig_rest_api  = sys.modules.get("modules.rest_api", ...)

    try:
        # Hide flask so the module re-imports with FLASK_AVAILABLE=False
        sys.modules["flask"] = None  # type: ignore
        if "modules.rest_api" in sys.modules:
            del sys.modules["modules.rest_api"]
        import modules.rest_api as m
        assert m.FLASK_AVAILABLE is False
    finally:
        # Full cleanup — remove the tainted module and restore originals
        sys.modules.pop("modules.rest_api", None)
        if orig_flask is ...:
            sys.modules.pop("flask", None)
        else:
            sys.modules["flask"] = orig_flask  # type: ignore
        if orig_rest_api is not ...:
            sys.modules["modules.rest_api"] = orig_rest_api  # type: ignore


def test_flask_available_flag():
    """FLASK_AVAILABLE reflects whether flask can be imported."""
    from modules.rest_api import FLASK_AVAILABLE
    try:
        import flask  # noqa: F401
        assert FLASK_AVAILABLE is True
    except ImportError:
        assert FLASK_AVAILABLE is False


# ── API key helpers ───────────────────────────────────────────────────────────

def test_get_or_create_api_key_returns_string(monkeypatch):
    """get_or_create_api_key always returns a non-empty string."""
    # Monkeypatch keyring to avoid touching the real OS keychain in CI
    import modules.rest_api as m

    monkeypatch.setattr(m, "_KEYRING_OK", True)
    calls = {}

    def _get(service, key):
        return calls.get(key)

    def _set(service, key, val):
        calls[key] = val

    monkeypatch.setattr(m._keyring, "get_password", _get, raising=False)
    monkeypatch.setattr(m._keyring, "set_password", _set, raising=False)

    key = m.get_or_create_api_key()
    assert isinstance(key, str) and len(key) == 64  # 32 bytes hex = 64 chars


def test_get_or_create_api_key_stable(monkeypatch):
    """Second call returns the same key without regenerating."""
    import modules.rest_api as m

    stored = {}
    monkeypatch.setattr(m, "_KEYRING_OK", True)
    monkeypatch.setattr(m._keyring, "get_password", lambda s, k: stored.get(k), raising=False)
    monkeypatch.setattr(m._keyring, "set_password", lambda s, k, v: stored.update({k: v}), raising=False)

    k1 = m.get_or_create_api_key()
    k2 = m.get_or_create_api_key()
    assert k1 == k2


def test_regenerate_api_key_changes_key(monkeypatch):
    """regenerate_api_key produces a different key each time."""
    import modules.rest_api as m

    stored = {}
    monkeypatch.setattr(m, "_KEYRING_OK", True)
    monkeypatch.setattr(m._keyring, "get_password", lambda s, k: stored.get(k), raising=False)
    monkeypatch.setattr(m._keyring, "set_password", lambda s, k, v: stored.update({k: v}), raising=False)

    k1 = m.get_or_create_api_key()
    k2 = m.regenerate_api_key()
    assert k1 != k2


def test_get_stored_api_key_empty_when_keyring_unavailable(monkeypatch):
    import modules.rest_api as m
    monkeypatch.setattr(m, "_KEYRING_OK", False)
    assert m.get_stored_api_key() == ""


# ── Flask app tests ───────────────────────────────────────────────────────────

pytest.importorskip("flask", reason="Flask not installed — skipping Flask endpoint tests")


@pytest.fixture()
def api_client(monkeypatch):
    """Return a Flask test client with a known API key injected."""
    import modules.rest_api as m

    _key = "testkey" + "a" * 57  # 64 char key

    monkeypatch.setattr(m, "_KEYRING_OK", True)
    monkeypatch.setattr(m, "get_stored_api_key", lambda: _key)

    store = _FakeStore()
    app = m.create_app(store)
    app.config["TESTING"] = True

    with app.test_client() as client:
        client._api_key = _key  # type: ignore[attr-defined]
        yield client


def test_health_no_auth(api_client):
    """/health is accessible without an API key."""
    resp = api_client.get("/health")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["status"] == "ok"
    assert "uptime_s" in data


def test_devices_requires_auth(api_client):
    """/devices rejects requests with no key."""
    resp = api_client.get("/devices")
    assert resp.status_code == 401


def test_devices_with_valid_key(api_client):
    """/devices returns 200 with valid X-API-Key header."""
    resp = api_client.get("/devices", headers={"X-API-Key": api_client._api_key})
    assert resp.status_code == 200
    assert json.loads(resp.data) == []


def test_devices_with_query_param(api_client):
    """/devices also accepts api_key query parameter."""
    resp = api_client.get(f"/devices?api_key={api_client._api_key}")
    assert resp.status_code == 200


def test_alerts_returns_list(api_client):
    """/alerts returns a list."""
    resp = api_client.get("/alerts", headers={"X-API-Key": api_client._api_key})
    assert resp.status_code == 200
    assert isinstance(json.loads(resp.data), list)


def test_uptime_not_found(api_client):
    """/uptime/<ip> returns 404 when no data exists for that host."""
    resp = api_client.get("/uptime/10.0.0.1", headers={"X-API-Key": api_client._api_key})
    assert resp.status_code == 404


def test_speed_history_returns_list(api_client):
    """/speed-history returns a list."""
    resp = api_client.get("/speed-history", headers={"X-API-Key": api_client._api_key})
    assert resp.status_code == 200
    assert isinstance(json.loads(resp.data), list)


def test_invalid_key_rejected(api_client):
    """A wrong API key is rejected with 401."""
    resp = api_client.get("/devices", headers={"X-API-Key": "wrongkey"})
    assert resp.status_code == 401


def test_unknown_route_returns_json_404(api_client):
    """/nonexistent returns JSON 404."""
    resp = api_client.get("/nonexistent", headers={"X-API-Key": api_client._api_key})
    assert resp.status_code == 404
    data = json.loads(resp.data)
    assert "error" in data

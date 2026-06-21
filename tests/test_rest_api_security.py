"""
Security tests for modules/rest_api.py.

Tests authentication enforcement, CORS gating, and malformed-parameter
handling without starting a real HTTP server — uses Flask's test client.
"""
from __future__ import annotations

import pytest

try:
    from modules.rest_api import FLASK_AVAILABLE, create_app
except ImportError:
    FLASK_AVAILABLE = False

if not FLASK_AVAILABLE:
    pytest.skip("Flask not installed — REST API security tests skipped",
                allow_module_level=True)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def app_with_key(tmp_path, monkeypatch):
    """Flask test client with a known API key and in-memory store."""
    from modules.metric_store import MetricStore
    from modules import rest_api as _api_mod

    store = MetricStore(str(tmp_path / "sec_test.db"))
    _VALID_KEY = "test-key-0123456789abcdef"
    monkeypatch.setattr(_api_mod, "get_stored_api_key", lambda: _VALID_KEY)

    app = create_app(store)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, _VALID_KEY


@pytest.fixture()
def app_no_key(tmp_path, monkeypatch):
    """Flask test client where no API key has been configured yet."""
    from modules.metric_store import MetricStore
    from modules import rest_api as _api_mod

    store = MetricStore(str(tmp_path / "no_key_test.db"))
    monkeypatch.setattr(_api_mod, "get_stored_api_key", lambda: "")

    app = create_app(store)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ── /health is always public ──────────────────────────────────────────────────

def test_health_no_key_required(app_no_key):
    resp = app_no_key.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"


def test_health_with_wrong_key_still_200(app_with_key):
    client, _ = app_with_key
    resp = client.get("/health", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 200


# ── Missing API key → 503 (key not configured) ───────────────────────────────

def test_missing_api_key_configured_returns_503(app_no_key):
    """When no API key is stored, protected endpoints must return 503."""
    resp = app_no_key.get("/devices")
    assert resp.status_code == 503
    data = resp.get_json()
    assert "error" in data


def test_missing_api_key_configured_on_alerts(app_no_key):
    resp = app_no_key.get("/alerts")
    assert resp.status_code == 503


# ── Wrong API key → 401 ───────────────────────────────────────────────────────

def test_invalid_api_key_returns_401(app_with_key):
    """Providing a wrong key must return 401."""
    client, _ = app_with_key
    resp = client.get("/devices", headers={"X-API-Key": "completely-wrong-key"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert "error" in data


def test_empty_api_key_header_returns_401(app_with_key):
    """Sending the header with an empty value must return 401."""
    client, _ = app_with_key
    resp = client.get("/devices", headers={"X-API-Key": ""})
    assert resp.status_code == 401


def test_no_api_key_header_returns_401(app_with_key):
    """Omitting the X-API-Key header entirely must return 401."""
    client, _ = app_with_key
    resp = client.get("/devices")
    assert resp.status_code == 401


# ── Correct API key → 200 ────────────────────────────────────────────────────

def test_valid_key_devices_returns_200(app_with_key):
    client, key = app_with_key
    resp = client.get("/devices", headers={"X-API-Key": key})
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_valid_key_alerts_returns_200(app_with_key):
    client, key = app_with_key
    resp = client.get("/alerts", headers={"X-API-Key": key})
    assert resp.status_code == 200


def test_valid_key_grade_returns_200(app_with_key):
    client, key = app_with_key
    resp = client.get("/grade", headers={"X-API-Key": key})
    assert resp.status_code in (200, 404)   # 404 if no grade stored yet


# ── Malformed query parameters → graceful 400, not 500 ───────────────────────

def test_malformed_hours_on_alerts(app_with_key):
    """?hours=abc must return 400 with an error message, not raise an exception."""
    client, key = app_with_key
    resp = client.get("/alerts?hours=abc", headers={"X-API-Key": key})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert resp.status_code != 500


def test_malformed_hours_on_uptime(app_with_key):
    """?hours=notanumber on /uptime must return 400, not 500."""
    client, key = app_with_key
    resp = client.get("/uptime/192.168.1.1?hours=notanumber",
                      headers={"X-API-Key": key})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_valid_hours_float_on_alerts(app_with_key):
    """?hours=1.5 is valid and must not raise an error."""
    client, key = app_with_key
    resp = client.get("/alerts?hours=1.5", headers={"X-API-Key": key})
    assert resp.status_code == 200


# ── CORS header present only for localhost origins ────────────────────────────

def test_cors_present_for_localhost_origin(app_with_key):
    """ACAO header must be set when Origin is localhost."""
    client, key = app_with_key
    resp = client.get(
        "/devices",
        headers={"X-API-Key": key, "Origin": "http://localhost:3000"},
    )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" in resp.headers
    assert resp.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_cors_present_for_127_origin(app_with_key):
    """ACAO header must be set when Origin is 127.0.0.1."""
    client, key = app_with_key
    resp = client.get(
        "/devices",
        headers={"X-API-Key": key, "Origin": "http://127.0.0.1:8080"},
    )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" in resp.headers


def test_cors_absent_for_external_origin(app_with_key):
    """ACAO header must NOT be set for non-localhost origins."""
    client, key = app_with_key
    resp = client.get(
        "/devices",
        headers={"X-API-Key": key, "Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 200
    assert "Access-Control-Allow-Origin" not in resp.headers

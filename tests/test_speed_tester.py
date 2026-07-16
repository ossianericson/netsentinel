"""Tests for modules/speed_tester.py — SpeedTestResult dataclass and helpers."""
from __future__ import annotations

import importlib
import sys

import pytest


def test_import():
    from modules import speed_tester  # noqa: F401


def test_speed_test_result_dataclass():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=100.5,
        upload_mbps=50.2,
        ping_ms=12.3,
        server_name="NYC Server",
        server_city="New York",
        server_country="US",
        backend="ookla",
        timestamp="2026-01-01T12:00:00",
        modem_signal=None,
    )
    assert r.download_mbps == pytest.approx(100.5)
    assert r.upload_mbps == pytest.approx(50.2)
    assert r.ping_ms == pytest.approx(12.3)
    assert r.backend == "ookla"
    assert r.modem_signal is None


def test_speed_test_result_minimal():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=0.0, upload_mbps=0.0, ping_ms=0.0,
        server_name="", server_city="", server_country="",
        backend="pure_python", timestamp="", modem_signal=None,
    )
    assert r.backend == "pure_python"


def test_speed_to_fraction_zero():
    from modules.speed_tester import speed_to_fraction
    assert speed_to_fraction(0.0, 1000.0) == pytest.approx(0.0)


def test_speed_to_fraction_full():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(1000.0, 1000.0)
    assert result <= 1.0


def test_speed_to_fraction_clamps():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(2000.0, 1000.0)
    assert result <= 1.0


def test_speed_to_fraction_mid():
    from modules.speed_tester import speed_to_fraction
    result = speed_to_fraction(500.0, 1000.0)
    assert 0.0 < result <= 1.0


def test_speed_server_dataclass():
    from modules.speed_tester import SpeedServer
    s = SpeedServer(id="12345", name="NYC Server",
                    city="New York", country="US",
                    host="speedtest.example.com", latency_ms=5.0)
    assert s.id == "12345"
    assert s.country == "US"
    assert s.latency_ms == pytest.approx(5.0)


def test_find_ookla_cli_returns_path_or_none():
    """_find_ookla_cli() must return a Path or None, never raise."""
    from modules.speed_tester import _find_ookla_cli
    result = _find_ookla_cli()
    assert result is None or hasattr(result, "__fspath__")


# ── Regression: server-list fetch must retry on transient failure (RULE-T3) ────

def test_fetch_servers_retries_on_transient_failure(monkeypatch):
    """A single transient failure must not raise — fetch_servers() should retry
    and succeed once the underlying fetch recovers."""
    st = importlib.import_module("modules.speed_tester")
    from modules.speed_tester_backends import SpeedServer

    # Force ImportError on `import speedtest` so the cascade exercises only
    # the pure-Python fallback (avoids any real network call in this test).
    monkeypatch.setitem(sys.modules, "speedtest", None)
    monkeypatch.setattr(st.time, "sleep", lambda _s: None)  # skip real backoff delay

    calls = {"n": 0}

    def _flaky(limit, on_status=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated network blip")
        return [SpeedServer(id="1", name="Test", city="X", country="US",
                            host="h:8080", latency_ms=5.0)]

    monkeypatch.setattr(st, "_fetch_servers_python", _flaky)

    statuses = []
    servers = st.fetch_servers(limit=3, on_status=statuses.append)

    assert calls["n"] == 2
    assert len(servers) == 1
    assert servers[0].id == "1"
    assert any("retry" in s.lower() for s in statuses)


def test_fetch_servers_falls_back_to_cache_when_all_attempts_fail(monkeypatch, tmp_path):
    """If every retry fails, fetch_servers() must return the last cached list
    rather than raising, when a cache exists."""
    st = importlib.import_module("modules.speed_tester")
    sts = importlib.import_module("modules.speed_tester_servers")
    from modules.speed_tester_backends import SpeedServer

    monkeypatch.setitem(sys.modules, "speedtest", None)
    monkeypatch.setattr(sts, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(st.time, "sleep", lambda _s: None)

    cached = [SpeedServer(id="9", name="Cached", city="C", country="US",
                          host="h:8080", latency_ms=1.0)]
    sts._save_servers_cache(cached)

    def _always_fail(limit, on_status=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(st, "_fetch_servers_python", _always_fail)

    servers = st.fetch_servers(limit=3)
    assert len(servers) == 1
    assert servers[0].id == "9"


def test_fetch_servers_raises_after_exhausting_retries_with_no_cache(monkeypatch, tmp_path):
    """No cache and every attempt fails → RuntimeError, not a silent empty list."""
    st = importlib.import_module("modules.speed_tester")
    sts = importlib.import_module("modules.speed_tester_servers")

    monkeypatch.setitem(sys.modules, "speedtest", None)
    monkeypatch.setattr(sts, "get_app_data_dir", lambda: tmp_path)  # empty dir — no cache
    monkeypatch.setattr(st.time, "sleep", lambda _s: None)

    def _always_fail(limit, on_status=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(st, "_fetch_servers_python", _always_fail)

    with pytest.raises(RuntimeError):
        st.fetch_servers(limit=3)


# ── preferred_location: search-by-name bypass for wrong-country geolocation ─────

def test_fetch_servers_uses_query_when_preferred_location_set(monkeypatch):
    """When preferred_location is given, fetch_servers must use the location-search
    path and must NOT touch the IP-geolocation cascade at all — this is the actual
    fix for the wrong-country candidate list bug (RULE-T3 regression coverage)."""
    st = importlib.import_module("modules.speed_tester")
    from modules.speed_tester_backends import SpeedServer

    calls = {"query": None}

    def _fake_by_query(query, limit=30, on_status=None):
        calls["query"] = query
        return [SpeedServer(id="42", name="Telia", city="Stockholm",
                            country="Sweden", host="h:8080", latency_ms=5.0)]

    def _fail_if_called(*_a, **_kw):
        raise AssertionError("geo-guess cascade must not run when preferred_location is set")

    monkeypatch.setattr(st, "_fetch_servers_by_query", _fake_by_query)
    monkeypatch.setattr(st, "_fetch_servers_python", _fail_if_called)

    servers = st.fetch_servers(limit=10, preferred_location="Stockholm, Sweden")

    assert calls["query"] == "Stockholm, Sweden"
    assert len(servers) == 1
    assert servers[0].country == "Sweden"


def test_fetch_servers_default_behavior_unchanged_without_preferred_location(monkeypatch):
    """Absent preferred_location must be byte-for-byte today's behavior — no regression
    for users unaffected by the geolocation bug."""
    st = importlib.import_module("modules.speed_tester")
    from modules.speed_tester_backends import SpeedServer

    monkeypatch.setitem(sys.modules, "speedtest", None)  # force pure-python path

    def _fake_python(limit, on_status=None):
        return [SpeedServer(id="1", name="X", city="Y", country="Z",
                            host="h:8080", latency_ms=1.0)]

    monkeypatch.setattr(st, "_fetch_servers_python", _fake_python)

    servers = st.fetch_servers(limit=5)
    assert len(servers) == 1
    assert servers[0].id == "1"


def test_resolve_server_id_prefers_pinned_id(monkeypatch):
    """An explicit pinned server ID wins outright — no network call needed."""
    st = importlib.import_module("modules.speed_tester")

    def _fail(*_a, **_kw):
        raise AssertionError("must not fetch servers when a pinned id is already given")

    monkeypatch.setattr(st, "fetch_servers", _fail)
    assert st.resolve_server_id(preferred_server_id="123", preferred_location="Sweden") == "123"


def test_resolve_server_id_falls_back_to_location_search(monkeypatch):
    """No pinned id, but a saved location → resolve to the fastest search result."""
    st = importlib.import_module("modules.speed_tester")
    from modules.speed_tester_backends import SpeedServer

    monkeypatch.setattr(
        st, "fetch_servers",
        lambda limit=10, preferred_location=None: [
            SpeedServer(id="99", name="A", city="B", country="Sweden",
                        host="h:8080", latency_ms=1.0)
        ],
    )
    assert st.resolve_server_id(preferred_server_id=None, preferred_location="Sweden") == "99"


def test_resolve_server_id_returns_none_when_neither_set():
    st = importlib.import_module("modules.speed_tester")
    assert st.resolve_server_id(None, None) is None


def test_resolve_server_id_location_search_failure_returns_none(monkeypatch):
    """A failed location search must degrade to None (today's fully-automatic
    behavior), never raise, so a scheduled background test isn't broken by it."""
    st = importlib.import_module("modules.speed_tester")

    def _fail(*_a, **_kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(st, "fetch_servers", _fail)
    assert st.resolve_server_id(None, "Sweden") is None

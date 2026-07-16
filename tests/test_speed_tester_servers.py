"""Tests for modules/speed_tester_servers.py (S20-7b split)."""
import importlib
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse, parse_qs

import pytest


def test_import():
    mod = importlib.import_module("modules.speed_tester_servers")
    assert hasattr(mod, "_fetch_client_coords")
    assert hasattr(mod, "_fetch_servers_python")
    assert hasattr(mod, "_geolite2_coords")
    assert hasattr(mod, "_fetch_servers_by_query")
    assert hasattr(mod, "_probe_and_rank")


def test_geolite2_coords_no_db():
    """Returns (None, None) when GeoLocator.is_available is False."""
    from modules import speed_tester_servers as m

    mock_locator = MagicMock()
    mock_locator.is_available = False
    with patch("modules.geo_locator.get_locator", return_value=mock_locator):
        assert m._geolite2_coords("8.8.8.8") == (None, None)


def test_geolite2_coords_empty_ip():
    """Empty string returns (None, None) without touching the db."""
    from modules import speed_tester_servers as m

    assert m._geolite2_coords("") == (None, None)


def test_geolite2_coords_with_db():
    """Returns string lat/lon when the db lookup succeeds."""
    from modules import speed_tester_servers as m

    fake_result = MagicMock()
    fake_result.latitude = 59.33
    fake_result.longitude = 18.07
    fake_result.is_bogon = False

    mock_locator = MagicMock()
    mock_locator.is_available = True
    mock_locator.lookup.return_value = fake_result

    with patch("modules.geo_locator.get_locator", return_value=mock_locator):
        lat, lon = m._geolite2_coords("1.2.3.4")
    assert lat == "59.33"
    assert lon == "18.07"


def test_fetch_client_coords_cache(monkeypatch):
    """After a successful lookup the result is cached; subsequent calls skip network."""
    import modules.speed_tester_servers as m

    # Reset cache for this test
    monkeypatch.setattr(m, "_coords_cache", (None, None))

    call_count = [0]

    def _fake_http_get(url, timeout=10):
        call_count[0] += 1
        # Minimal speedtest.net XML stub
        return (
            b'<?xml version="1.0" ?><settings>'
            b'<client ip="1.2.3.4" lat="59.33" lon="18.07" isp="Test ISP"/>'
            b'</settings>'
        )

    monkeypatch.setattr(m, "_http_get", _fake_http_get)

    # GeoLite2 not available
    mock_locator = MagicMock()
    mock_locator.is_available = False
    with patch("modules.geo_locator.get_locator", return_value=mock_locator):
        coords1 = m._fetch_client_coords()
        coords2 = m._fetch_client_coords()  # should hit cache

    assert coords1 == ("59.33", "18.07")
    assert coords2 == ("59.33", "18.07")
    assert call_count[0] == 1  # network called exactly once


def test_fetch_client_coords_geolite2_preferred(monkeypatch):
    """GeoLite2 result is returned in preference to speedtest.net lat/lon."""
    import modules.speed_tester_servers as m

    monkeypatch.setattr(m, "_coords_cache", (None, None))

    def _fake_http_get(url, timeout=10):
        return (
            b'<?xml version="1.0" ?><settings>'
            b'<client ip="1.2.3.4" lat="0.00" lon="0.00" isp="Test ISP"/>'
            b'</settings>'
        )

    monkeypatch.setattr(m, "_http_get", _fake_http_get)

    fake_result = MagicMock()
    fake_result.latitude = 59.33
    fake_result.longitude = 18.07
    fake_result.is_bogon = False

    mock_locator = MagicMock()
    mock_locator.is_available = True
    mock_locator.lookup.return_value = fake_result

    with patch("modules.geo_locator.get_locator", return_value=mock_locator):
        coords = m._fetch_client_coords()

    assert coords == ("59.33", "18.07")


def test_fetch_servers_python_calls_on_status(monkeypatch):
    """on_status callback is invoked at least once during fetch."""
    import modules.speed_tester_servers as m

    monkeypatch.setattr(m, "_coords_cache", (None, None))

    # Stub coords fetch
    monkeypatch.setattr(m, "_fetch_client_coords", lambda: ("59.33", "18.07"))

    # Stub server list response
    import json

    def _fake_http_get(url, timeout=10):
        servers = [
            {"id": "1", "sponsor": "Test", "name": "Stockholm",
             "country": "SE", "host": "test.example.com:8080"}
        ]
        return json.dumps(servers).encode()

    monkeypatch.setattr(m, "_http_get", _fake_http_get)

    messages = []
    m._fetch_servers_python(limit=1, on_status=messages.append)

    assert any("location" in msg.lower() or "server" in msg.lower() for msg in messages)


# ── Last-good server list cache (RULE 23 app-data storage) ─────────────────────

def test_servers_cache_round_trip(tmp_path, monkeypatch):
    import modules.speed_tester_servers as m
    from modules.speed_tester_backends import SpeedServer

    monkeypatch.setattr(m, "get_app_data_dir", lambda: tmp_path)

    servers = [SpeedServer(id="1", name="A", city="B", country="US",
                           host="h:8080", latency_ms=3.0)]
    m._save_servers_cache(servers)

    loaded = m._load_servers_cache()
    assert len(loaded) == 1
    assert loaded[0].id == "1"
    assert loaded[0].name == "A"


def test_servers_cache_missing_returns_empty(tmp_path, monkeypatch):
    import modules.speed_tester_servers as m

    monkeypatch.setattr(m, "get_app_data_dir", lambda: tmp_path)
    assert m._load_servers_cache() == []


def test_servers_cache_corrupt_returns_empty(tmp_path, monkeypatch):
    import modules.speed_tester_servers as m

    monkeypatch.setattr(m, "get_app_data_dir", lambda: tmp_path)
    (tmp_path / "speedtest_servers_cache.json").write_text("not valid json", encoding="utf-8")
    assert m._load_servers_cache() == []


# ── Location search (bypasses IP geolocation entirely) ─────────────────────────

def test_probe_and_rank_sorts_by_measured_latency(monkeypatch):
    """_probe_and_rank must probe each server and return them sorted fastest-first."""
    import modules.speed_tester_servers as m
    from modules.speed_tester_backends import SpeedServer

    servers = [
        SpeedServer(id="1", name="Slow", city="A", country="X", host="slow.example:8080", latency_ms=0.0),
        SpeedServer(id="2", name="Fast", city="B", country="Y", host="fast.example:8080", latency_ms=0.0),
    ]

    def _fake_tcp_probe(hostname, port, timeout=2):
        rtt = 5.0 if hostname == "fast.example" else 50.0
        return True, rtt, None

    monkeypatch.setattr(m, "tcp_probe", _fake_tcp_probe)

    ranked = m._probe_and_rank(servers)

    assert [s.id for s in ranked] == ["2", "1"]
    assert ranked[0].latency_ms == pytest.approx(5.0)


def test_probe_and_rank_calls_on_status(monkeypatch):
    import modules.speed_tester_servers as m
    from modules.speed_tester_backends import SpeedServer

    monkeypatch.setattr(m, "tcp_probe", lambda hostname, port, timeout=2: (True, 10.0, None))

    messages = []
    m._probe_and_rank(
        [SpeedServer(id="1", name="A", city="B", country="X", host="h:8080", latency_ms=0.0)],
        on_status=messages.append,
    )
    assert any("latency" in msg.lower() for msg in messages)


def test_fetch_servers_by_query_uses_search_param_not_coordinates(monkeypatch):
    """The location-search fetch must never touch lat/lon or client coordinate lookup —
    it sidesteps IP geolocation entirely (RULE-T3 regression coverage for the wrong-country
    server-list bug)."""
    import json
    import modules.speed_tester_servers as m

    captured_urls = []

    def _fake_http_get(url, timeout=10):
        captured_urls.append(url)
        servers = [
            {"id": "42", "sponsor": "Telia", "name": "Stockholm",
             "country": "Sweden", "host": "stockholm.example.com:8080"},
        ]
        return json.dumps(servers).encode()

    monkeypatch.setattr(m, "_http_get", _fake_http_get)
    monkeypatch.setattr(m, "_probe_and_rank", lambda servers, on_status=None: servers)

    def _fail_if_called():
        raise AssertionError("_fetch_servers_by_query must not call _fetch_client_coords")

    monkeypatch.setattr(m, "_fetch_client_coords", _fail_if_called)

    result = m._fetch_servers_by_query("Stockholm, Sweden", limit=30)

    assert len(captured_urls) == 1
    parsed = urlparse(captured_urls[0])
    qs = parse_qs(parsed.query)
    assert qs.get("search") == ["Stockholm, Sweden"]
    assert "lat" not in qs
    assert "lon" not in qs
    assert parsed.hostname == "www.speedtest.net"

    assert len(result) == 1
    assert result[0].id == "42"
    assert result[0].country == "Sweden"


def test_fetch_servers_by_query_calls_on_status(monkeypatch):
    import json
    import modules.speed_tester_servers as m

    def _fake_http_get(url, timeout=10):
        return json.dumps([
            {"id": "1", "sponsor": "Test", "name": "Stockholm",
             "country": "Sweden", "host": "test.example.com:8080"}
        ]).encode()

    monkeypatch.setattr(m, "_http_get", _fake_http_get)
    monkeypatch.setattr(m, "_probe_and_rank", lambda servers, on_status=None: servers)

    messages = []
    m._fetch_servers_by_query("Sweden", limit=10, on_status=messages.append)
    assert any("server" in msg.lower() for msg in messages)

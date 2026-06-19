"""Tests for modules/speed_tester_servers.py (S20-7b split)."""
import importlib
from unittest.mock import MagicMock, patch


def test_import():
    mod = importlib.import_module("modules.speed_tester_servers")
    assert hasattr(mod, "_fetch_client_coords")
    assert hasattr(mod, "_fetch_servers_python")
    assert hasattr(mod, "_geolite2_coords")


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

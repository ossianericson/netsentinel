"""
Tests for modules/geo_locator.py

Covers:
  - is_bogon: RFC 1918, loopback, CGNAT, link-local, public
  - GeoResult defaults
  - GeoLocator: no-db graceful fallback, lookup returns GeoResult,
    bogon handling, lookup_many, reload, is_available, close
  - _first_en helper
  - download_db_permalink security validation (HTTPS enforcement, host allowlist)
  - _is_gzip helper
  - get_locator singleton
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modules.geo_locator import (
    GeoLocator,
    GeoResult,
    _first_en,
    _is_gzip,
    db_path,
    download_db_permalink,
    get_locator,
    is_bogon,
)


# ── is_bogon ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ip,expected", [
    ("10.0.0.1",       True),
    ("10.255.255.255",  True),
    ("172.16.0.1",     True),
    ("172.31.255.255",  True),
    ("192.168.1.1",    True),
    ("127.0.0.1",      True),
    ("127.0.0.127",    True),
    ("169.254.1.1",    True),
    ("100.64.0.1",     True),   # CGNAT
    ("100.127.255.255", True),  # CGNAT
    ("8.8.8.8",        False),
    ("1.1.1.1",        False),
    ("151.101.0.0",    False),
    ("::1",            True),
])
def test_is_bogon(ip, expected):
    assert is_bogon(ip) is expected


def test_is_bogon_invalid():
    assert is_bogon("not-an-ip") is False


def test_is_bogon_public_ipv6():
    # 2001:db8:: is documentation range, but is_bogon only checks our specific sets
    # so a random public-looking IPv6 should return False
    assert is_bogon("2606:4700:4700::1111") is False


# ── GeoResult defaults ────────────────────────────────────────────────────────

def test_georesult_defaults():
    r = GeoResult(ip="1.2.3.4")
    assert r.country == ""
    assert r.latitude == 0.0
    assert r.longitude == 0.0
    assert r.is_bogon is False


def test_georesult_bogon_flag():
    r = GeoResult(ip="10.0.0.1", is_bogon=True)
    assert r.is_bogon is True


# ── GeoLocator: no .mmdb present ─────────────────────────────────────────────

def test_locator_no_db_is_not_available(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    assert not loc.is_available


def test_locator_no_db_lookup_returns_georesult(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    r = loc.lookup("8.8.8.8")
    assert isinstance(r, GeoResult)
    assert r.ip == "8.8.8.8"
    assert r.country == ""


def test_locator_bogon_returns_bogon_flag(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    r = loc.lookup("192.168.1.1")
    assert r.is_bogon is True
    assert r.ip == "192.168.1.1"


def test_locator_lookup_many(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    results = loc.lookup_many(["8.8.8.8", "1.1.1.1", "192.168.0.1"])
    assert len(results) == 3
    ips = [r.ip for r in results]
    assert "8.8.8.8" in ips
    assert "192.168.0.1" in ips


def test_locator_close_without_db(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    loc.close()   # should not raise


def test_locator_reload_without_db(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    loc.reload()   # should not raise
    assert not loc.is_available


# ── GeoLocator: with a mocked maxminddb.Reader ───────────────────────────────

def _make_mock_db(ip: str = "8.8.8.8") -> MagicMock:
    """Return a mock maxminddb reader that returns one record."""
    record = {
        "country": {"iso_code": "US", "names": {"en": "United States"}},
        "city":    {"names": {"en": "Mountain View"}},
        "location": {"latitude": 37.386, "longitude": -122.083},
    }
    mock = MagicMock()
    mock.get.return_value = record
    return mock


def test_locator_with_mock_db(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    loc._db = _make_mock_db()   # inject mock

    r = loc.lookup("8.8.8.8")
    assert r.country == "US"
    assert r.country_name == "United States"
    assert r.city == "Mountain View"
    assert r.latitude == pytest.approx(37.386)
    assert r.longitude == pytest.approx(-122.083)


def test_locator_mock_db_returns_none(tmp_path):
    """When db.get() returns None, GeoResult should be empty but not raise."""
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    mock = MagicMock()
    mock.get.return_value = None
    loc._db = mock

    r = loc.lookup("8.8.8.8")
    assert r.ip == "8.8.8.8"
    assert r.country == ""


def test_locator_mock_db_raises(tmp_path):
    """When db.get() raises, GeoResult should be empty but not propagate."""
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    mock = MagicMock()
    mock.get.side_effect = RuntimeError("corrupt")
    loc._db = mock

    r = loc.lookup("8.8.8.8")
    assert r.ip == "8.8.8.8"
    assert r.country == ""


def test_locator_close_calls_db_close(tmp_path):
    loc = GeoLocator(mmdb_path=tmp_path / "nonexistent.mmdb")
    mock = MagicMock()
    loc._db = mock
    loc.close()
    mock.close.assert_called_once()
    assert loc._db is None


# ── _first_en ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("names,expected", [
    ({"en": "Germany", "de": "Deutschland"}, "Germany"),
    ({"de": "Deutschland"},                   "Deutschland"),
    ({},                                       ""),
    (None,                                     ""),
])
def test_first_en(names, expected):
    assert _first_en(names or {}) == expected


# ── download_db_permalink security ────────────────────────────────────────────

def test_download_rejects_http():
    with pytest.raises(ValueError, match="HTTPS"):
        download_db_permalink("http://download.maxmind.com/test.mmdb")


def test_download_rejects_untrusted_host():
    with pytest.raises(ValueError, match="Untrusted"):
        download_db_permalink("https://evil.com/GeoLite2-City.mmdb")


def test_download_rejects_maxmind_subdomain_lookalike():
    with pytest.raises(ValueError, match="Untrusted"):
        download_db_permalink("https://notmaxmind.com/GeoLite2-City.mmdb")


def test_download_accepts_maxmind_subdomain():
    """Should not raise on valid host — but we mock urlopen so no real request."""
    # Fake response: minimal gzip with 2-byte magic header so _is_gzip returns True
    gzip_magic = b"\x1f\x8b" + b"\x00" * 100
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.headers = {"Content-Length": "102"}
    mock_resp.read.side_effect = [gzip_magic, b""]

    with patch("modules.geo_locator.urllib.request.urlopen", return_value=mock_resp):
        with patch("modules.geo_locator._is_gzip", return_value=False):
            with patch("modules.geo_locator.Path.replace"):
                # Just ensure no ValueError is raised for a legit URL
                try:
                    download_db_permalink(
                        "https://download.maxmind.com/GeoLite2-City.mmdb",
                        dest=Path("/tmp/test.mmdb"))
                except Exception as exc:
                    # We expect an OSError (mock can't fully write) but NOT ValueError
                    assert not isinstance(exc, ValueError), str(exc)


# ── _is_gzip ──────────────────────────────────────────────────────────────────

def test_is_gzip_true(tmp_path):
    p = tmp_path / "test.gz"
    p.write_bytes(b"\x1f\x8b" + b"\x00" * 20)
    assert _is_gzip(p) is True


def test_is_gzip_false(tmp_path):
    p = tmp_path / "test.mmdb"
    p.write_bytes(b"MMDB" + b"\x00" * 20)
    assert _is_gzip(p) is False


def test_is_gzip_nonexistent(tmp_path):
    assert _is_gzip(tmp_path / "nope.mmdb") is False


# ── get_locator singleton ─────────────────────────────────────────────────────

def test_get_locator_returns_geo_locator():
    loc = get_locator()
    assert isinstance(loc, GeoLocator)


def test_get_locator_same_instance():
    a = get_locator()
    b = get_locator()
    assert a is b


# ── db_path ───────────────────────────────────────────────────────────────────

def test_db_path_ends_with_mmdb():
    p = db_path()
    assert p.name == "GeoLite2-City.mmdb"


# ── P2 regression: GeoMapPage must close/reload locator on hide/show ──────────

def test_geo_locator_close_and_reload_roundtrip():
    """GeoLocator.close() followed by reload() must not raise (P2 regression).

    GeoMapPage.hideEvent() calls get_locator().close() and showEvent() calls
    get_locator().reload().  Exercises that roundtrip with graceful degradation.
    """
    loc = GeoLocator()
    initial_available = loc.is_available

    # close() must set is_available to False regardless of initial state
    loc.close()
    assert loc.is_available is False, "close() must mark locator unavailable"

    # close() again must be idempotent
    loc.close()
    assert loc.is_available is False

    # reload() must not raise, and restores availability to initial state
    loc.reload()
    assert loc.is_available == initial_available

    # lookup() must return a GeoResult regardless of db state
    result = loc.lookup("8.8.8.8")
    assert isinstance(result, GeoResult)
    assert result.ip == "8.8.8.8"


def test_geo_map_page_hides_closes_locator(qt_app, monkeypatch):
    """GeoMapPage.hideEvent() must call get_locator().close() (P2 regression)."""
    import pytest
    if qt_app is None:
        pytest.skip("No QApplication")

    from unittest.mock import MagicMock, patch
    from ui.pages.geo_map_page import GeoMapPage

    mock_locator = MagicMock()
    mock_locator.is_available = False

    close_called: list = []
    reload_called: list = []

    mock_locator.close.side_effect = lambda: close_called.append(1)
    mock_locator.reload.side_effect = lambda: reload_called.append(1)

    # Patch at the import site inside geo_map_page (not in modules.geo_locator)
    with patch("ui.pages.geo_map_page.get_locator", return_value=mock_locator):
        page = GeoMapPage()
        # Invoke event handlers directly — page.hide() is a no-op on a widget that
        # was never shown (Qt only fires hideEvent when transitioning from visible).
        from PyQt6.QtGui import QHideEvent, QShowEvent
        page.hideEvent(QHideEvent())
        assert len(close_called) >= 1, "get_locator().close() not called in hideEvent()"
        page.showEvent(QShowEvent())
        assert len(reload_called) >= 1, "get_locator().reload() not called in showEvent()"

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()

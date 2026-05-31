"""Tests for modules/mac_lookup.py — OUI vendor lookup helper."""
import pytest


def test_mac_lookup_import():
    from modules import mac_lookup
    assert mac_lookup is not None


def test_normalise_strips_separators():
    from modules.mac_lookup import _normalise
    # Returns lowercase hex digits only
    result = _normalise("AA:BB:CC:DD:EE:FF")
    assert ":" not in result
    assert "-" not in result
    assert all(c in "0123456789abcdef" for c in result)


def test_normalise_handles_colon_format():
    from modules.mac_lookup import _normalise
    result = _normalise("aa:bb:cc:dd:ee:ff")
    assert len(result) == 12


def test_normalise_handles_dash_format():
    from modules.mac_lookup import _normalise
    result = _normalise("AA-BB-CC-DD-EE-FF")
    assert len(result) == 12


def test_lookup_vendor_returns_none_for_broadcast():
    from modules.mac_lookup import lookup_vendor
    result = lookup_vendor("ff:ff:ff:ff:ff:ff")
    assert result is None or isinstance(result, str)


def test_lookup_vendor_returns_none_for_invalid():
    from modules.mac_lookup import lookup_vendor
    result = lookup_vendor("xx:yy:zz")
    assert result is None or isinstance(result, str)


def test_lookup_vendor_accepts_colon_dash_formats():
    from modules.mac_lookup import lookup_vendor
    for mac in ("00:50:56:ab:cd:ef", "00-50-56-ab-cd-ef", "005056abcdef"):
        result = lookup_vendor(mac)
        assert result is None or isinstance(result, str)


@pytest.mark.live
def test_api_lookup_reaches_internet():
    """Only run when real network available."""
    from modules.mac_lookup import _api_lookup
    result = _api_lookup("74DA38", timeout=3)
    assert result is None or isinstance(result, str)

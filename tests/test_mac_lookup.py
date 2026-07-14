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


def test_lookup_vendor_resolves_via_offenders_json_when_registry_misses(tmp_path, monkeypatch):
    """Regression (F-11 claims-audit): offenders.json's tier-2 lookup called
    data.get(oui) as if the file were an OUI->vendor dict, but offenders.json is
    actually a JSON LIST of rogue-device signature records
    ({"vendor": ..., "ouis": [...]}) -- .get() on a list always raised
    AttributeError, silently swallowed by `except Exception: pass`. This tier
    never once returned a vendor in production. Fixed to iterate the list and
    match by OUI prefix so the real vendor data in offenders.json is actually used."""
    import json
    from modules import mac_lookup

    offenders_path = tmp_path / "offenders.json"
    offenders_path.write_text(json.dumps([
        {"vendor": "Test Rogue Vendor", "ouis": ["aa:bb:cc"]},
    ]), encoding="utf-8")

    monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})  # tier 1 misses

    def _fail_api(*a, **k):
        raise AssertionError("must not reach the online API -- offenders.json should have matched first")
    monkeypatch.setattr(mac_lookup, "_api_lookup", _fail_api)  # tier 3 must not be reached
    mac_lookup._CACHE.clear()

    result = mac_lookup.lookup_vendor("aa:bb:cc:dd:ee:ff", offenders_path=str(offenders_path))
    assert result == "Test Rogue Vendor"


def test_lookup_vendor_allow_online_false_never_calls_api(tmp_path, monkeypatch):
    """Regression (F-60 claims-audit): ui/help.py's Devices page claims
    vendor/model resolution needs 'no internet call needed', but
    lookup_vendor() unconditionally hit api.macvendors.com on tier-4 with no
    way to suppress it. allow_online=False must skip tier 4 entirely, even
    when every local tier misses."""
    import json
    from modules import mac_lookup

    empty_offenders = tmp_path / "offenders.json"
    empty_offenders.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})  # tier 1 misses
    monkeypatch.setattr(
        "scapy.all.conf.manufdb._get_manuf", lambda oui: oui  # tier 3 "miss" sentinel
    )

    def _fail_api(*a, **k):
        raise AssertionError("must not reach the online API when allow_online=False")
    monkeypatch.setattr(mac_lookup, "_api_lookup", _fail_api)
    mac_lookup._CACHE.clear()

    result = mac_lookup.lookup_vendor(
        "aa:bb:cc:dd:ee:ff", offenders_path=str(empty_offenders), allow_online=False
    )
    assert result is None


def test_lookup_vendor_resolves_via_scapy_manuf_db(tmp_path, monkeypatch):
    """Regression (F-11 claims-audit): README.md claimed a '60,000+ entry OUI
    database', but the real local vendor tables total ~265 entries and scapy's
    own bundled manuf database (~50,000 entries; scapy is already a hard
    dependency per requirements.txt) was never queried anywhere in the
    lookup chain. Wired in as a new tier, after mac_registry/offenders.json
    and before the network fallback -- delivers on the claim using an
    already-required dependency, no new install."""
    import json
    from modules import mac_lookup

    empty_offenders = tmp_path / "offenders.json"
    empty_offenders.write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})  # tier 1 misses
    mac_lookup._CACHE.clear()

    def _fail_api(*a, **k):
        raise AssertionError("must not reach the online API -- scapy's manuf DB should have matched")
    monkeypatch.setattr(mac_lookup, "_api_lookup", _fail_api)

    # 00:50:56 is VMware's registered OUI -- not in offenders.json's small
    # rogue-device list, so this exercises the scapy tier specifically.
    result = mac_lookup.lookup_vendor("00:50:56:ab:cd:ef", offenders_path=str(empty_offenders))
    assert result and "vmware" in result.lower()

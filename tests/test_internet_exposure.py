"""Tests for modules/internet_exposure.py — internet exposure checker."""
from modules.internet_exposure import UPnPMapping, ExposureResult, check_exposure


def test_import():
    from modules import internet_exposure as m
    assert hasattr(m, "check_exposure")
    assert hasattr(m, "UPnPMapping")
    assert hasattr(m, "ExposureResult")


def test_upnp_mapping_fields():
    m = UPnPMapping(
        external_port=8080,
        internal_ip="192.168.1.10",
        internal_port=80,
        protocol="TCP",
        description="HTTP",
    )
    assert m.external_port == 8080
    assert m.internal_ip == "192.168.1.10"
    assert m.protocol == "TCP"
    assert m.enabled is True


def test_exposure_result_defaults():
    r = ExposureResult()
    assert r.wan_ip == ""
    assert r.cgnat is False
    assert r.upnp_available is False
    assert r.upnp_mappings == []


def test_check_exposure_no_network(monkeypatch):
    monkeypatch.setattr("modules.internet_exposure._ssdp_discover", lambda **kw: [])
    monkeypatch.setattr("modules.internet_exposure._get_wan_ip", lambda: (None, False))
    result = check_exposure()
    assert isinstance(result, ExposureResult)
    assert result.upnp_mappings == []


def test_check_exposure_ssdp_timeout(monkeypatch):
    monkeypatch.setattr("modules.internet_exposure._ssdp_discover", lambda **kw: [])
    monkeypatch.setattr("modules.internet_exposure._get_wan_ip", lambda: ("203.0.113.1", False))
    result = check_exposure()
    assert isinstance(result, ExposureResult)
    assert result.wan_ip == "203.0.113.1"


def test_check_exposure_blank_wan_ip_is_not_testable(monkeypatch):
    """A blocked WAN-IP lookup (e.g. VPN blocking the outbound API call) must not
    silently read as a clean 'no exposed services' result — it must be flagged."""
    monkeypatch.setattr("modules.internet_exposure._ssdp_discover", lambda **kw: [])
    monkeypatch.setattr("modules.internet_exposure._get_wan_ip", lambda: ("", False))
    result = check_exposure()
    assert result.not_testable is True
    assert result.not_testable_reason != ""


def test_check_exposure_blank_wan_ip_plain_verdict_is_not_a_clean_bill_of_health(monkeypatch):
    """Regression: plain_verdict used to fall through to the green checkmark
    'no LAN services appear internet-exposed' text when the WAN-IP lookup itself
    failed — a blocked check must not read as a confirmed clean result."""
    monkeypatch.setattr("modules.internet_exposure._ssdp_discover", lambda **kw: [])
    monkeypatch.setattr("modules.internet_exposure._get_wan_ip", lambda: ("", False))
    result = check_exposure()
    assert "no lan services appear internet-exposed" not in result.plain_verdict.lower()
    assert "✅" not in result.plain_verdict


def test_check_exposure_valid_wan_ip_is_still_testable(monkeypatch):
    monkeypatch.setattr("modules.internet_exposure._ssdp_discover", lambda **kw: [])
    monkeypatch.setattr("modules.internet_exposure._get_wan_ip", lambda: ("203.0.113.1", False))
    result = check_exposure()
    assert result.not_testable is False

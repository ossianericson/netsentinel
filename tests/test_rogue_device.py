"""Tests for modules/rogue_device.py — rogue device fingerprinter."""
import json
from modules.rogue_device import DeviceInfo, _get_default_gateway, _get_arp_table, scan


def test_import():
    import modules.rogue_device as m
    assert hasattr(m, "scan")
    assert hasattr(m, "DeviceInfo")
    assert hasattr(m, "_get_arp_table")


def test_device_info_fields():
    d = DeviceInfo(
        ip="192.168.1.1",
        mac="aa:bb:cc:dd:ee:ff",
        vendor="Cisco",
        hostname="router.local",
    )
    assert d.ip == "192.168.1.1"
    assert d.mac == "aa:bb:cc:dd:ee:ff"
    assert d.vendor == "Cisco"


def test_device_info_defaults():
    d = DeviceInfo(ip="10.0.0.1", mac="00:11:22:33:44:55")
    assert d.hostname == ""
    assert d.risk_level == "UNKNOWN"
    assert d.known_issues == []


def test_get_default_gateway_returns_str_or_none():
    gw = _get_default_gateway()
    assert gw is None or isinstance(gw, str)


def test_get_arp_table_returns_list():
    result = _get_arp_table()
    assert isinstance(result, list)


def test_scan_with_offenders_path(tmp_path):
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([{"ouis": [], "vendor": "Test", "known_issues": []}]))
    result = scan(offenders_path=offenders)
    assert isinstance(result, dict)
    assert "devices" in result


def test_scan_returns_known_keys(tmp_path):
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    result = scan(offenders_path=offenders)
    assert "plain_verdict" in result
    assert "total_count" in result


# ── Gateway device-type and hostname sanity tests ────────────────────────────

from modules.rogue_device import _CONSUMER_HOSTNAME_RE


def test_consumer_hostname_re_matches_playstation():
    assert _CONSUMER_HOSTNAME_RE.search("Playstation 4")


def test_consumer_hostname_re_matches_xbox():
    assert _CONSUMER_HOSTNAME_RE.search("Xbox Series X")


def test_consumer_hostname_re_matches_iphone():
    assert _CONSUMER_HOSTNAME_RE.search("iPhone-12")


def test_consumer_hostname_re_no_match_for_deco():
    assert not _CONSUMER_HOSTNAME_RE.search("deco-main")


def test_consumer_hostname_re_no_match_for_generic_router():
    assert not _CONSUMER_HOSTNAME_RE.search("gateway.local")


def test_gateway_device_type_is_router(tmp_path, monkeypatch):
    """Gateway IP must be classified as Router / Gateway regardless of OUI."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip = "192.168.1.1"
    liteon_mac = "5c:93:a2:11:22:33"

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(gw_ip, liteon_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].device_type == "Router / Gateway"


def test_proxy_arp_ip_detected_and_excluded(tmp_path, monkeypatch):
    """IPs that share the gateway MAC (proxy ARP) must be excluded from results."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip  = "192.168.1.1"
    gw_mac = "a8:59:35:11:22:33"
    ps4_ip = "192.168.1.71"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table",
        lambda: [(gw_ip, gw_mac), (ps4_ip, gw_mac)],
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)

    # ps4_ip shares the gateway MAC — must land in proxy_arp_ips
    assert ps4_ip in result["proxy_arp_ips"]
    # Only the gateway itself should appear in devices
    assert result["total_count"] == 1
    ips = [d.ip for d in result["devices"]]
    assert gw_ip in ips
    assert ps4_ip not in ips


def test_proxy_arp_ips_empty_when_no_shared_mac(tmp_path, monkeypatch):
    """proxy_arp_ips must be empty when every IP has a unique MAC."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table",
        lambda: [("192.168.1.1", "aa:bb:cc:00:00:01"), ("192.168.1.2", "aa:bb:cc:00:00:02")],
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    assert result["proxy_arp_ips"] == set()


def test_gateway_consumer_hostname_is_cleared(tmp_path, monkeypatch):
    """Gateway IP with a PS4 hostname must have its hostname cleared."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip = "192.168.1.1"
    liteon_mac = "5c:93:a2:11:22:33"

    from unittest.mock import MagicMock
    fake_name_info = MagicMock()
    fake_name_info.hostname = "Playstation 4"
    fake_name_info.vendor = ""
    fake_name_info.device_type = ""

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(gw_ip, liteon_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda _ips, **_kw: {gw_ip: fake_name_info})
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].hostname == ""
    assert devices[0].device_type == "Router / Gateway"

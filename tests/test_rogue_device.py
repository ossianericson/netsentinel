"""Tests for modules/rogue_device.py — rogue device fingerprinter."""
import json
import pytest
from pathlib import Path
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

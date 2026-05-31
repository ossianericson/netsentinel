"""Tests for modules/arp_monitor.py — ARP spoof/MITM detector."""
import pytest
from modules.arp_monitor import SCAPY_AVAILABLE, SpoofEvent, ARPScanResult, _build_baseline


def test_import():
    import modules.arp_monitor as m
    assert hasattr(m, "SCAPY_AVAILABLE")
    assert hasattr(m, "SpoofEvent")
    assert hasattr(m, "ARPScanResult")
    assert hasattr(m, "ARPSniffer")


def test_scapy_available_is_bool():
    assert isinstance(SCAPY_AVAILABLE, bool)


def test_spoof_event_fields():
    ev = SpoofEvent(
        event_type="ip_takeover",
        attacker_mac="11:22:33:44:55:66",
        attacker_ip="192.168.1.100",
        victim_ip="192.168.1.1",
        original_mac="aa:bb:cc:dd:ee:ff",
    )
    assert ev.event_type == "ip_takeover"
    assert ev.attacker_mac == "11:22:33:44:55:66"
    assert ev.victim_ip == "192.168.1.1"
    assert ev.original_mac == "aa:bb:cc:dd:ee:ff"


def test_arp_scan_result_defaults():
    r = ARPScanResult(events=[], baseline={})
    assert r.events == []
    assert r.total_arp_packets == 0
    assert r.plain_verdict == ""


def test_build_baseline_returns_dict(monkeypatch):
    monkeypatch.setattr(
        "modules.arp_monitor.subprocess.check_output",
        lambda *a, **kw: b"Internet Address  Physical Address\n192.168.1.1  aa-bb-cc-dd-ee-ff",
    )
    result = _build_baseline()
    assert isinstance(result, dict)


def test_build_baseline_graceful_failure(monkeypatch):
    import subprocess
    monkeypatch.setattr(
        "modules.arp_monitor.subprocess.check_output",
        lambda *a, **kw: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "arp")),
    )
    result = _build_baseline()
    assert isinstance(result, dict)

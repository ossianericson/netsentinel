"""Tests for modules/arp_watch.py (V6 Sprint 4.1 — ARP spoof background watch)."""
from __future__ import annotations

from unittest.mock import patch

from modules.arp_monitor import ARPScanResult, SpoofEvent


def test_import():
    from modules.arp_watch import run_arp_watch_cycle, ArpWatchReport
    assert run_arp_watch_cycle is not None
    assert ArpWatchReport is not None


def test_no_events_returns_empty_report():
    from modules.arp_watch import run_arp_watch_cycle

    result = ARPScanResult(events=[], baseline={"192.168.1.1": "aa:bb:cc:dd:ee:ff"})
    with patch("modules.arp_watch.arp_monitor.scan", return_value=result) as mock_scan:
        report = run_arp_watch_cycle(gateway_ip="192.168.1.1", duration=5)

    mock_scan.assert_called_once()
    assert report.events == []


def test_spoof_events_are_passed_through():
    from modules.arp_watch import run_arp_watch_cycle

    evt = SpoofEvent(
        event_type="GATEWAY_HIJACK",
        attacker_mac="11:22:33:44:55:66",
        attacker_ip="192.168.1.50",
        victim_ip="192.168.1.1",
        original_mac="aa:bb:cc:dd:ee:ff",
        verdict="GATEWAY HIJACK: ...",
    )
    result = ARPScanResult(events=[evt])
    with patch("modules.arp_watch.arp_monitor.scan", return_value=result):
        report = run_arp_watch_cycle(gateway_ip="192.168.1.1", duration=5)

    assert report.events == [evt]

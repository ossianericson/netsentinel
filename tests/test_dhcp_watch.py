"""Tests for modules/dhcp_watch.py (V6 Sprint 4.2 — rogue DHCP background watch)."""
from __future__ import annotations

from unittest.mock import patch

from modules.dhcp_detector import DHCPOffer, DHCPScanResult


def test_import():
    from modules.dhcp_watch import run_dhcp_watch_cycle, DhcpWatchReport
    assert run_dhcp_watch_cycle is not None
    assert DhcpWatchReport is not None


def test_no_offers_returns_empty_report():
    from modules.dhcp_watch import run_dhcp_watch_cycle

    result = DHCPScanResult(offers=[])
    with patch("modules.dhcp_watch.dhcp_detector.scan", return_value=result) as mock_scan:
        report = run_dhcp_watch_cycle(known_dhcp_server="192.168.1.1", duration=5)

    mock_scan.assert_called_once()
    assert report.offers == []
    assert report.rogue_offers == []


def test_rogue_offer_is_isolated_from_legitimate():
    from modules.dhcp_watch import run_dhcp_watch_cycle

    legit = DHCPOffer(server_ip="192.168.1.1", server_mac="aa:bb:cc:dd:ee:ff",
                       offered_ip="192.168.1.100", gateway="192.168.1.1", is_rogue=False)
    rogue = DHCPOffer(server_ip="192.168.1.99", server_mac="11:22:33:44:55:66",
                       offered_ip="192.168.1.101", gateway="192.168.1.99", is_rogue=True,
                       verdict="ROGUE DHCP SERVER: ...")
    result = DHCPScanResult(offers=[legit, rogue])
    with patch("modules.dhcp_watch.dhcp_detector.scan", return_value=result):
        report = run_dhcp_watch_cycle(known_dhcp_server="192.168.1.1", duration=5)

    assert report.offers == [legit, rogue]
    assert report.rogue_offers == [rogue]

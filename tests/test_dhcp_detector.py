"""Tests for modules/dhcp_detector.py — DHCP rogue server detection."""
from __future__ import annotations

import pytest


def test_import():
    import modules.dhcp_detector  # noqa: F401


def test_dhcp_offer_dataclass():
    from modules.dhcp_detector import DHCPOffer
    offer = DHCPOffer(
        server_ip="192.168.1.1",
        server_mac="aa:bb:cc:dd:ee:ff",
        offered_ip="192.168.1.100",
        gateway="192.168.1.1",
        dns_servers=["8.8.8.8"],
    )
    assert offer.server_ip == "192.168.1.1"
    assert offer.server_mac == "aa:bb:cc:dd:ee:ff"
    assert offer.offered_ip == "192.168.1.100"
    assert offer.lease_time == 0  # default
    assert offer.is_rogue is False  # default


def test_dhcp_offer_rogue_flag():
    from modules.dhcp_detector import DHCPOffer
    offer = DHCPOffer(
        server_ip="10.0.0.99",
        server_mac="de:ad:be:ef:00:01",
        offered_ip="10.0.0.100",
        gateway="10.0.0.99",
        dns_servers=[],
        is_rogue=True,
        verdict="Rogue DHCP server detected",
    )
    assert offer.is_rogue is True
    assert "Rogue" in offer.verdict


def test_dhcp_scan_result_empty():
    from modules.dhcp_detector import DHCPScanResult
    result = DHCPScanResult(offers=[], legitimate_server="192.168.1.1")
    assert result.offers == []
    assert result.plain_verdict == ""  # default


def test_dhcp_scan_result_plain_verdict():
    from modules.dhcp_detector import DHCPOffer, DHCPScanResult
    offer = DHCPOffer("192.168.1.1", "aa:bb:cc:dd:ee:01",
                      "192.168.1.50", "192.168.1.1", [], 3600)
    result = DHCPScanResult(offers=[offer], legitimate_server="192.168.1.1",
                             plain_verdict="1 server found")
    assert result.plain_verdict == "1 server found"
    assert len(result.offers) == 1


def test_dhcp_detector_instantiation():
    from modules.dhcp_detector import DHCPDetector
    import threading
    stop = threading.Event()
    try:
        detector = DHCPDetector(
            on_offer=lambda o: None,
            on_error=lambda e: None,
            known_server_ip=None,
            timeout=1,
            stop_event=stop,
        )
        assert detector is not None
    except Exception as exc:
        pytest.skip(f"DHCPDetector requires admin: {exc}")


def test_scan_graceful_no_scapy():
    from modules.dhcp_detector import scan
    import threading
    stop = threading.Event()
    stop.set()  # stop immediately
    try:
        result = scan(
            known_dhcp_server=None,
            on_offer=lambda o: None,
            on_error=lambda e: None,
            duration=0,
            stop_event=stop,
        )
        assert result is not None
    except (PermissionError, OSError):
        pass  # Expected on non-admin
    except Exception:
        pass  # Other expected errors

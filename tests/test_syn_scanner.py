"""Tests for modules/syn_scanner.py — SYN stealth port scanner."""
from modules.syn_scanner import SYNPortResult, SYNScanResult, syn_scan, udp_scan


def test_import():
    import modules.syn_scanner as m
    assert hasattr(m, "SYNPortResult")
    assert hasattr(m, "SYNScanResult")
    assert hasattr(m, "syn_scan")
    assert hasattr(m, "udp_scan")


def test_syn_port_result_fields():
    r = SYNPortResult(port=443, state="open", proto="TCP", service="HTTPS")
    assert r.port == 443
    assert r.state == "open"
    assert r.service == "HTTPS"
    assert r.proto == "TCP"


def test_syn_port_result_states():
    for state in ("open", "closed", "filtered"):
        r = SYNPortResult(port=80, state=state, proto="TCP", service="")
        assert r.state == state


def test_syn_scan_result_fields():
    r = SYNScanResult(host="192.168.1.1")
    assert r.host == "192.168.1.1"
    assert r.open_ports == []
    assert r.error == ""


def test_syn_scan_no_admin_or_no_scapy():
    result = syn_scan("192.168.1.1", ports=[80], timeout=0.1)
    assert isinstance(result, SYNScanResult)
    if result.error:
        assert isinstance(result.error, str)


def test_udp_scan_no_admin_or_no_scapy():
    result = udp_scan("192.168.1.1", ports=[53], timeout=0.1)
    assert isinstance(result, SYNScanResult)
    if result.error:
        assert isinstance(result.error, str)

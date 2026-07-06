"""Tests for modules/syn_scanner.py — SYN stealth port scanner."""
from unittest.mock import patch

from modules.syn_scanner import SYNPortResult, SYNScanResult, syn_scan, udp_scan


def test_import():
    from modules import syn_scanner as m
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
    assert r.banner == ""
    assert r.service_version == ""


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


def test_grab_banners_populates_open_ports():
    from modules.syn_scanner import _grab_banners

    open_ports = [
        SYNPortResult(port=22, state="open", proto="tcp", service="SSH"),
        SYNPortResult(port=9999, state="open", proto="tcp", service="port 9999"),
    ]

    def _fake_probe_service(sock, port, ip, timeout):
        if port == 22:
            return "SSH-2.0-OpenSSH_8.9p1", "OpenSSH 8.9p1"
        raise OSError("connection refused")

    with patch("modules.syn_scanner.socket.create_connection") as mock_conn, \
         patch("modules.syn_scanner.probe_service", side_effect=_fake_probe_service):
        mock_conn.return_value.__enter__.return_value = object()
        _grab_banners(open_ports, ip="192.168.1.1", timeout=0.5)

    assert open_ports[0].banner == "SSH-2.0-OpenSSH_8.9p1"
    assert open_ports[0].service_version == "OpenSSH 8.9p1"
    # A failed probe must not raise — banner/version simply stay empty
    assert open_ports[1].banner == ""
    assert open_ports[1].service_version == ""

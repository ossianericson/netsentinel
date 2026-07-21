"""Tests for modules/syn_scanner.py — SYN stealth port scanner."""
from unittest.mock import patch

import pytest

from modules.syn_scanner import SYNPortResult, SYNScanResult, syn_scan, udp_scan

scapy = pytest.importorskip("scapy.all")


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


def test_syn_scan_counts_unanswered_ports_as_filtered():
    """Regression: line ~280 used to iterate a stale empty placeholder (`_`)
    instead of the real `unanswered` list returned by sr(), so every
    genuinely-filtered (no-response) port silently vanished from open_ports,
    filtered, AND closed — not even miscounted, just dropped."""

    def _fake_sr(packets, **kwargs):
        return [], packets  # nothing answered -> everything unanswered

    with patch("scapy.all.sr", side_effect=_fake_sr), \
         patch("modules.syn_scanner._grab_banners"):
        result = syn_scan("127.0.0.1", ports=[80, 443], timeout=0.1)

    assert result.error == ""
    assert result.open_ports == []
    assert result.closed == 0
    assert result.filtered == 2


def test_syn_scan_all_filtered_is_not_testable():
    """A firewall silently dropping every probe must not read as a clean
    'no open ports' verdict — it must be flagged not_testable with a reason."""

    def _fake_sr(packets, **kwargs):
        return [], packets  # nothing answered -> everything unanswered

    with patch("scapy.all.sr", side_effect=_fake_sr), \
         patch("modules.syn_scanner._grab_banners"):
        result = syn_scan("127.0.0.1", ports=[80, 443], timeout=0.1)

    assert result.not_testable is True
    assert "127.0.0.1" in result.not_testable_reason or "filtered" in result.not_testable_reason.lower()
    assert "not_testable" not in result.plain_verdict  # sanity: verdict is prose, not the field name


def test_syn_scan_some_open_is_still_testable():
    """A scan that finds at least one open port is a confirmed result, not not_testable."""

    def _fake_sr(packets, **kwargs):
        from scapy.all import TCP
        answered = []
        for p in packets:
            if p[TCP].dport == 80:
                recv = p.copy()
                recv[TCP].flags = "SA"
                answered.append((p, recv))
        unanswered = [p for p in packets if p[TCP].dport != 80]
        return answered, unanswered

    with patch("scapy.all.sr", side_effect=_fake_sr), \
         patch("modules.syn_scanner._grab_banners"):
        result = syn_scan("127.0.0.1", ports=[80, 443], timeout=0.1)

    assert len(result.open_ports) == 1
    assert result.not_testable is False


def test_udp_scan_all_silent_is_not_testable():
    """Sprint 5b (F): a firewall silently dropping every UDP probe AND every
    ICMP unreachable response must not read as ordinary UDP ambiguity — zero
    ICMP-closed and zero explicit-open across the whole scan means no signal
    got through in either direction, distinct from a normal mixed
    open|filtered/closed picture (which stays non-error, per Sprint 5a)."""

    def _fake_sr(packets, **kwargs):
        return [], packets  # nothing answered at all

    with patch("scapy.all.sr", side_effect=_fake_sr):
        result = udp_scan("127.0.0.1", ports=[53, 123], timeout=0.1)

    assert result.not_testable is True
    assert "127.0.0.1" in result.not_testable_reason
    assert all(p.state == "open|filtered" for p in result.open_ports)
    assert "not_testable" not in result.plain_verdict  # sanity: verdict is prose


def test_udp_scan_with_icmp_closed_is_still_testable():
    """At least one ICMP port-unreachable proves packets are getting through
    in both directions — ordinary open|filtered ambiguity on OTHER ports is
    expected and must not be flagged not_testable."""

    def _fake_sr(packets, **kwargs):
        from scapy.all import ICMP, IP, UDP as _UDP
        answered = []
        for p in packets:
            if p[_UDP].dport == 53:
                recv = IP(dst="127.0.0.1") / ICMP(type=3)
                answered.append((p, recv))
        unanswered = [p for p in packets if p[_UDP].dport != 53]
        return answered, unanswered

    with patch("scapy.all.sr", side_effect=_fake_sr):
        result = udp_scan("127.0.0.1", ports=[53, 123], timeout=0.1)

    assert result.closed == 1
    assert result.not_testable is False


def test_udp_scan_with_explicit_open_is_still_testable():
    """At least one explicit non-ICMP response also proves the scan reached
    the host — must not be flagged not_testable."""

    def _fake_sr(packets, **kwargs):
        from scapy.all import IP, UDP as _UDP
        answered = []
        for p in packets:
            if p[_UDP].dport == 53:
                recv = IP(dst="127.0.0.1") / _UDP(sport=53)
                answered.append((p, recv))
        unanswered = [p for p in packets if p[_UDP].dport != 53]
        return answered, unanswered

    with patch("scapy.all.sr", side_effect=_fake_sr):
        result = udp_scan("127.0.0.1", ports=[53, 123], timeout=0.1)

    open_states = [p.state for p in result.open_ports if p.port == 53]
    assert open_states == ["open"]
    assert result.not_testable is False


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

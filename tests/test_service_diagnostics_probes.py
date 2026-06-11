"""
Tests for modules/service_diagnostics_probes.py

Focused unit tests for individual probe dataclasses, parsing helpers, and
probe constructors. Live network tests are marked @pytest.mark.live and
excluded from CI.
"""
from __future__ import annotations

import pytest


# ── Import test ───────────────────────────────────────────────────────────────

def test_module_importable():
    import modules.service_diagnostics_probes as m
    assert hasattr(m, "dns_probe")
    assert hasattr(m, "tcp_probe")
    assert hasattr(m, "https_probe")
    assert hasattr(m, "icmp_probe")
    assert hasattr(m, "traceroute_probe")


# ── DnsProbeResult ────────────────────────────────────────────────────────────

def test_dns_probe_result_fields():
    from modules.service_diagnostics_probes import DnsProbeResult
    r = DnsProbeResult(hostname="example.com")
    assert r.hostname == "example.com"
    assert r.ipv4 == ""
    assert r.ipv6 == ""
    assert r.rtt_ms == -1.0
    assert r.error == ""


def test_dns_probe_result_with_data():
    from modules.service_diagnostics_probes import DnsProbeResult
    r = DnsProbeResult(
        hostname="google.com", ipv4="142.250.80.46", rtt_ms=8.3
    )
    assert r.ipv4 == "142.250.80.46"
    assert r.rtt_ms == pytest.approx(8.3)


# ── TcpProbeResult ────────────────────────────────────────────────────────────

def test_tcp_probe_result_defaults():
    from modules.service_diagnostics_probes import TcpProbeResult
    r = TcpProbeResult(host="example.com", port=443)
    assert r.up is False
    assert r.rtt_ms == -1.0
    assert r.error == ""


def test_tcp_probe_result_success():
    from modules.service_diagnostics_probes import TcpProbeResult
    r = TcpProbeResult(host="example.com", port=443, up=True, rtt_ms=12.5)
    assert r.up is True
    assert r.rtt_ms == pytest.approx(12.5)


# ── HttpsProbeResult ──────────────────────────────────────────────────────────

def test_https_probe_result_defaults():
    from modules.service_diagnostics_probes import HttpsProbeResult
    r = HttpsProbeResult(url="https://example.com")
    assert r.up is False
    assert r.status_code == 0
    assert r.rtt_ms == -1.0
    assert r.error == ""


def test_https_probe_result_http_error():
    from modules.service_diagnostics_probes import HttpsProbeResult
    r = HttpsProbeResult(
        url="https://example.com", up=False, status_code=503, error="HTTP 503"
    )
    assert r.status_code == 503
    assert not r.up


# ── IcmpProbeResult ───────────────────────────────────────────────────────────

def test_icmp_probe_result_defaults():
    from modules.service_diagnostics_probes import IcmpProbeResult
    r = IcmpProbeResult(host="8.8.8.8")
    assert r.min_ms == -1.0
    assert r.avg_ms == -1.0
    assert r.max_ms == -1.0
    assert r.loss_pct == 100.0
    assert r.jitter_ms == -1.0
    assert r.error == ""


# ── TracerouteResult / TraceHop ───────────────────────────────────────────────

def test_traceroute_result_defaults():
    from modules.service_diagnostics_probes import TracerouteResult
    r = TracerouteResult(host="example.com")
    assert r.hops == []
    assert r.hop_count == 0
    assert r.reached is False
    assert r.anomalies == []


def test_trace_hop_fields():
    from modules.service_diagnostics_probes import TraceHop
    h = TraceHop(hop=3, ip="10.0.0.1", rtt_ms=4.2)
    assert h.hop == 3
    assert h.ip == "10.0.0.1"
    assert h.rtt_ms == pytest.approx(4.2)


# ── _parse_ping_output ────────────────────────────────────────────────────────

def test_parse_ping_windows_full():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "Pinging 1.1.1.1 with 32 bytes of data:\n"
        "Reply from 1.1.1.1: bytes=32 time=10ms TTL=57\n"
        "Reply from 1.1.1.1: bytes=32 time=12ms TTL=57\n"
        "\n"
        "Ping statistics for 1.1.1.1:\n"
        "    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),\n"
        "Approximate round trip times in milli-seconds:\n"
        "    Minimum = 10ms, Maximum = 12ms, Average = 11ms\n"
    )
    r = IcmpProbeResult(host="1.1.1.1")
    _parse_ping_output(output, r, "Windows")
    assert r.min_ms == 10.0
    assert r.max_ms == 12.0
    assert r.avg_ms == 11.0
    assert r.jitter_ms == pytest.approx(2.0)
    assert r.loss_pct == 0.0


def test_parse_ping_windows_100_loss():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "Ping statistics for 10.0.0.99:\n"
        "    Packets: Sent = 4, Received = 0, Lost = 4 (100% loss),\n"
    )
    r = IcmpProbeResult(host="10.0.0.99")
    _parse_ping_output(output, r, "Windows")
    assert r.loss_pct == 100.0
    assert r.avg_ms == -1.0


def test_parse_ping_linux_with_mdev():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=15.1 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "4 packets transmitted, 4 received, 0% packet loss, time 3004ms\n"
        "rtt min/avg/max/mdev = 14.000/15.100/16.200/0.900 ms\n"
    )
    r = IcmpProbeResult(host="8.8.8.8")
    _parse_ping_output(output, r, "Linux")
    assert r.min_ms == pytest.approx(14.0)
    assert r.avg_ms == pytest.approx(15.1)
    assert r.max_ms == pytest.approx(16.2)
    assert r.jitter_ms == pytest.approx(0.9, abs=0.01)
    assert r.loss_pct == 0.0


def test_parse_ping_linux_partial_loss():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "4 packets transmitted, 3 received, 25% packet loss, time 3001ms\n"
        "rtt min/avg/max/mdev = 10.000/11.000/12.000/1.000 ms\n"
    )
    r = IcmpProbeResult(host="example.com")
    _parse_ping_output(output, r, "Linux")
    assert r.loss_pct == pytest.approx(25.0)
    assert r.avg_ms == pytest.approx(11.0)


# ── _raw_dns_a (internal, unit-testable via import) ───────────────────────────

def test_raw_dns_a_raises_on_bad_server():
    """Connecting to a non-DNS port should raise, not hang silently."""
    from modules.service_diagnostics_probes import _raw_dns_a
    with pytest.raises(Exception):
        # Port 9 (discard) — no DNS response expected
        _raw_dns_a("example.com", "127.0.0.1")


# ── Live probe tests (excluded from CI) ──────────────────────────────────────

@pytest.mark.live
def test_live_dns_probe_resolves():
    from modules.service_diagnostics_probes import dns_probe
    r = dns_probe("cloudflare.com")
    assert r.ipv4, "Expected IPv4 from cloudflare.com"
    assert r.rtt_ms > 0
    assert r.error == ""


@pytest.mark.live
def test_live_dns_probe_custom_server():
    from modules.service_diagnostics_probes import dns_probe
    r = dns_probe("example.com", server="8.8.8.8")
    assert r.ipv4, "Expected IPv4 via 8.8.8.8"


@pytest.mark.live
def test_live_tcp_probe_443():
    from modules.service_diagnostics_probes import tcp_probe
    r = tcp_probe("one.one.one.one", 443)
    assert r.up
    assert r.rtt_ms > 0


@pytest.mark.live
def test_live_https_probe_cloudflare():
    from modules.service_diagnostics_probes import https_probe
    r = https_probe("https://1.1.1.1")
    assert r.up
    assert r.status_code in (200, 301, 302)


@pytest.mark.live
def test_live_icmp_probe_google():
    from modules.service_diagnostics_probes import icmp_probe
    r = icmp_probe("8.8.8.8", count=2)
    assert r.avg_ms > 0 or r.error  # may be blocked; just check it runs

"""Tests for modules/network_diagnostics.py — health check dataclasses and helpers."""
from __future__ import annotations

import pytest


def test_import():
    import modules.network_diagnostics  # noqa: F401


def test_ping_result_dataclass():
    from modules.network_diagnostics import PingResult
    r = PingResult(host="8.8.8.8", ip="8.8.8.8", rtt_ms=12.5, status="ok")
    assert r.host == "8.8.8.8"
    assert r.rtt_ms == pytest.approx(12.5)
    assert r.status == "ok"


def test_dns_result_dataclass():
    from modules.network_diagnostics import DnsResult
    r = DnsResult(server="8.8.8.8", domain="example.com",
                  latency_ms=3.2, resolved_ip="93.184.216.34", status="ok")
    assert r.server == "8.8.8.8"
    assert r.status == "ok"


def test_http_result_dataclass():
    from modules.network_diagnostics import HttpResult
    r = HttpResult(url="https://example.com", status_code=200,
                   latency_ms=45.0, status="ok")
    assert r.status_code == 200
    assert r.status == "ok"


def test_trace_hop_dataclass():
    from modules.network_diagnostics import TraceHop
    hop = TraceHop(hop=1, ip="10.0.0.1", rtt_ms=0.5)
    assert hop.hop == 1
    assert hop.ip == "10.0.0.1"
    assert hop.rtt_ms == pytest.approx(0.5)


def test_dns_leak_entry_dataclass():
    from modules.network_diagnostics import DnsLeakEntry
    entry = DnsLeakEntry(server_ip="1.1.1.1", country="US", org="Cloudflare")
    assert entry.server_ip == "1.1.1.1"
    assert entry.org == "Cloudflare"


def test_dns_leak_result_dataclass():
    from modules.network_diagnostics import DnsLeakResult, DnsLeakEntry
    entry = DnsLeakEntry(server_ip="1.1.1.1", country="US", org="Cloudflare")
    result = DnsLeakResult(resolvers_seen=[entry], leak_detected=False,
                            plain_verdict="No leak detected")
    assert result.leak_detected is False
    assert len(result.resolvers_seen) == 1
    assert "leak" in result.plain_verdict.lower() or isinstance(result.plain_verdict, str)


def test_diagnostics_result_structure():
    from modules.network_diagnostics import DiagnosticsResult, PingResult
    pr = PingResult(host="1.1.1.1", ip="1.1.1.1", rtt_ms=5.0, status="ok")
    result = DiagnosticsResult(
        ping_results=[pr], dns_results=[], http_results=[],
        trace_hops=[], dns_leak=None, download_mbps=None,
        public_ip=None, plain_verdict="ok", gateway_ip="192.168.1.1",
    )
    assert len(result.ping_results) == 1
    assert result.dns_results == []


def test_scan_function_exists():
    from modules.network_diagnostics import scan
    import inspect
    assert callable(scan)
    sig = inspect.signature(scan)
    assert len(sig.parameters) >= 1

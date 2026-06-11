"""
Tests for modules/service_diagnostics.py and modules/service_diagnostics_probes.py
"""
from __future__ import annotations

import pytest


# ── Import tests ──────────────────────────────────────────────────────────────

def test_probes_importable():
    from modules.service_diagnostics_probes import (
        DnsProbeResult,
        TcpProbeResult,
        HttpsProbeResult,
        IcmpProbeResult,
        TracerouteResult,
        TraceHop,
        dns_probe,
        tcp_probe,
        https_probe,
        icmp_probe,
        traceroute_probe,
    )
    assert DnsProbeResult
    assert TcpProbeResult
    assert HttpsProbeResult
    assert IcmpProbeResult
    assert TracerouteResult
    assert TraceHop
    assert callable(dns_probe)
    assert callable(tcp_probe)
    assert callable(https_probe)
    assert callable(icmp_probe)
    assert callable(traceroute_probe)


def test_diagnostics_importable():
    from modules.service_diagnostics import (
        ServiceEntry,
        ServiceDiagnosticResult,
        BatchDiagnosticResult,
        LayerResult,
        DiagnosticEngine,
        SERVICE_CATALOG,
    )
    assert ServiceEntry
    assert ServiceDiagnosticResult
    assert BatchDiagnosticResult
    assert LayerResult
    assert DiagnosticEngine
    assert isinstance(SERVICE_CATALOG, dict)


# ── Service catalog structure ─────────────────────────────────────────────────

def test_catalog_streaming_services_present():
    from modules.service_diagnostics import SERVICE_CATALOG
    expected = {
        "netflix", "hbomax", "disneyplus", "appletv",
        "primevideo", "youtube", "spotify", "twitch",
    }
    assert expected.issubset(set(SERVICE_CATALOG.keys()))


def test_catalog_gaming_services_present():
    from modules.service_diagnostics import SERVICE_CATALOG
    expected = {
        "steam", "epicgames", "fortnite", "xboxlive",
        "psn", "nintendo", "riot", "ea", "ubisoft", "battlenet",
    }
    assert expected.issubset(set(SERVICE_CATALOG.keys()))


def test_catalog_total_service_count():
    from modules.service_diagnostics import SERVICE_CATALOG
    # 8 streaming + 10 gaming = 18 total
    assert len(SERVICE_CATALOG) == 18


def test_catalog_entries_have_required_fields():
    from modules.service_diagnostics import SERVICE_CATALOG
    for sid, entry in SERVICE_CATALOG.items():
        assert entry.id == sid, f"{sid}: id mismatch"
        assert entry.name, f"{sid}: name is empty"
        assert entry.category in ("streaming", "gaming"), f"{sid}: bad category"
        assert entry.probe_hosts, f"{sid}: no probe_hosts"
        assert entry.tcp_ports, f"{sid}: no tcp_ports"
        assert entry.https_urls, f"{sid}: no https_urls"
        for url in entry.https_urls:
            assert url.startswith("https://"), f"{sid}: non-HTTPS url {url}"


def test_catalog_no_duplicate_ids():
    from modules.service_diagnostics import _STREAMING, _GAMING
    ids = [s.id for s in _STREAMING + _GAMING]
    assert len(ids) == len(set(ids)), "Duplicate service IDs found"


# ── Dataclass defaults ────────────────────────────────────────────────────────

def test_layer_result_default_passed():
    from modules.service_diagnostics import LayerResult
    lr = LayerResult()
    assert lr.passed is True
    assert lr.detail == ""


def test_service_diagnostic_result_defaults():
    from modules.service_diagnostics import ServiceDiagnosticResult
    r = ServiceDiagnosticResult(service_id="test", service_name="Test")
    assert r.failure_layer == "none"
    assert r.confidence == 0
    assert r.dns_probes == []
    assert r.tcp_probes == []
    assert r.https_probes == []
    assert r.icmp_result is None
    assert r.trace is None


def test_batch_diagnostic_result_defaults():
    from modules.service_diagnostics import BatchDiagnosticResult
    b = BatchDiagnosticResult()
    assert b.results == []
    assert b.cross_summary == ""
    assert b.dns_failure_count == 0
    assert b.reachability_failure_count == 0
    assert b.total == 0


def test_dns_probe_result_defaults():
    from modules.service_diagnostics_probes import DnsProbeResult
    r = DnsProbeResult(hostname="example.com")
    assert r.ipv4 == ""
    assert r.ipv6 == ""
    assert r.rtt_ms == -1.0
    assert r.error == ""


def test_icmp_probe_result_defaults():
    from modules.service_diagnostics_probes import IcmpProbeResult
    r = IcmpProbeResult(host="example.com")
    assert r.loss_pct == 100.0
    assert r.avg_ms == -1.0


# ── Classification logic ──────────────────────────────────────────────────────

def _make_dns_ok(hostname: str = "example.com", rtt: float = 12.0):
    from modules.service_diagnostics_probes import DnsProbeResult
    return DnsProbeResult(hostname=hostname, ipv4="93.184.216.34", rtt_ms=rtt)


def _make_dns_fail(hostname: str = "example.com"):
    from modules.service_diagnostics_probes import DnsProbeResult
    return DnsProbeResult(hostname=hostname, error="Name resolution failed")


def _make_tcp_ok(host: str = "example.com", port: int = 443):
    from modules.service_diagnostics_probes import TcpProbeResult
    return TcpProbeResult(host=host, port=port, up=True, rtt_ms=18.0)


def _make_tcp_fail(host: str = "example.com", port: int = 443):
    from modules.service_diagnostics_probes import TcpProbeResult
    return TcpProbeResult(host=host, port=port, up=False, error="Connection refused")


def _make_https_ok(url: str = "https://example.com"):
    from modules.service_diagnostics_probes import HttpsProbeResult
    return HttpsProbeResult(url=url, up=True, status_code=200, rtt_ms=80.0)


def _make_https_fail(url: str = "https://example.com"):
    from modules.service_diagnostics_probes import HttpsProbeResult
    return HttpsProbeResult(url=url, up=False, error="Connection refused")


def _make_icmp_ok(avg: float = 20.0, loss: float = 0.0):
    from modules.service_diagnostics_probes import IcmpProbeResult
    return IcmpProbeResult(
        host="example.com", min_ms=avg * 0.9, avg_ms=avg,
        max_ms=avg * 1.1, loss_pct=loss, jitter_ms=avg * 0.1,
    )


def _make_icmp_fail():
    from modules.service_diagnostics_probes import IcmpProbeResult
    return IcmpProbeResult(host="example.com", loss_pct=100.0, avg_ms=-1.0)


def _make_result_with_probes(
    service_id: str = "steam",
    dns_ok: bool = True,
    tcp_ok: bool = True,
    https_ok: bool = True,
    icmp_avg: float = 20.0,
    icmp_loss: float = 0.0,
):
    from modules.service_diagnostics import ServiceDiagnosticResult
    r = ServiceDiagnosticResult(service_id=service_id, service_name="Steam")
    r.dns_probes = [_make_dns_ok() if dns_ok else _make_dns_fail()]
    r.tcp_probes = [_make_tcp_ok() if tcp_ok else _make_tcp_fail()]
    r.https_probes = [_make_https_ok() if https_ok else _make_https_fail()]
    r.icmp_result = _make_icmp_ok(avg=icmp_avg, loss=icmp_loss) if icmp_avg > 0 else _make_icmp_fail()
    return r


def test_classify_all_healthy():
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes()
    _classify(r, ref_reachable=True)
    assert r.failure_layer == "none"
    assert r.confidence >= 80
    assert "normally" in r.summary


def test_classify_dns_failure_ref_reachable():
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(dns_ok=False, tcp_ok=False, https_ok=False)
    _classify(r, ref_reachable=True)
    assert r.failure_layer == "dns"
    assert not r.dns.passed
    assert r.confidence >= 70


def test_classify_dns_failure_ref_unreachable():
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(dns_ok=False, tcp_ok=False, https_ok=False)
    _classify(r, ref_reachable=False)
    assert r.failure_layer == "dns"
    assert r.confidence >= 80
    assert "router" in r.summary.lower()


def test_classify_remote_outage():
    """DNS resolved, reference reachable, but service itself unreachable."""
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(dns_ok=True, tcp_ok=False, https_ok=False)
    _classify(r, ref_reachable=True)
    assert r.failure_layer == "remote_outage"
    assert r.confidence >= 70


def test_classify_local_network_failure():
    """Nothing reachable + 100% packet loss → local network."""
    from modules.service_diagnostics import _classify
    from modules.service_diagnostics_probes import IcmpProbeResult
    r = _make_result_with_probes(dns_ok=True, tcp_ok=False, https_ok=False)
    r.icmp_result = IcmpProbeResult(host="example.com", loss_pct=100.0, avg_ms=-1.0)
    _classify(r, ref_reachable=False)
    assert r.failure_layer == "local_network"


def test_classify_isp_failure():
    """Nothing reachable but not 100% packet loss → ISP."""
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(
        dns_ok=True, tcp_ok=False, https_ok=False, icmp_avg=300.0, icmp_loss=60.0
    )
    _classify(r, ref_reachable=False)
    assert r.failure_layer == "isp"


def test_classify_high_latency_routing():
    """Reachable but high latency → routing."""
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(
        dns_ok=True, tcp_ok=True, https_ok=True, icmp_avg=350.0, icmp_loss=0.0
    )
    _classify(r, ref_reachable=True)
    assert r.failure_layer == "routing"
    assert r.confidence >= 55


def test_classify_packet_loss_isp():
    """Reachable but high loss → ISP congestion."""
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(
        dns_ok=True, tcp_ok=True, https_ok=True, icmp_avg=50.0, icmp_loss=15.0
    )
    _classify(r, ref_reachable=True)
    assert r.failure_layer == "isp"


# ── Cross-service analysis ────────────────────────────────────────────────────

def test_cross_diagnose_all_ok():
    from modules.service_diagnostics import BatchDiagnosticResult, _cross_diagnose, ServiceDiagnosticResult
    b = BatchDiagnosticResult(total=3)
    for i in range(3):
        r = ServiceDiagnosticResult(service_id=str(i), service_name=f"Svc{i}")
        r.failure_layer = "none"
        b.results.append(r)
    result = _cross_diagnose(b)
    assert "normally" in result


def test_cross_diagnose_all_dns_fail():
    from modules.service_diagnostics import BatchDiagnosticResult, _cross_diagnose, ServiceDiagnosticResult, LayerResult
    b = BatchDiagnosticResult(total=3)
    for i in range(3):
        r = ServiceDiagnosticResult(service_id=str(i), service_name=f"Svc{i}")
        r.failure_layer = "dns"
        r.dns = LayerResult(passed=False)
        b.results.append(r)
    result = _cross_diagnose(b)
    assert "dns" in result.lower()


def test_cross_diagnose_single_remote_outage():
    from modules.service_diagnostics import BatchDiagnosticResult, _cross_diagnose, ServiceDiagnosticResult
    b = BatchDiagnosticResult(total=2)
    ok = ServiceDiagnosticResult(service_id="youtube", service_name="YouTube")
    ok.failure_layer = "none"
    bad = ServiceDiagnosticResult(service_id="steam", service_name="Steam")
    bad.failure_layer = "remote_outage"
    b.results = [ok, bad]
    result = _cross_diagnose(b)
    assert "Steam" in result


def test_cross_diagnose_empty_batch():
    from modules.service_diagnostics import BatchDiagnosticResult, _cross_diagnose
    b = BatchDiagnosticResult()
    assert _cross_diagnose(b) == "No services tested."


# ── Engine instantiation ──────────────────────────────────────────────────────

def test_engine_instantiation():
    from modules.service_diagnostics import DiagnosticEngine
    engine = DiagnosticEngine()
    assert engine is not None


def test_engine_unknown_service():
    from modules.service_diagnostics import DiagnosticEngine
    engine = DiagnosticEngine()
    result = engine.run("does_not_exist_xyz")
    assert result.service_id == "does_not_exist_xyz"
    assert "Unknown service" in result.summary
    assert result.confidence == 100


# ── Ping output parsing ───────────────────────────────────────────────────────

def test_parse_ping_windows():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "Pinging 8.8.8.8 with 32 bytes of data:\n"
        "Reply from 8.8.8.8: bytes=32 time=14ms TTL=115\n"
        "Reply from 8.8.8.8: bytes=32 time=13ms TTL=115\n"
        "Reply from 8.8.8.8: bytes=32 time=15ms TTL=115\n"
        "\n"
        "Ping statistics for 8.8.8.8:\n"
        "    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),\n"
        "Approximate round trip times in milli-seconds:\n"
        "    Minimum = 13ms, Maximum = 15ms, Average = 14ms\n"
    )
    r = IcmpProbeResult(host="8.8.8.8")
    _parse_ping_output(output, r, "Windows")
    assert r.min_ms == 13.0
    assert r.max_ms == 15.0
    assert r.avg_ms == 14.0
    assert r.loss_pct == 0.0
    assert r.jitter_ms == 2.0


def test_parse_ping_linux():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        "64 bytes from 8.8.8.8: icmp_seq=1 ttl=115 time=12.3 ms\n"
        "64 bytes from 8.8.8.8: icmp_seq=2 ttl=115 time=11.8 ms\n"
        "\n"
        "--- 8.8.8.8 ping statistics ---\n"
        "2 packets transmitted, 2 received, 0% packet loss, time 1001ms\n"
        "rtt min/avg/max/mdev = 11.800/12.050/12.300/0.250 ms\n"
    )
    r = IcmpProbeResult(host="8.8.8.8")
    _parse_ping_output(output, r, "Linux")
    assert r.min_ms == 11.800
    assert r.avg_ms == 12.050
    assert r.max_ms == 12.300
    assert r.jitter_ms == pytest.approx(0.250, abs=0.01)
    assert r.loss_pct == 0.0


def test_parse_ping_100_percent_loss():
    from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output
    output = (
        "Pinging 10.0.0.1 with 32 bytes of data:\n"
        "Request timed out.\n"
        "Request timed out.\n"
        "\n"
        "Ping statistics for 10.0.0.1:\n"
        "    Packets: Sent = 2, Received = 0, Lost = 2 (100% loss),\n"
    )
    r = IcmpProbeResult(host="10.0.0.1")
    _parse_ping_output(output, r, "Windows")
    assert r.loss_pct == 100.0
    assert r.avg_ms == -1.0


# ── Summary text quality ──────────────────────────────────────────────────────

def test_summary_mentions_service_name():
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(service_id="netflix")
    r.service_name = "Netflix"
    _classify(r, ref_reachable=True)
    assert "Netflix" in r.summary


def test_summary_dns_failure_ref_ok_mentions_dns():
    from modules.service_diagnostics import _classify
    r = _make_result_with_probes(dns_ok=False, tcp_ok=False, https_ok=False)
    _classify(r, ref_reachable=True)
    assert "DNS" in r.summary


def test_confidence_range():
    """confidence must always be 0–100."""
    from modules.service_diagnostics import _classify
    for dns_ok in (True, False):
        for tcp_ok in (True, False):
            r = _make_result_with_probes(dns_ok=dns_ok, tcp_ok=tcp_ok, https_ok=tcp_ok)
            _classify(r, ref_reachable=True)
            assert 0 <= r.confidence <= 100, (
                f"confidence={r.confidence} out of range for dns_ok={dns_ok}, tcp_ok={tcp_ok}"
            )


# ── Live probe smoke tests (skipped in CI) ────────────────────────────────────

@pytest.mark.live
def test_live_dns_probe_google():
    from modules.service_diagnostics_probes import dns_probe
    result = dns_probe("google.com")
    assert result.ipv4, "Expected a valid IPv4 from google.com"
    assert result.rtt_ms > 0


@pytest.mark.live
def test_live_tcp_probe_https():
    from modules.service_diagnostics_probes import tcp_probe
    result = tcp_probe("google.com", 443)
    assert result.up
    assert result.rtt_ms > 0


@pytest.mark.live
def test_live_engine_run_youtube():
    from modules.service_diagnostics import DiagnosticEngine
    engine = DiagnosticEngine()
    result = engine.run("youtube")
    assert result.service_id == "youtube"
    assert isinstance(result.confidence, int)
    assert result.failure_layer in (
        "none", "device", "local_network", "dns", "isp", "routing", "remote_outage"
    )

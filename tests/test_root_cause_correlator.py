"""
Tests for modules/root_cause_correlator.py

Verifies that correlate() produces a CorrelationResult with correct
severity, suppression logic, and ISP-fault detection.

No network, no file I/O, no GUI required.
"""

import sys
import os
import types
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.root_cause_correlator import correlate, CorrelationResult, CorrelatedFinding


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_summary(uptime=99.9, isp_hops_latency=None, avg_rtt=20.0, total_pings=1000):
    obj = types.SimpleNamespace(
        uptime_pct=uptime,
        avg_rtt_ms=avg_rtt,
        avg_dns_ms=30.0,
        avg_jitter_ms=3.0,
        outages=[],
        total_pings=total_pings,
        isp_hops_latency=isp_hops_latency,
    )
    return obj


def _diag_result(trace_hops=None, download_mbps=50.0):
    return types.SimpleNamespace(
        trace_hops=trace_hops or [],
        download_mbps=download_mbps,
        ping_results=[],
        dns_results=[],
    )


def _storm_result(level="CLEAN", bcast_pps=5.0):
    return types.SimpleNamespace(storm_level=level, bcast_per_sec=bcast_pps)


def _stp_bpdus():
    return []


def _rogue_bpdus():
    bpdu = types.SimpleNamespace(is_rogue=True, src_mac="aa:bb:cc:dd:ee:ff")
    return [bpdu]


def _fingerprint_devices(count=5):
    return [
        types.SimpleNamespace(
            ip=f"192.168.1.{i}", mac=f"aa:bb:cc:00:00:{i:02x}", vendor="Acme"
        )
        for i in range(count)
    ]


# ── Basic return type ─────────────────────────────────────────────────────────

class TestReturnType:
    def test_returns_correlation_result(self):
        result = correlate()
        assert isinstance(result, CorrelationResult)

    def test_no_data_no_findings(self):
        result = correlate()
        assert isinstance(result.findings, list)
        assert result.global_severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

    def test_plain_summary_is_string(self):
        result = correlate()
        assert isinstance(result.plain_summary, str)

    def test_isp_issue_detected_is_bool(self):
        result = correlate()
        assert isinstance(result.isp_issue_detected, bool)

    def test_suppress_local_alerts_is_bool(self):
        result = correlate()
        assert isinstance(result.suppress_local_alerts, bool)


# ── Clean network → no critical findings ─────────────────────────────────────

class TestCleanNetwork:
    def setup_method(self):
        self.result = correlate(
            diag_result=_diag_result(),
            storm_result=_storm_result(level="CLEAN"),
            stp_bpdus=_stp_bpdus(),
            fingerprint_devices=_fingerprint_devices(3),
            log_summary=_log_summary(uptime=99.9),
            gateway_mac=None,
        )

    def test_severity_not_critical(self):
        assert self.result.global_severity not in ("HIGH", "CRITICAL")

    def test_isp_issue_not_detected(self):
        assert not self.result.isp_issue_detected

    def test_no_suppression(self):
        assert not self.result.suppress_local_alerts


# ── Rogue BPDU → STP finding raised ──────────────────────────────────────────

class TestRogueBpdu:
    def setup_method(self):
        self.result = correlate(
            stp_bpdus=_rogue_bpdus(),
            log_summary=_log_summary(),
        )

    def test_finding_added(self):
        assert len(self.result.findings) >= 1

    def test_finding_has_correct_fields(self):
        for f in self.result.findings:
            assert isinstance(f, CorrelatedFinding)
            assert f.headline
            assert f.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
            assert f.category
            assert f.remediation

    def test_stp_severity_high_or_critical(self):
        severities = [f.severity for f in self.result.findings]
        assert any(s in ("HIGH", "CRITICAL") for s in severities)


# ── Broadcast storm finding ───────────────────────────────────────────────────

class TestBroadcastStorm:
    def setup_method(self):
        self.result = correlate(
            storm_result=_storm_result(level="STORM", bcast_pps=5000.0),
            log_summary=_log_summary(),
        )

    def test_storm_finding_raised(self):
        assert len(self.result.findings) >= 1

    def test_storm_severity_significant(self):
        severities = [f.severity for f in self.result.findings]
        assert any(s in ("MEDIUM", "HIGH", "CRITICAL") for s in severities)


# ── ISP fault detection ───────────────────────────────────────────────────────

class TestIspFaultDetection:
    def test_low_uptime_flags_findings(self):
        result = correlate(log_summary=_log_summary(uptime=60.0, total_pings=500))
        # A low-uptime network should produce at least one finding
        assert len(result.findings) >= 1

    def test_isp_issue_sets_summary(self):
        result = correlate(log_summary=_log_summary(uptime=60.0))
        assert len(result.plain_summary) > 0


# ── Finding structure ─────────────────────────────────────────────────────────

class TestFindingStructure:
    def test_all_findings_have_required_fields(self):
        result = correlate(
            stp_bpdus=_rogue_bpdus(),
            storm_result=_storm_result(level="STORM"),
            log_summary=_log_summary(uptime=70.0),
        )
        required = {"source", "category", "severity", "headline", "detail", "remediation"}
        for f in result.findings:
            for attr in required:
                val = getattr(f, attr, None)
                assert val is not None, f"CorrelatedFinding missing attribute: {attr}"


# ── A3: verify_step field ─────────────────────────────────────────────────────

class TestVerifyStep:
    def test_finding_has_verify_step_field(self):
        f = CorrelatedFinding(
            source="test", category="test", severity="INFO",
            headline="h", detail="d", remediation="r",
        )
        assert hasattr(f, "verify_step")
        assert f.verify_step == ""

    def test_verify_step_custom_value(self):
        f = CorrelatedFinding(
            source="test", category="test", severity="INFO",
            headline="h", detail="d", remediation="r",
            verify_step="Go to DNS & Stability to confirm.",
        )
        assert f.verify_step == "Go to DNS & Stability to confirm."

    def test_isp_finding_has_verify_step(self):
        hop = types.SimpleNamespace(rtt_ms=1.0)
        bad_hops = [types.SimpleNamespace(rtt_ms=-1) for _ in range(4)]
        dr = types.SimpleNamespace(
            trace_hops=[hop] + bad_hops, ping_results=[], dns_results=[],
            download_mbps=50.0, dns_leak=None,
        )
        result = correlate(diag_result=dr)
        isp_findings = [f for f in result.findings if "ISP" in f.category]
        for f in isp_findings:
            assert hasattr(f, "verify_step")

    def test_stp_finding_has_verify_step(self):
        result = correlate(stp_bpdus=_rogue_bpdus())
        for f in result.findings:
            assert hasattr(f, "verify_step")


# ── A3: gateway_ip threading ──────────────────────────────────────────────────

class TestGatewayIpThreading:
    def test_correlate_accepts_gateway_ip(self):
        result = correlate(gateway_ip="192.168.1.1")
        assert isinstance(result, CorrelationResult)

    def test_dns_failure_remediation_uses_gateway_ip(self):
        import types as _t
        dns_fail = _t.SimpleNamespace(status="FAIL", server="8.8.8.8")
        dr = _t.SimpleNamespace(
            trace_hops=[], ping_results=[], dns_results=[dns_fail],
            download_mbps=50.0, dns_leak=None,
        )
        result = correlate(diag_result=dr, gateway_ip="192.168.0.1")
        dns_findings = [f for f in result.findings if "DNS" in f.category]
        assert dns_findings, "Expected at least one DNS finding"
        from urllib.parse import urlparse
        remedy = dns_findings[0].remediation
        urls = [tok for tok in remedy.split() if "://" in tok]
        assert any(urlparse(u).hostname == "192.168.0.1" for u in urls), (
            f"gateway_ip not present in DNS remediation: {remedy}"
        )

    def test_no_cli_commands_in_remediations(self):
        import types as _t
        dns_fail = _t.SimpleNamespace(status="FAIL", server="8.8.8.8")
        dr = _t.SimpleNamespace(
            trace_hops=[], ping_results=[], dns_results=[dns_fail],
            download_mbps=1.0, dns_leak=None,
        )
        result = correlate(
            diag_result=dr,
            storm_result=_storm_result(level="STORM"),
            stp_bpdus=_rogue_bpdus(),
            log_summary=_log_summary(uptime=50.0),
        )
        _BAD_PHRASES = [
            "nslookup", "ipconfig", "ping -t", "ping -c",
            "speedtest.net", "Network Adapter settings", "IPv4 Properties",
        ]
        for f in result.findings:
            for phrase in _BAD_PHRASES:
                assert phrase not in f.remediation, (
                    f"CLI reference '{phrase}' found in {f.category} remediation: "
                    f"{f.remediation!r}"
                )

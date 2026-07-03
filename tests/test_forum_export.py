"""Tests for modules/forum_export.py (TDD — written before implementation)."""

import types

from modules.root_cause_correlator import CorrelationResult, CorrelatedFinding
from modules.forum_export import (
    build_diagnosis_markdown,
    build_service_diagnostics_markdown,
)


def _diag_result():
    return CorrelationResult(
        findings=[
            CorrelatedFinding(
                source="Network Diagnostics",
                category="DNS Resolution Failure",
                severity="HIGH",
                headline="DNS is slow at 192.168.1.50",
                detail="Device aa:bb:cc:dd:ee:ff is affected.",
                remediation="Restart the router at 192.168.1.1.",
                verify_step="Re-run diagnostics after the fix.",
            ),
        ],
        global_severity="HIGH",
        plain_summary="DNS is slow at 192.168.1.50. Plus 0 additional issue(s).",
        metrics={"ping_ms": 22.5, "jitter_ms": 3.0, "loss_pct": 5.0, "dns_ms": 30.0},
    )


def test_build_diagnosis_markdown_contains_metrics_table():
    md = build_diagnosis_markdown(_diag_result(), symptom="slow")
    assert "22.5" in md
    assert "3.0" in md
    assert "5.0" in md
    assert "30.0" in md


def test_build_diagnosis_markdown_sanitizes_ip_and_mac():
    md = build_diagnosis_markdown(_diag_result(), symptom="slow")
    assert "192.168.1.50" not in md
    assert "192.168.1.1" not in md
    assert "aa:bb:cc:dd:ee:ff" not in md.lower()


def test_build_diagnosis_markdown_has_footer_attribution():
    md = build_diagnosis_markdown(_diag_result(), symptom="slow")
    assert "NetSentinel" in md
    assert "Microsoft Store" in md


def test_build_diagnosis_markdown_includes_findings_headline_sanitized():
    md = build_diagnosis_markdown(_diag_result(), symptom="slow")
    assert "DNS is slow" in md


def _service_result():
    dns_probe = types.SimpleNamespace(hostname="www.netflix.com", rtt_ms=12.0, error="")
    tcp_probe = types.SimpleNamespace(host="www.netflix.com", port=443, up=True, rtt_ms=18.0, error="")
    https_probe = types.SimpleNamespace(url="https://www.netflix.com", up=True, status_code=200, rtt_ms=40.0, error="")
    icmp = types.SimpleNamespace(host="www.netflix.com", avg_ms=15.0, jitter_ms=2.0, loss_pct=0.0, error="")
    return types.SimpleNamespace(
        service_id="netflix",
        service_name="Netflix",
        dns_probes=[dns_probe],
        tcp_probes=[tcp_probe],
        https_probes=[https_probe],
        icmp_result=icmp,
        failure_layer="none",
        summary="Netflix is reachable and healthy.",
    )


def test_build_service_diagnostics_markdown_contains_service_name():
    md = build_service_diagnostics_markdown(_service_result())
    assert "Netflix" in md


def test_build_service_diagnostics_markdown_contains_metrics():
    md = build_service_diagnostics_markdown(_service_result())
    assert "12.0" in md
    assert "18.0" in md
    assert "40.0" in md
    assert "2.0" in md


def test_build_service_diagnostics_markdown_has_footer_attribution():
    md = build_service_diagnostics_markdown(_service_result())
    assert "NetSentinel" in md
    assert "Microsoft Store" in md


# ── build_isp_forum_markdown (Feature 3c) ────────────────────────────────────

def _isp_inputs():
    log_summary = types.SimpleNamespace(
        uptime_pct=97.5, avg_rtt_ms=42.0, avg_jitter_ms=8.0,
        outages=[types.SimpleNamespace(), types.SimpleNamespace()],
    )
    diag_result = types.SimpleNamespace(download_mbps=85.0, public_ip="203.0.113.7")
    benchmark_result = types.SimpleNamespace(overall_grade="D", overall_score=48.0)
    return log_summary, diag_result, benchmark_result


def test_build_isp_forum_markdown_contains_metrics():
    from modules.forum_export import build_isp_forum_markdown
    ls, dr, br = _isp_inputs()
    md = build_isp_forum_markdown(log_summary=ls, diag_result=dr,
                                  benchmark_result=br, isp_name="Comcast")
    assert "97.5" in md
    assert "42.0" in md
    assert "8.0" in md
    assert "85.0" in md


def test_build_isp_forum_markdown_has_footer_and_isp():
    from modules.forum_export import build_isp_forum_markdown
    ls, dr, br = _isp_inputs()
    md = build_isp_forum_markdown(log_summary=ls, diag_result=dr,
                                  benchmark_result=br, isp_name="Comcast")
    assert "Comcast" in md
    assert "NetSentinel" in md
    assert "Microsoft Store" in md


def test_build_isp_forum_markdown_omits_public_ip():
    """Public WAN IP must never appear in a shareable forum post."""
    from modules.forum_export import build_isp_forum_markdown
    ls, dr, br = _isp_inputs()
    md = build_isp_forum_markdown(log_summary=ls, diag_result=dr,
                                  benchmark_result=br, isp_name="Comcast")
    assert "203.0.113.7" not in md


def test_build_isp_forum_markdown_handles_missing_data():
    from modules.forum_export import build_isp_forum_markdown
    md = build_isp_forum_markdown()
    assert "NetSentinel" in md

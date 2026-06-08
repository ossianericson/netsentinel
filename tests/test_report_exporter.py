"""
Tests for modules/report_exporter.py :: generate_html()

Pure-function tests — no file I/O, no network, no GUI.
All objects passed as dicts or simple namespaces to avoid importing
every dataclass from production modules.
"""

import sys
import os
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.report_exporter import generate_html


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ns(**kwargs):
    """Build a SimpleNamespace so getattr() inside report_exporter works."""
    return types.SimpleNamespace(**kwargs)


def _diag(public_ip="1.2.3.4", download_mbps=50.0,
          ping_results=None, plain_verdict="", dns_leak=None):
    """Minimal DiagnosticsResult-like object."""
    return _ns(
        public_ip=public_ip,
        download_mbps=download_mbps,
        ping_results=ping_results or [],
        plain_verdict=plain_verdict,
        dns_leak=dns_leak,
    )


def _ping(host, status="OK", rtt_ms=10.0):
    return _ns(host=host, status=status, rtt_ms=rtt_ms)


def _leak(detected: bool, verdict: str = ""):
    return _ns(leak_detected=detected, plain_verdict=verdict)


# ── Tests: basic structure ────────────────────────────────────────────────────

def test_returns_string():
    html = generate_html()
    assert isinstance(html, str)


def test_contains_netsentinel_branding():
    html = generate_html()
    assert "NetSentinel" in html


def test_contains_doctype():
    html = generate_html()
    assert html.strip().startswith("<!DOCTYPE html>") or "<!DOCTYPE html>" in html


def test_contains_print_css():
    html = generate_html()
    assert "@media print" in html


def test_contains_all_module_headings():
    html = generate_html()
    for i in range(1, 6):
        assert f"Module {i}" in html


# ── Tests: overall verdict level → CSS class ─────────────────────────────────

def test_high_verdict_applies_red_class():
    html = generate_html(overall_verdict="Issues found", overall_level="HIGH")
    assert 'class="verdict-box red"' in html


def test_medium_verdict_applies_amber_class():
    html = generate_html(overall_verdict="Check recommended", overall_level="MEDIUM")
    assert 'class="verdict-box amber"' in html


def test_clean_verdict_applies_green_class():
    html = generate_html(overall_verdict="All clear", overall_level="CLEAN")
    assert 'class="verdict-box green"' in html


def test_unknown_level_falls_back_to_amber():
    html = generate_html(overall_verdict="?", overall_level="BLORP")
    assert 'class="verdict-box amber"' in html


# ── Tests: Module 1 device rendering ─────────────────────────────────────────

def test_module1_device_ip_in_output():
    data = {"devices": [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff",
                          "vendor": "ACME Corp", "risk_level": "HIGH",
                          "verdict": "Unknown device", "remediation": "Investigate"}]}
    html = generate_html(module1_data=data)
    assert "192.168.1.50" in html


def test_module1_device_mac_in_output():
    data = {"devices": [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff",
                          "vendor": "ACME", "risk_level": "LOW",
                          "verdict": "", "remediation": ""}]}
    html = generate_html(module1_data=data)
    assert "aa:bb:cc:dd:ee:ff" in html


def test_module1_none_shows_not_run():
    html = generate_html(module1_data=None)
    assert "Module not run" in html


# ── Tests: diagnostics section ────────────────────────────────────────────────

def test_diagnostics_public_ip_rendered():
    html = generate_html(diagnostics_data=_diag(public_ip="203.0.113.42"))
    assert "203.0.113.42" in html


def test_diagnostics_none_shows_not_run():
    html = generate_html(diagnostics_data=None)
    assert "Diagnostics not run" in html


def test_diagnostics_ping_host_rendered():
    pings = [_ping("8.8.8.8", "OK", 12.0)]
    html = generate_html(diagnostics_data=_diag(ping_results=pings))
    assert "8.8.8.8" in html


def test_diagnostics_ping_fail_status_rendered():
    pings = [_ping("8.8.8.8", "FAIL", -1.0)]
    html = generate_html(diagnostics_data=_diag(ping_results=pings))
    assert "FAIL" in html
    assert "unreachable" in html


# ── Tests: DNS leak section ───────────────────────────────────────────────────

def test_dns_leak_detected_in_output():
    leak = _leak(detected=True, verdict="Leak detected via 3 resolvers")
    html = generate_html(diagnostics_data=_diag(dns_leak=leak))
    assert "DNS Leak" in html
    assert "Leak detected via 3 resolvers" in html


def test_dns_no_leak_in_output():
    leak = _leak(detected=False, verdict="No DNS leak detected")
    html = generate_html(diagnostics_data=_diag(dns_leak=leak))
    assert "DNS Leak" in html
    assert "No DNS leak detected" in html


def test_no_dns_leak_object_no_leak_section():
    html = generate_html(diagnostics_data=_diag(dns_leak=None))
    # No "DNS Leak" heading when dns_leak is None
    assert "DNS Leak" not in html


# ── Tests: network info section ───────────────────────────────────────────────

def test_network_info_gateway_rendered():
    info = {"gateway": "192.168.1.1", "local_ips": [], "dns_servers": [], "adapters": []}
    html = generate_html(network_info_data=info)
    assert "192.168.1.1" in html


def test_network_info_dns_server_rendered():
    info = {"gateway": "", "local_ips": [], "dns_servers": ["8.8.8.8"], "adapters": []}
    html = generate_html(network_info_data=info)
    assert "8.8.8.8" in html


def test_network_info_local_ip_rendered():
    info = {
        "gateway": "", "dns_servers": [], "adapters": [],
        "local_ips": [{"ip": "10.0.0.5", "adapter": "Ethernet"}],
    }
    html = generate_html(network_info_data=info)
    assert "10.0.0.5" in html


def test_network_info_none_shows_not_collected():
    html = generate_html(network_info_data=None)
    assert "not collected" in html


def test_network_info_adapter_rendered():
    info = {
        "gateway": "", "local_ips": [], "dns_servers": [],
        "adapters": [{"name": "Ethernet0", "type": "Ethernet",
                      "ipv4": "192.168.1.10", "speed_mbps": 1000,
                      "signal_pct": -1, "connected": True}],
    }
    html = generate_html(network_info_data=info)
    assert "Ethernet0" in html
    assert "1000 Mbps" in html


# ── Tests: HTML escaping ──────────────────────────────────────────────────────

def test_xss_in_vendor_is_escaped():
    data = {"devices": [{"ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff",
                          "vendor": "<script>alert(1)</script>",
                          "risk_level": "HIGH", "verdict": "", "remediation": ""}]}
    html = generate_html(module1_data=data)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_xss_in_overall_verdict_is_escaped():
    html = generate_html(overall_verdict="<script>pwned</script>", overall_level="HIGH")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_xss_in_public_ip_is_escaped():
    html = generate_html(diagnostics_data=_diag(public_ip='<img onerror="x">'))
    assert '<img' not in html
    assert "&lt;img" in html


# ── Tests: meta footer ────────────────────────────────────────────────────────

def test_meta_footer_present():
    html = generate_html()
    assert "Offline tool" in html
    assert "No data leaves your machine" in html

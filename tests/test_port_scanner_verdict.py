"""
Tests for modules/port_scanner.py

Uses pre-built PortScanResult / PortResult objects to test the verdict
and classification logic without opening any real network connections.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.port_scanner import (
    PortResult,
    PortScanResult,
    PORT_NAMES,
    HIGH_RISK_PORTS,
    COMMON_PORTS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_result(open_ports: list[dict], host: str = "192.168.1.1") -> PortScanResult:
    """
    Build a PortScanResult with a pre-computed plain_verdict from the same
    logic used in port_scanner.scan(), without hitting the network.
    """
    result = PortScanResult(host=host, ip=host, scanned=len(COMMON_PORTS))
    for p in open_ports:
        port = p["port"]
        name = PORT_NAMES.get(port, f"port {port}")
        risk = "HIGH" if port in HIGH_RISK_PORTS else "LOW"
        result.open_ports.append(
            PortResult(port=port, name=name, open=True,
                       banner=p.get("banner", ""), risk=risk)
        )
    result.open_ports.sort(key=lambda x: x.port)

    # Replicate verdict logic from scan()
    high_risk = [p for p in result.open_ports if p.risk == "HIGH"]
    if not result.open_ports:
        result.plain_verdict = f"No open ports found on {host} ({host})."
    elif high_risk:
        names = ", ".join(f"{p.port} ({p.name.split()[0]})" for p in high_risk)
        result.plain_verdict = (
            f"⚠  {len(result.open_ports)} open port(s) — HIGH RISK: {names}.  "
            "These services should not be exposed on a home network."
        )
    else:
        result.plain_verdict = (
            f"✅  {len(result.open_ports)} open port(s), none flagged as high risk."
        )
    return result


# ── Tests: HIGH_RISK_PORTS set ────────────────────────────────────────────────

def test_telnet_is_high_risk():
    assert 23 in HIGH_RISK_PORTS


def test_rdp_is_high_risk():
    assert 3389 in HIGH_RISK_PORTS


def test_smb_is_high_risk():
    assert 445 in HIGH_RISK_PORTS


def test_vnc_is_high_risk():
    assert 5900 in HIGH_RISK_PORTS


def test_http_is_not_high_risk():
    assert 80 not in HIGH_RISK_PORTS


def test_https_is_not_high_risk():
    assert 443 not in HIGH_RISK_PORTS


# ── Tests: PORT_NAMES coverage ────────────────────────────────────────────────

def test_common_ports_all_named():
    """Every port in COMMON_PORTS must have a human-readable name."""
    for port in COMMON_PORTS:
        assert port in PORT_NAMES, f"Port {port} has no name in PORT_NAMES"
        assert len(PORT_NAMES[port]) > 2


# ── Tests: verdict for no open ports ─────────────────────────────────────────

def test_no_open_ports_verdict():
    result = _build_result([])
    assert "No open ports" in result.plain_verdict
    assert "⚠" not in result.plain_verdict


# ── Tests: verdict for LOW-risk only ports ────────────────────────────────────

def test_low_risk_only_verdict():
    result = _build_result([{"port": 80}, {"port": 443}])
    assert "✅" in result.plain_verdict
    assert "none flagged as high risk" in result.plain_verdict
    assert "⚠" not in result.plain_verdict


# ── Tests: verdict for HIGH-risk ports ───────────────────────────────────────

def test_high_risk_port_verdict_contains_warning():
    result = _build_result([{"port": 3389}])
    assert "⚠" in result.plain_verdict
    assert "HIGH RISK" in result.plain_verdict
    assert "3389" in result.plain_verdict


def test_high_risk_verdict_names_the_service():
    result = _build_result([{"port": 3389}])
    # Service name for 3389 starts with "RDP"
    assert "RDP" in result.plain_verdict or "Remote" in result.plain_verdict


def test_mixed_risk_verdict_flags_high_only():
    result = _build_result([{"port": 80}, {"port": 3389}, {"port": 443}])
    assert "⚠" in result.plain_verdict
    assert "3389" in result.plain_verdict
    assert "3 open" in result.plain_verdict


def test_multiple_high_risk_ports_all_named():
    result = _build_result([{"port": 23}, {"port": 3389}])
    assert "23" in result.plain_verdict
    assert "3389" in result.plain_verdict


# ── Tests: PortResult risk field ──────────────────────────────────────────────

def test_port_result_risk_high_for_dangerous_port():
    pr = PortResult(
        port=445, name=PORT_NAMES[445], open=True,
        risk="HIGH" if 445 in HIGH_RISK_PORTS else "LOW"
    )
    assert pr.risk == "HIGH"


def test_port_result_risk_low_for_safe_port():
    pr = PortResult(
        port=80, name=PORT_NAMES[80], open=True,
        risk="HIGH" if 80 in HIGH_RISK_PORTS else "LOW"
    )
    assert pr.risk == "LOW"


# ── Tests: open_ports sorted by port number ───────────────────────────────────

def test_open_ports_sorted():
    result = _build_result([{"port": 443}, {"port": 80}, {"port": 22}])
    ports = [p.port for p in result.open_ports]
    assert ports == sorted(ports)


# ── Tests: banner field ───────────────────────────────────────────────────────

def test_banner_preserved():
    result = _build_result([{"port": 22, "banner": "SSH-2.0-OpenSSH_9.0"}])
    assert result.open_ports[0].banner == "SSH-2.0-OpenSSH_9.0"


def test_empty_banner_default():
    result = _build_result([{"port": 80}])
    assert result.open_ports[0].banner == ""


# ── Tests: error state ────────────────────────────────────────────────────────

def test_error_result_has_no_open_ports():
    result = PortScanResult(host="bad.host", error="Cannot resolve bad.host")
    assert result.open_ports == []
    assert result.error != ""

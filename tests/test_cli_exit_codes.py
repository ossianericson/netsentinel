"""
Behavioural tests for cli.py — exit-code contract.

Exit codes:
  0  → scan completed, no HIGH-RISK devices
  2  → scan completed, at least one HIGH-RISK device found

All network calls, file writes, and subprocess calls are mocked.
sys.exit is intercepted via pytest.raises(SystemExit).
"""

import sys
import os
import types
import argparse
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_device(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff",
                 risk="LOW", hostname="", vendor="ACME"):
    return types.SimpleNamespace(
        ip=ip, mac=mac, risk_level=risk,
        hostname=hostname, vendor=vendor,
        device_type="", verdict="", remediation="",
    )


def _make_scan_data(devices, high_risk_count=None):
    if high_risk_count is None:
        high_risk_count = sum(1 for d in devices if d.risk_level == "HIGH")
    return {
        "devices": devices,
        "high_risk_count": high_risk_count,
        "total_count": len(devices),
        "plain_verdict": f"{high_risk_count} HIGH-RISK device(s) found."
                         if high_risk_count else "All clear.",
    }


def _make_args(
    cidr=None,
    format="html",
    output=None,
    quiet=True,
    verbose=False,
    ipv6=False,
):
    return argparse.Namespace(
        cidr=cidr,
        format=format,
        output=output or "netsentinel_test.html",
        quiet=quiet,
        verbose=verbose,
        ipv6=ipv6,
    )


# ── Patch context for cmd_scan ────────────────────────────────────────────────

def _scan_patches(scan_data: dict):
    """
    Return a dict of patches needed to run cmd_scan() without any network
    or disk access.  scan_data is the dict returned by m1_scan().
    """
    return {
        "modules.utils.flush_network_caches":  MagicMock(return_value=[]),
        "modules.utils.get_local_ip":          MagicMock(return_value="192.168.1.5"),
        "modules.utils.ping_sweep_subnet":     MagicMock(return_value=[]),
        "modules.utils.ping_sweep_cidr":       MagicMock(return_value=[]),
        "modules.rogue_device.scan":           MagicMock(return_value=scan_data),
        "modules.report_exporter.generate_html":
            MagicMock(return_value="<html>test</html>"),
        "modules.report_exporter.generate_json":
            MagicMock(return_value='{"test": true}'),
        "modules.report_exporter.generate_csv_devices":
            MagicMock(return_value="ip,mac\n"),
        "pathlib.Path.write_text": MagicMock(),
    }


def _run_cmd_scan(args, scan_data):
    from cli import cmd_scan

    patches = _scan_patches(scan_data)

    with patch("modules.utils.flush_network_caches",
               patches["modules.utils.flush_network_caches"]), \
         patch("modules.utils.get_local_ip",
               patches["modules.utils.get_local_ip"]), \
         patch("modules.utils.ping_sweep_subnet",
               patches["modules.utils.ping_sweep_subnet"]), \
         patch("modules.utils.ping_sweep_cidr",
               patches["modules.utils.ping_sweep_cidr"]), \
         patch("modules.rogue_device.scan",
               patches["modules.rogue_device.scan"]), \
         patch("modules.report_exporter.generate_html",
               patches["modules.report_exporter.generate_html"]), \
         patch("modules.report_exporter.generate_json",
               patches["modules.report_exporter.generate_json"]), \
         patch("modules.report_exporter.generate_csv_devices",
               patches["modules.report_exporter.generate_csv_devices"]), \
         patch("pathlib.Path.write_text",
               patches["pathlib.Path.write_text"]):
        with pytest.raises(SystemExit) as exc_info:
            cmd_scan(args)

    return exc_info.value.code


# ── Exit-code 0: no HIGH-RISK devices ────────────────────────────────────────

class TestExitCodeNoHighRisk:
    def test_exit_0_when_no_high_risk_devices(self):
        devices = [
            _make_device(ip="192.168.1.1", risk="LOW"),
            _make_device(ip="192.168.1.2", risk="MEDIUM"),
        ]
        scan_data = _make_scan_data(devices, high_risk_count=0)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 0

    def test_exit_0_when_empty_device_list(self):
        scan_data = _make_scan_data([], high_risk_count=0)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 0

    def test_exit_0_with_only_clean_devices(self):
        devices = [_make_device(risk="CLEAN") for _ in range(5)]
        scan_data = _make_scan_data(devices, high_risk_count=0)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 0

    def test_exit_0_with_json_format(self):
        devices = [_make_device(risk="LOW")]
        scan_data = _make_scan_data(devices, high_risk_count=0)
        code = _run_cmd_scan(_make_args(format="json", output="out.json"), scan_data)
        assert code == 0

    def test_exit_0_with_csv_format(self):
        devices = [_make_device(risk="LOW")]
        scan_data = _make_scan_data(devices, high_risk_count=0)
        code = _run_cmd_scan(_make_args(format="csv", output="out.csv"), scan_data)
        assert code == 0


# ── Exit-code 2: HIGH-RISK devices present ────────────────────────────────────

class TestExitCodeHighRisk:
    def test_exit_2_when_one_high_risk_device(self):
        devices = [_make_device(ip="192.168.1.99", risk="HIGH")]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 2

    def test_exit_2_when_multiple_high_risk_devices(self):
        devices = [_make_device(ip=f"192.168.1.{i}", risk="HIGH") for i in range(3)]
        scan_data = _make_scan_data(devices, high_risk_count=3)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 2

    def test_exit_2_with_mixed_risk_levels(self):
        devices = [
            _make_device(ip="192.168.1.1", risk="LOW"),
            _make_device(ip="192.168.1.2", risk="HIGH"),
            _make_device(ip="192.168.1.3", risk="MEDIUM"),
        ]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code == 2

    def test_exit_2_not_0_when_high_risk(self):
        devices = [_make_device(risk="HIGH")]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(), scan_data)
        assert code != 0

    def test_exit_2_with_cidr_scan(self):
        devices = [_make_device(risk="HIGH")]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(cidr="10.0.0.0/24"), scan_data)
        assert code == 2

    def test_exit_2_with_json_format(self):
        devices = [_make_device(risk="HIGH")]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(format="json", output="out.json"), scan_data)
        assert code == 2

    def test_exit_2_with_csv_format(self):
        devices = [_make_device(risk="HIGH")]
        scan_data = _make_scan_data(devices, high_risk_count=1)
        code = _run_cmd_scan(_make_args(format="csv", output="out.csv"), scan_data)
        assert code == 2


# ── Exit-code 1: invalid format ──────────────────────────────────────────────

class TestExitCodeError:
    def test_exit_1_on_unknown_format(self):
        devices = []
        scan_data = _make_scan_data(devices, high_risk_count=0)
        # Unknown format should call sys.exit(1) before reaching the high-risk check
        with patch("modules.utils.flush_network_caches", return_value=[]), \
             patch("modules.utils.get_local_ip", return_value="192.168.1.1"), \
             patch("modules.utils.ping_sweep_subnet", return_value=[]), \
             patch("modules.rogue_device.scan", return_value=scan_data):
            from cli import cmd_scan
            with pytest.raises(SystemExit) as exc_info:
                cmd_scan(_make_args(format="xml_invalid", output="out.xyz"))
        assert exc_info.value.code == 1

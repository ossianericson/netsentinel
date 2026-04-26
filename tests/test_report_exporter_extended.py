"""
Behavioural tests for modules/report_exporter.py

Covers JSON and CSV output — verifying that expected fields are present
and that data round-trips correctly.

The existing test_report_exporter.py covers generate_html(); these tests
cover generate_json() and generate_csv_devices().

No network, no file I/O, no GUI required.
"""

import csv
import io
import json
import sys
import os
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.report_exporter import generate_json, generate_csv_devices


# ── Helpers ───────────────────────────────────────────────────────────────────

def _device(**kwargs):
    defaults = {
        "ip": "192.168.1.10",
        "mac": "aa:bb:cc:dd:ee:ff",
        "hostname": "myhost",
        "vendor": "ACME Corp",
        "device_type": "Router",
        "os_family": "Linux",
        "risk_level": "HIGH",
        "connection_type": "Ethernet",
        "known_issues": ["STP BPDU injection"],
        "verdict": "Rogue root bridge candidate",
        "remediation": "Disconnect Ethernet",
        "forum_ref": "https://example.com/ref",
    }
    defaults.update(kwargs)
    return defaults


def _module1(devices=None, high_risk=1):
    devs = devices if devices is not None else [_device()]
    return {
        "devices": devs,
        "high_risk_count": high_risk,
        "total_count": len(devs),
        "plain_verdict": "1 HIGH-RISK device found.",
    }


# ── generate_json: top-level structure ───────────────────────────────────────

class TestGenerateJsonStructure:
    def test_returns_valid_json(self):
        output = generate_json()
        parsed = json.loads(output)  # must not raise
        assert isinstance(parsed, dict)

    def test_contains_generated_at(self):
        parsed = json.loads(generate_json())
        assert "generated_at" in parsed
        assert parsed["generated_at"]  # non-empty

    def test_contains_tool_field(self):
        parsed = json.loads(generate_json())
        assert parsed.get("tool") == "NetSentinel"

    def test_contains_overall_verdict(self):
        parsed = json.loads(generate_json(overall_verdict="All clear", overall_level="CLEAN"))
        assert parsed["overall_verdict"] == "All clear"
        assert parsed["overall_level"] == "CLEAN"

    def test_no_module1_means_no_devices_key(self):
        parsed = json.loads(generate_json(module1_data=None))
        assert "devices" not in parsed


# ── generate_json: device fields ─────────────────────────────────────────────

class TestGenerateJsonDevices:
    def test_devices_array_present(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert "devices" in parsed
        assert isinstance(parsed["devices"], list)

    def test_device_ip_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["ip"] == "192.168.1.10"

    def test_device_mac_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["mac"] == "aa:bb:cc:dd:ee:ff"

    def test_device_risk_level_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["risk_level"] == "HIGH"

    def test_device_vendor_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["vendor"] == "ACME Corp"

    def test_device_verdict_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["verdict"] == "Rogue root bridge candidate"

    def test_device_remediation_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["remediation"] == "Disconnect Ethernet"

    def test_device_hostname_field(self):
        parsed = json.loads(generate_json(module1_data=_module1()))
        assert parsed["devices"][0]["hostname"] == "myhost"

    def test_high_risk_count_field(self):
        parsed = json.loads(generate_json(module1_data=_module1(high_risk=3)))
        assert parsed["high_risk_count"] == 3

    def test_total_devices_field(self):
        devs = [_device(ip=f"192.168.1.{i}") for i in range(5)]
        parsed = json.loads(generate_json(module1_data=_module1(devices=devs)))
        assert parsed["total_devices"] == 5

    def test_multiple_devices_all_present(self):
        devs = [
            _device(ip="192.168.1.1", mac="aa:aa:aa:aa:aa:01"),
            _device(ip="192.168.1.2", mac="aa:aa:aa:aa:aa:02"),
            _device(ip="192.168.1.3", mac="aa:aa:aa:aa:aa:03"),
        ]
        parsed = json.loads(generate_json(module1_data=_module1(devices=devs)))
        ips = [d["ip"] for d in parsed["devices"]]
        assert "192.168.1.1" in ips
        assert "192.168.1.2" in ips
        assert "192.168.1.3" in ips

    def test_credentials_not_in_json_output(self):
        """Credentials must never appear in report output."""
        parsed = json.loads(generate_json(module1_data=_module1()))
        output_str = json.dumps(parsed)
        for sensitive in ("password", "ssh_key", "private_key", "secret", "credential"):
            assert sensitive not in output_str.lower()


# ── generate_json: namespace objects (not plain dicts) ───────────────────────

class TestGenerateJsonNamespaceDevices:
    """generate_json must handle DeviceInfo-style objects via getattr()."""

    def _ns_device(self):
        return types.SimpleNamespace(
            ip="10.0.0.5",
            mac="bb:cc:dd:ee:ff:00",
            hostname="server01",
            vendor="Dell",
            device_type="Server",
            os_family="Linux",
            risk_level="MEDIUM",
            connection_type="Ethernet",
            known_issues=[],
            verdict="No issues",
            remediation="",
            forum_ref="",
        )

    def test_namespace_device_ip(self):
        data = {"devices": [self._ns_device()], "high_risk_count": 0, "total_count": 1,
                "plain_verdict": ""}
        parsed = json.loads(generate_json(module1_data=data))
        assert parsed["devices"][0]["ip"] == "10.0.0.5"

    def test_namespace_device_risk_level(self):
        data = {"devices": [self._ns_device()], "high_risk_count": 0, "total_count": 1,
                "plain_verdict": ""}
        parsed = json.loads(generate_json(module1_data=data))
        assert parsed["devices"][0]["risk_level"] == "MEDIUM"


# ── generate_csv_devices: header ─────────────────────────────────────────────

class TestGenerateCsvHeader:
    def _parse(self, data):
        raw = generate_csv_devices(data)
        return list(csv.reader(io.StringIO(raw)))

    def test_first_row_is_header(self):
        rows = self._parse(_module1())
        assert rows[0][0] == "IP Address"

    def test_header_contains_required_columns(self):
        rows = self._parse(_module1())
        header = rows[0]
        for col in ("IP Address", "MAC Address", "Vendor", "Risk Level",
                    "Verdict", "Remediation", "Hostname"):
            assert col in header, f"Missing column: {col}"

    def test_empty_module1_produces_header_only(self):
        rows = self._parse({"devices": [], "high_risk_count": 0})
        assert len(rows) == 1  # header row, no data rows


# ── generate_csv_devices: data rows ──────────────────────────────────────────

class TestGenerateCsvData:
    def _parse(self, data):
        raw = generate_csv_devices(data)
        reader = csv.DictReader(io.StringIO(raw))
        return list(reader)

    def test_one_row_per_device(self):
        devs = [_device(ip=f"192.168.1.{i}") for i in range(3)]
        rows = self._parse(_module1(devices=devs))
        assert len(rows) == 3

    def test_ip_address_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["IP Address"] == "192.168.1.10"

    def test_mac_address_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["MAC Address"] == "aa:bb:cc:dd:ee:ff"

    def test_vendor_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["Vendor"] == "ACME Corp"

    def test_risk_level_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["Risk Level"] == "HIGH"

    def test_verdict_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["Verdict"] == "Rogue root bridge candidate"

    def test_remediation_in_row(self):
        rows = self._parse(_module1())
        assert rows[0]["Remediation"] == "Disconnect Ethernet"

    def test_known_issues_pipe_separated(self):
        dev = _device(known_issues=["Issue A", "Issue B"])
        rows = self._parse(_module1(devices=[dev]))
        assert "Issue A" in rows[0]["Known Issues"]
        assert "Issue B" in rows[0]["Known Issues"]

    def test_credentials_not_in_csv_output(self):
        """Credentials must never appear in CSV report output."""
        raw = generate_csv_devices(_module1())
        for sensitive in ("password", "ssh_key", "private_key", "secret", "credential"):
            assert sensitive not in raw.lower()

    def test_none_module1_returns_header_only(self):
        raw = generate_csv_devices(None)
        rows = list(csv.reader(io.StringIO(raw)))
        assert len(rows) == 1


# ── generate_html: credential-free guarantee (integration) ───────────────────

class TestHtmlCredentialFree:
    def test_html_contains_no_credential_fields(self):
        from modules.report_exporter import generate_html
        dev = _device()
        data = _module1(devices=[dev])
        html = generate_html(module1_data=data)
        for sensitive in ("password", "ssh_key", "private_key"):
            assert sensitive not in html.lower()

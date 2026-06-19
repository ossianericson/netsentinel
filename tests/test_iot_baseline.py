"""
Tests for modules/iot_baseline.py

Tests cover:
  - DeviceBaseline and IoTAlert dataclass instantiation
  - _load_baselines / _save_baselines round-trip (pure I/O, no network)
  - IoTMonitor instantiation (no sniff started)
  - inject_into_assessment correctly updates a mock assessment
  - IOT_DEVICE_TYPES set is non-empty and contains expected labels

No network, no Scapy sniff, no file writes outside tmp (pytest tmp_path fixture).
"""

import sys
import os
import types
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.iot_baseline import (
    DeviceBaseline,
    IoTAlert,
    IoTMonitor,
    IOT_DEVICE_TYPES,
    _devices_to_monitor,
    _load_baselines,
    _save_baselines,
    inject_into_assessment,
)


# ── DeviceBaseline ────────────────────────────────────────────────────────────

class TestDeviceBaseline:
    def _make(self, **kwargs):
        defaults = dict(
            mac="aa:bb:cc:dd:ee:ff",
            ip="192.168.1.50",
            device_type="Smart TV",
            vendor="Samsung",
            model="Samsung Smart TV",
        )
        defaults.update(kwargs)
        return DeviceBaseline(**defaults)

    def test_basic_creation(self):
        b = self._make()
        assert b.mac == "aa:bb:cc:dd:ee:ff"
        assert b.ip == "192.168.1.50"
        assert b.device_type == "Smart TV"

    def test_default_fields(self):
        b = self._make()
        assert b.known_ips == []
        assert b.known_ports == []
        assert b.avg_pps == 0.0
        assert b.learned_at == ""
        assert b.sample_seconds == 0

    def test_can_set_known_ports(self):
        b = self._make(known_ports=[80, 443, 8080], avg_pps=1.5, sample_seconds=120)
        assert 443 in b.known_ports
        assert b.avg_pps == 1.5


# ── IoTAlert ─────────────────────────────────────────────────────────────────

class TestIoTAlert:
    def _make(self, **kwargs):
        defaults = dict(
            mac="aa:bb:cc:dd:ee:ff",
            ip="192.168.1.50",
            device_label="Samsung Smart TV [192.168.1.50]",
            alert_type="NEW_DEST",
            severity="HIGH",
            detail="Device contacted unexpected external IP",
            remediation="Isolate the device on a guest network.",
        )
        defaults.update(kwargs)
        return IoTAlert(**defaults)

    def test_basic_creation(self):
        a = self._make()
        assert a.mac == "aa:bb:cc:dd:ee:ff"
        assert a.alert_type == "NEW_DEST"
        assert a.severity == "HIGH"

    def test_timestamp_auto_set(self):
        a = self._make()
        # Should be a valid ISO-like timestamp
        assert len(a.timestamp) >= 10
        assert "T" in a.timestamp

    def test_alert_types(self):
        for atype in ("NEW_DEST", "NEW_PORT", "METADATA_PROBE", "SYN_SCAN", "RATE_SPIKE"):
            a = self._make(alert_type=atype)
            assert a.alert_type == atype

    def test_severity_values(self):
        for sev in ("CRITICAL", "HIGH", "MEDIUM"):
            a = self._make(severity=sev)
            assert a.severity == sev


# ── Persistence round-trip ────────────────────────────────────────────────────

class TestPersistence:
    def _make_baseline(self, mac="aa:bb:cc:00:00:01", ip="192.168.1.10"):
        return DeviceBaseline(
            mac=mac, ip=ip,
            device_type="Smart Speaker",
            vendor="Google",
            model="Google Nest Audio",
            known_ips=["192.168.1.10"],
            known_ports=[443, 5228],
            avg_pps=2.3,
            learned_at="2025-01-01T00:00:00",
            sample_seconds=300,
        )

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "iot_baseline.json"
        original = {"aa:bb:cc:00:00:01": self._make_baseline()}
        _save_baselines(original, path)
        loaded = _load_baselines(path)
        assert "aa:bb:cc:00:00:01" in loaded
        restored = loaded["aa:bb:cc:00:00:01"]
        assert restored.mac == "aa:bb:cc:00:00:01"
        assert restored.ip == "192.168.1.10"
        assert restored.vendor == "Google"
        assert 443 in restored.known_ports
        assert restored.avg_pps == pytest.approx(2.3)

    def test_save_creates_parent_dirs(self, tmp_path):
        deep_path = tmp_path / "a" / "b" / "c" / "baseline.json"
        _save_baselines({}, deep_path)
        assert deep_path.exists()

    def test_load_missing_file_returns_empty(self, tmp_path):
        result = _load_baselines(tmp_path / "does_not_exist.json")
        assert result == {}

    def test_load_corrupt_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json", encoding="utf-8")
        result = _load_baselines(path)
        assert result == {}

    def test_round_trip_multiple_devices(self, tmp_path):
        path = tmp_path / "multi.json"
        baselines = {
            f"aa:bb:cc:00:00:{i:02x}": self._make_baseline(
                mac=f"aa:bb:cc:00:00:{i:02x}",
                ip=f"192.168.1.{i}",
            )
            for i in range(1, 6)
        }
        _save_baselines(baselines, path)
        loaded = _load_baselines(path)
        assert len(loaded) == 5
        for mac in baselines:
            assert mac in loaded


# ── IoTMonitor instantiation ──────────────────────────────────────────────────

class TestIoTMonitorInit:
    def _make_baseline(self, mac, ip):
        return DeviceBaseline(
            mac=mac, ip=ip,
            device_type="IP Camera",
            vendor="Arlo", model="Arlo Pro 4",
        )

    def test_can_be_created_without_sniff(self):
        alerts = []
        monitor = IoTMonitor(
            baselines={},
            on_alert=alerts.append,
        )
        assert monitor is not None

    def test_ip_to_mac_mapping_built(self):
        baselines = {
            "aa:bb:cc:00:00:01": self._make_baseline("aa:bb:cc:00:00:01", "192.168.1.10"),
            "aa:bb:cc:00:00:02": self._make_baseline("aa:bb:cc:00:00:02", "192.168.1.11"),
        }
        monitor = IoTMonitor(baselines=baselines, on_alert=lambda a: None)
        assert monitor._ip_to_mac.get("192.168.1.10") == "aa:bb:cc:00:00:01"
        assert monitor._ip_to_mac.get("192.168.1.11") == "aa:bb:cc:00:00:02"

    def test_stop_sets_stop_event(self):
        import threading
        ev = threading.Event()
        monitor = IoTMonitor(baselines={}, on_alert=lambda a: None, stop_event=ev)
        monitor.stop()
        assert ev.is_set()


# ── inject_into_assessment ────────────────────────────────────────────────────

class TestInjectIntoAssessment:
    def _make_assessment(self):
        return types.SimpleNamespace(
            findings=[],
            total_score=10,
            severity="LOW",
            plain_summary="All clear.",
        )

    def _make_alert(self, severity="HIGH", alert_type="NEW_DEST"):
        return IoTAlert(
            mac="aa:bb:cc:dd:ee:ff",
            ip="192.168.1.50",
            device_label="Smart TV [192.168.1.50]",
            alert_type=alert_type,
            severity=severity,
            detail="Unexpected connection detected.",
            remediation="Isolate the device.",
        )

    def test_adds_findings(self):
        assessment = self._make_assessment()
        inject_into_assessment(assessment, [self._make_alert()])
        assert len(assessment.findings) == 1

    def test_raises_total_score(self):
        assessment = self._make_assessment()
        inject_into_assessment(assessment, [self._make_alert(severity="HIGH")])
        assert assessment.total_score > 10

    def test_critical_alert_sets_severity(self):
        assessment = self._make_assessment()
        inject_into_assessment(assessment, [self._make_alert(severity="CRITICAL")])
        assert assessment.severity == "CRITICAL"

    def test_total_score_capped_at_100(self):
        assessment = self._make_assessment()
        assessment.total_score = 90
        many_alerts = [self._make_alert(severity="CRITICAL") for _ in range(10)]
        inject_into_assessment(assessment, many_alerts)
        assert assessment.total_score == 100

    def test_updates_plain_summary(self):
        assessment = self._make_assessment()
        inject_into_assessment(assessment, [self._make_alert()])
        assert "IoT" in assessment.plain_summary or "COMPROMISED" in assessment.plain_summary

    def test_no_alerts_no_change(self):
        assessment = self._make_assessment()
        original_score = assessment.total_score
        inject_into_assessment(assessment, [])
        assert assessment.total_score == original_score
        assert assessment.findings == []


# ── IOT_DEVICE_TYPES set ──────────────────────────────────────────────────────

class TestIotDeviceTypes:
    def test_is_a_set(self):
        assert isinstance(IOT_DEVICE_TYPES, set)

    def test_non_empty(self):
        assert len(IOT_DEVICE_TYPES) >= 5

    def test_contains_expected_types(self):
        expected = {"Smart TV", "Smart Speaker", "IP Camera", "IoT Device", "Streaming Stick"}
        for t in expected:
            assert t in IOT_DEVICE_TYPES, f"{t!r} not in IOT_DEVICE_TYPES"


# ── _devices_to_monitor (S5-5: extend baselining to all device types) ────────

class TestDevicesToMonitor:
    def test_includes_non_iot_device_types(self):
        devices = [
            {"ip": "192.168.1.20", "mac": "aa:bb:cc:00:00:20",
             "device_type": "Windows/Mac/Linux PC", "vendor": "Dell"},
        ]
        ip_to_mac, ip_to_dtype, _, _ = _devices_to_monitor(devices)
        assert ip_to_mac == {"192.168.1.20": "aa:bb:cc:00:00:20"}
        assert ip_to_dtype["192.168.1.20"] == "Windows/Mac/Linux PC"

    def test_includes_classic_iot_types_too(self):
        devices = [
            {"ip": "192.168.1.21", "mac": "aa:bb:cc:00:00:21",
             "device_type": "Smart TV", "vendor": "Sony"},
        ]
        ip_to_mac, _, _, _ = _devices_to_monitor(devices)
        assert "192.168.1.21" in ip_to_mac

    def test_excludes_devices_missing_ip_or_mac(self):
        devices = [
            {"ip": "", "mac": "aa:bb:cc:00:00:22", "device_type": "Smart TV"},
            {"ip": "192.168.1.23", "mac": "", "device_type": "Smart TV"},
        ]
        ip_to_mac, _, _, _ = _devices_to_monitor(devices)
        assert ip_to_mac == {}

    def test_works_with_object_attributes(self):
        dev = types.SimpleNamespace(
            ip="192.168.1.24", mac="aa:bb:cc:00:00:24",
            device_type="Android/iOS Mobile", vendor="Google", model="Pixel",
        )
        ip_to_mac, ip_to_dtype, ip_to_vendor, ip_to_model = _devices_to_monitor([dev])
        assert ip_to_mac["192.168.1.24"] == "aa:bb:cc:00:00:24"
        assert ip_to_dtype["192.168.1.24"] == "Android/iOS Mobile"
        assert ip_to_vendor["192.168.1.24"] == "Google"
        assert ip_to_model["192.168.1.24"] == "Pixel"

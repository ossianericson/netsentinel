"""
Tests for modules/scheduler.py — diff logic and data classes.
No network calls — scan functions are mocked out.
"""
import time
import threading
import pytest
from unittest.mock import MagicMock, patch
from modules.scheduler import ScanScheduler, ScheduledScanResult, _notify


# ── ScheduledScanResult ────────────────────────────────────────────────────────

class TestScheduledScanResult:
    def test_defaults(self):
        r = ScheduledScanResult()
        assert r.new_devices == []
        assert r.changed_devices == []
        assert r.total_devices == 0
        assert r.scan_data == {}
        assert r.timestamp > 0

    def test_custom_values(self):
        r = ScheduledScanResult(
            new_devices=[{"mac": "aa:bb:cc:dd:ee:ff", "ip": "10.0.0.5"}],
            total_devices=3,
        )
        assert len(r.new_devices) == 1
        assert r.total_devices == 3


# ── ScanScheduler.__init__ ────────────────────────────────────────────────────

class TestScanSchedulerInit:
    def test_default_interval(self):
        s = ScanScheduler()
        assert s.interval_s == 15 * 60

    def test_custom_interval(self):
        s = ScanScheduler(interval_minutes=5)
        assert s.interval_s == 300

    def test_callbacks_default_to_noop(self):
        s = ScanScheduler()
        # Should not raise
        s.on_result(ScheduledScanResult())
        s.on_alert("title", "msg")
        s.on_status("status")

    def test_custom_callbacks(self):
        results = []
        alerts = []
        s = ScanScheduler(
            on_result=lambda r: results.append(r),
            on_alert=lambda t, m: alerts.append((t, m)),
        )
        s.on_result(ScheduledScanResult())
        s.on_alert("New device", "aa:bb:cc")
        assert len(results) == 1
        assert alerts[0][0] == "New device"

    def test_stop_event_provided(self):
        ev = threading.Event()
        s = ScanScheduler(stop_event=ev)
        assert s.stop_event is ev


# ── ScanScheduler._diff ────────────────────────────────────────────────────────

class TestScanSchedulerDiff:
    def _make_scheduler(self):
        return ScanScheduler(notify_desktop=False)

    def test_diff_empty_baseline_all_new(self):
        s = self._make_scheduler()
        s._baseline = {}
        scan_data = {
            "devices": [
                {"mac": "aa:bb:cc:11:22:33", "ip": "192.168.1.10",
                 "hostname": "pc1", "vendor": "Dell", "risk_level": "CLEAN"},
            ]
        }
        with patch("modules.utils.diff_devices_against_baseline",
                   return_value=[{"mac": "aa:bb:cc:11:22:33", "ip": "192.168.1.10"}]):
            result = s._diff(scan_data)
        assert result.total_devices == 1
        assert isinstance(result, ScheduledScanResult)

    def test_diff_no_changes_empty_result(self):
        s = self._make_scheduler()
        s._baseline = {"aa:bb:cc:11:22:33": {"mac": "aa:bb:cc:11:22:33", "ip": "192.168.1.10"}}
        scan_data = {
            "devices": [
                {"mac": "aa:bb:cc:11:22:33", "ip": "192.168.1.10",
                 "hostname": "pc1", "vendor": "Dell", "risk_level": "CLEAN"},
            ]
        }
        with patch("modules.utils.diff_devices_against_baseline", return_value=[]):
            result = s._diff(scan_data)
        assert result.new_devices == []
        assert result.changed_devices == []

    def test_diff_detects_ip_change(self):
        s = self._make_scheduler()
        mac = "aa:bb:cc:11:22:33"
        s._baseline = {mac: {"mac": mac, "ip": "192.168.1.10"}}
        scan_data = {
            "devices": [
                {"mac": mac, "ip": "192.168.1.99",  # IP changed
                 "hostname": "pc1", "vendor": "Dell", "risk_level": "CLEAN"},
            ]
        }
        with patch("modules.utils.diff_devices_against_baseline", return_value=[]):
            result = s._diff(scan_data)
        assert len(result.changed_devices) == 1
        assert result.changed_devices[0]["prev_ip"] == "192.168.1.10"
        assert result.changed_devices[0]["ip"] == "192.168.1.99"

    def test_diff_handles_dataclass_devices(self):
        """_diff must handle both dict and dataclass device objects."""
        from modules.rogue_device import DeviceInfo
        s = self._make_scheduler()
        s._baseline = {}
        device = DeviceInfo(ip="10.0.0.1", mac="de:ad:be:ef:00:01", vendor="Acme")
        scan_data = {"devices": [device]}
        with patch("modules.utils.diff_devices_against_baseline", return_value=[]):
            result = s._diff(scan_data)
        assert result.total_devices == 1


# ── ScanScheduler._alert ──────────────────────────────────────────────────────

class TestScanSchedulerAlert:
    def test_alert_fires_callback_for_new_devices(self):
        alerts = []
        s = ScanScheduler(
            on_alert=lambda t, m: alerts.append((t, m)),
            notify_desktop=False,
        )
        result = ScheduledScanResult(
            new_devices=[{"mac": "aa:bb:cc:11:22:33", "ip": "10.0.0.5"}]
        )
        s._alert(result)
        assert len(alerts) == 1
        assert "new device" in alerts[0][0].lower()

    def test_alert_fires_for_ip_change(self):
        alerts = []
        s = ScanScheduler(
            on_alert=lambda t, m: alerts.append((t, m)),
            notify_desktop=False,
        )
        result = ScheduledScanResult(
            changed_devices=[{"mac": "aa:bb:cc:11:22:33", "ip": "10.0.0.99",
                               "prev_ip": "10.0.0.5"}]
        )
        s._alert(result)
        assert len(alerts) == 1
        assert "IP changed" in alerts[0][0]

    def test_alert_silent_when_no_changes(self):
        alerts = []
        s = ScanScheduler(
            on_alert=lambda t, m: alerts.append((t, m)),
            notify_desktop=False,
        )
        s._alert(ScheduledScanResult())
        assert alerts == []

    def test_no_desktop_notify_when_disabled(self):
        """notify_desktop=False must not call _notify."""
        s = ScanScheduler(notify_desktop=False)
        with patch("modules.scheduler._notify") as mock_notify:
            result = ScheduledScanResult(
                new_devices=[{"mac": "de:ad:be:ef:00:01"}]
            )
            s._alert(result)
            mock_notify.assert_not_called()


# ── _notify — best-effort, must never raise ───────────────────────────────────

class TestNotify:
    def test_notify_does_not_raise_on_any_platform(self):
        """_notify must swallow all errors silently."""
        with patch("subprocess.run", side_effect=Exception("subprocess failed")):
            _notify("Test Title", "Test message")  # must not raise

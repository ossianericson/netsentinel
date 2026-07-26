"""
Phase 2.4 -- wire the dead tray/notify_device_gone toggle.

Its sibling, tray/notify_new_device, was already read and honoured in
_m1_track_devices() (ui/scan_wiring.py) for tr.new_devices. tray/notify_device_gone
existed in Settings but nothing ever read it -- a dead toggle. Mirror the
new-device pattern for the gone-devices branch.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.scan_wiring import ScanResultMixin  # noqa: E402

from modules.device_tracker import TrackedDevice, TrackerResult


class _FakeDeviceTracker:
    def __init__(self, store) -> None:
        self._store = store

    def process_scan(self, devices, known=None):
        return TrackerResult(gone_devices=[
            TrackedDevice(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.50",
                          hostname="", vendor="Acme", device_type=""),
        ])


class _FakeAlertEngine:
    def evaluate_tracker_result(self, tr):
        return []

    def evaluate_ip_churn_checks(self, churn):
        return []


class _FakeTray:
    def __init__(self, available=True) -> None:
        self._available = available
        self.balloons: list = []
        self.badge = 0

    def is_available(self) -> bool:
        return self._available

    def show_notification(self, title, message, severity="INFO", on_click=None) -> None:
        self.balloons.append((title, message, severity))

    def increment_badge(self) -> None:
        self.badge += 1


class _Stub(ScanResultMixin):
    pass


def _make_stub(tray):
    from unittest.mock import MagicMock
    stub = _Stub()
    stub._store = MagicMock()
    stub._alert_engine = _FakeAlertEngine()
    stub._tray_manager = tray
    stub._home_page = MagicMock()
    stub._mqtt_page = MagicMock()
    stub._set_status = MagicMock()
    stub._surface_alert_in_app = MagicMock()
    return stub


def _set_toggle(value: bool):
    from PyQt6.QtCore import QSettings
    qs = QSettings("NetSentinel", "NetSentinel")
    had = qs.contains("tray/notify_device_gone")
    prior = qs.value("tray/notify_device_gone", False, type=bool)
    qs.setValue("tray/notify_device_gone", value)
    return qs, had, prior


def _restore_toggle(qs, had, prior):
    if had:
        qs.setValue("tray/notify_device_gone", prior)
    else:
        qs.remove("tray/notify_device_gone")


def test_no_balloon_when_toggle_off(monkeypatch):
    monkeypatch.setattr("modules.device_tracker.DeviceTracker", _FakeDeviceTracker)
    qs, had, prior = _set_toggle(False)
    try:
        stub = _make_stub(_FakeTray())
        stub._m1_track_devices({"devices": []})
        assert stub._tray_manager.balloons == []
    finally:
        _restore_toggle(qs, had, prior)


def test_balloon_shown_when_toggle_on(monkeypatch):
    monkeypatch.setattr("modules.device_tracker.DeviceTracker", _FakeDeviceTracker)
    qs, had, prior = _set_toggle(True)
    try:
        stub = _make_stub(_FakeTray())
        stub._m1_track_devices({"devices": []})
        assert len(stub._tray_manager.balloons) == 1
        title, message, severity = stub._tray_manager.balloons[0]
        assert "192.168.1.50" in message
        assert severity == "WARNING"
    finally:
        _restore_toggle(qs, had, prior)

"""
Regression test for critical-UX Phase 1.2: tracker-fired alerts
(NEW_DEVICE/DEVICE_GONE, from AlertEngine.evaluate_tracker_result) were shown
as a toast and pushed to the Home page but never persisted via persist_alert()
-- unlike the sibling IP_CHURN loop six lines below it in the same method
(ui/scan_wiring.py::ScanResultMixin._m1_track_devices). That meant those
alerts landed nowhere the user could act on them later (no row in
alert_fired, invisible to Alert History / the unacked count / the status bar).

RULE-T3: this must fail before the fix (only IP_CHURN alerts persisted;
tracker alerts silently dropped) and pass after.
"""
from __future__ import annotations

import pytest

try:
    from ui.scan_wiring import ScanResultMixin
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.alert_types import AlertFired
from modules.device_tracker import TrackerResult


class _FakeStore:
    """Minimal store stub recording every persisted alert."""

    def __init__(self):
        self.fired_alerts: list = []

    def record_alert_fired(self, rule_name, host, severity, message, ts, rule_type):
        self.fired_alerts.append(
            {"rule_name": rule_name, "host": host, "severity": severity,
             "message": message, "ts": ts, "rule_type": rule_type}
        )
        return len(self.fired_alerts)


class _FakeDeviceTracker:
    """Stands in for modules.device_tracker.DeviceTracker -- process_scan()
    returns a pre-built TrackerResult without touching the real store."""

    def __init__(self, store):
        self._store = store

    def process_scan(self, devices, known=None):
        return TrackerResult(new_devices=[], gone_devices=[])


class _FakeAlertEngine:
    """Returns one NEW_DEVICE-style alert from evaluate_tracker_result and
    nothing from evaluate_ip_churn_checks, isolating the tracker-alert path."""

    def evaluate_tracker_result(self, tr):
        return [AlertFired(
            rule_name="new_device", rule_type="NEW_DEVICE", host="192.168.1.50",
            message="New device joined: 192.168.1.50", severity="INFO", ts=1000,
        )]

    def evaluate_ip_churn_checks(self, churn):
        return []


class _Stub(ScanResultMixin):
    pass


def _make_stub(store, engine):
    from unittest.mock import MagicMock
    stub = _Stub()
    stub._store = store
    stub._alert_engine = engine
    stub._surface_alert_in_app = MagicMock()
    stub._home_page = MagicMock()
    stub._mqtt_page = MagicMock()
    stub._set_status = MagicMock()
    return stub


def test_tracker_alert_is_persisted(monkeypatch):
    monkeypatch.setattr(
        "modules.device_tracker.DeviceTracker", _FakeDeviceTracker
    )
    store = _FakeStore()
    stub = _make_stub(store, _FakeAlertEngine())

    stub._m1_track_devices({"devices": []})

    assert len(store.fired_alerts) == 1, (
        "NEW_DEVICE/DEVICE_GONE tracker alerts must reach alert_fired via "
        "persist_alert(), matching the sibling IP_CHURN loop"
    )
    assert store.fired_alerts[0]["rule_type"] == "NEW_DEVICE"
    assert store.fired_alerts[0]["host"] == "192.168.1.50"


def test_tracker_alert_still_shows_toast_and_home_card(monkeypatch):
    """Persisting must not replace the existing toast/Home-card/MQTT feed."""
    monkeypatch.setattr(
        "modules.device_tracker.DeviceTracker", _FakeDeviceTracker
    )
    store = _FakeStore()
    engine = _FakeAlertEngine()
    stub = _make_stub(store, engine)

    stub._m1_track_devices({"devices": []})

    stub._surface_alert_in_app.assert_called_once()
    stub._home_page.on_alert.assert_called_once()
    stub._mqtt_page.on_alert.assert_called_once()


def test_persist_failure_does_not_break_scan_handler(monkeypatch):
    """persist_alert() raising must be swallowed, matching the IP_CHURN
    loop's non-fatal try/except shape -- a DB error must never crash the
    scan handler."""
    monkeypatch.setattr(
        "modules.device_tracker.DeviceTracker", _FakeDeviceTracker
    )

    class _BrokenStore(_FakeStore):
        def record_alert_fired(self, *a, **kw):
            raise RuntimeError("db locked")

    store = _BrokenStore()
    stub = _make_stub(store, _FakeAlertEngine())

    stub._m1_track_devices({"devices": []})  # must not raise

    stub._surface_alert_in_app.assert_called_once()

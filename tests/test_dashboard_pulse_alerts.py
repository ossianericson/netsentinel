"""
Regression tests for critical-UX Phase 1.4: the status-bar pulse strip had
four segments (online/devices/scan/logger) but no persistent unacked-alert
indicator, even though the same get_unacked_alerts() count already drives the
Home "Action needed" card and the rail badge -- so a user watching only the
footer had no idea alerts existed.

Covers the two behavioural pieces that don't require constructing a Dashboard
(RULE-TP4-DASH): _refresh_pulse_bar()'s new alerts segment, and
_refresh_alert_badge() now also refreshing the Home card on its own 30s
cadence via _push_monitor_pills() (previously only the rail dot/tooltip).

RULE-T3: must fail before the fix (_refresh_pulse_bar has no alerts branch;
_refresh_alert_badge never calls _push_monitor_pills).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.monitor_state import _MonitorStateMixin  # noqa: E402


class _FakeStore:
    def __init__(self, alerts):
        self._alerts = alerts

    def get_unacked_alerts(self):
        return self._alerts


class _FakeHost(_MonitorStateMixin):
    """Minimal stand-in exposing only what _refresh_pulse_bar touches."""

    def __init__(self, alerts=None):
        self._store = _FakeStore(alerts if alerts is not None else [])
        self._last_log_status = None
        self._last_scan_devices: list = []
        self._last_scan_time = 0
        from PyQt6.QtWidgets import QLabel
        self._pulse_online_lbl = QLabel()
        self._pulse_devices_lbl = QLabel()
        self._pulse_scan_lbl = QLabel()
        self._pulse_logger_lbl = QLabel()
        self._pulse_alerts_lbl = QLabel()


class TestPulseBarAlertsSegment:
    def test_hidden_when_no_unacked_alerts(self):
        host = _FakeHost(alerts=[])
        host._refresh_pulse_bar()
        assert host._pulse_alerts_lbl.isHidden()

    def test_shown_with_count_when_unacked_alerts_exist(self):
        host = _FakeHost(alerts=[
            {"id": 1, "severity": "WARNING"}, {"id": 2, "severity": "INFO"},
        ])
        host._refresh_pulse_bar()
        assert not host._pulse_alerts_lbl.isHidden()
        assert "2" in host._pulse_alerts_lbl.text()

    def test_red_when_any_critical(self):
        from ui import styles as _s
        host = _FakeHost(alerts=[{"id": 1, "severity": "CRITICAL"}])
        host._refresh_pulse_bar()
        assert _s.RED in host._pulse_alerts_lbl.styleSheet()

    def test_amber_when_none_critical(self):
        from ui import styles as _s
        host = _FakeHost(alerts=[{"id": 1, "severity": "WARNING"}])
        host._refresh_pulse_bar()
        assert _s.AMBER in host._pulse_alerts_lbl.styleSheet()

    def test_store_error_does_not_raise(self):
        class _BrokenStore:
            def get_unacked_alerts(self):
                raise RuntimeError("db locked")

        host = _FakeHost()
        host._store = _BrokenStore()
        host._refresh_pulse_bar()  # must not raise
        assert host._pulse_alerts_lbl.isHidden()


class TestAlertBadgeRefreshesHomeCard:
    def test_refresh_alert_badge_also_calls_push_monitor_pills(self):
        host = _FakeHost()
        host._push_monitor_pills = MagicMock()
        host._refresh_section_badges = MagicMock()

        host._refresh_alert_badge()

        host._push_monitor_pills.assert_called_once()

    def test_refresh_alert_badge_noop_without_store(self):
        host = _FakeHost()
        host._store = None
        host._push_monitor_pills = MagicMock()
        host._refresh_section_badges = MagicMock()

        host._refresh_alert_badge()

        host._push_monitor_pills.assert_not_called()

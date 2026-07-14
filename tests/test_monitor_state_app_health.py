"""
Tests for ui/monitor_state.py::_MonitorStateMixin._push_monitor_pills (F-05).

The App Health table's "Scheduler" and "Report Scheduler" rows previously both
derived from the same `_report_scheduler_worker.isRunning()` flag, so they could
only ever agree by construction -- starting the real scan scheduler (a
different QThread, `_sched_worker`) never turned the "Scheduler" row green.
This covers the fix: each row now reads its own worker independently.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui import styles as _s  # noqa: E402
from ui.monitor_state import _MonitorStateMixin  # noqa: E402


class _FakeHost(_MonitorStateMixin):
    """Minimal stand-in exposing only what _push_monitor_pills touches."""

    def __init__(self, sched_running: bool, report_sched_running: bool) -> None:
        self._store = None
        self._sched_worker = MagicMock()
        self._sched_worker.isRunning.return_value = sched_running
        self._report_scheduler_worker = MagicMock()
        self._report_scheduler_worker.isRunning.return_value = report_sched_running
        self._settings_page = MagicMock()
        # _m3_monitoring_active is a real method on the mixin elsewhere in
        # dashboard.py; stub it here since this fake host doesn't have it.
        self._m3_monitoring_active = MagicMock(return_value=False)

    def _set_flyout_dot(self, *_a, **_kw) -> None:
        pass  # not under test here


def _health_dict(sched_running: bool, report_sched_running: bool) -> dict:
    host = _FakeHost(sched_running, report_sched_running)
    host._push_monitor_pills()
    (health,), _unused_kwargs = host._settings_page.refresh_health_status.call_args
    return health


class TestSchedulerRowsAreIndependent:
    def test_scan_scheduler_running_alone(self):
        health = _health_dict(sched_running=True, report_sched_running=False)
        assert health["Scheduler"] == ("Running", True)
        assert health["Report Scheduler"] == ("Stopped", False)

    def test_report_scheduler_running_alone(self):
        health = _health_dict(sched_running=False, report_sched_running=True)
        assert health["Scheduler"] == ("Stopped", False)
        assert health["Report Scheduler"] == ("Running", True)

    def test_both_stopped(self):
        health = _health_dict(sched_running=False, report_sched_running=False)
        assert health["Scheduler"] == ("Stopped", False)
        assert health["Report Scheduler"] == ("Stopped", False)

    def test_both_running(self):
        health = _health_dict(sched_running=True, report_sched_running=True)
        assert health["Scheduler"] == ("Running", True)
        assert health["Report Scheduler"] == ("Running", True)


class _DotRecordingHost(_MonitorStateMixin):
    """Stand-in that records every _set_flyout_dot call instead of applying it,
    so a test can tell whether _push_monitor_pills() touched a given label."""

    def __init__(self) -> None:
        self._store = None
        self._m3_monitoring_active = MagicMock(return_value=False)
        self._flyout_dots: dict[str, str] = {}
        self.dot_calls: list[tuple[str, str]] = []

    def _set_flyout_dot(self, label: str, color: str) -> None:
        self.dot_calls.append((label, color))
        self._flyout_dots[label] = color


class TestNetworkLoggerDotOwnedByRegistry:
    """F-57: the Network Logger flyout dot is set by _nav_set_scan_state() (in
    ui/tabs_logger.py, on real start/stop) and must not be clobbered by
    _push_monitor_pills()'s independent QSettings-checkbox-based recomputation --
    the two used different colour vocabularies (registry: fresh/stale/running/
    error -> GREEN/AMBER/ACCENT/RED; pills: binary GREEN/off) with no coordination.
    """

    def test_push_monitor_pills_does_not_touch_network_logger_dot(self):
        host = _DotRecordingHost()
        # Simulate the scan registry having just set "running" (ACCENT) via a
        # real Start Logger click -- this is the state _push_monitor_pills()
        # must not overwrite.
        host._flyout_dots["Network Logger"] = _s.ACCENT

        host._push_monitor_pills()

        touched = [label for label, _color in host.dot_calls if label == "Network Logger"]
        assert touched == [], (
            "_push_monitor_pills() wrote to the Network Logger flyout dot; it "
            "must be exclusively owned by the scan registry (_nav_set_scan_state)"
        )
        assert host._flyout_dots["Network Logger"] == _s.ACCENT

"""Regression test — Dashboard._start_full_scan() re-entrancy guard.

Bug: re-triggering a full scan while one is already running destroys the
in-flight M1-M5 worker threads. _launch_modules_impl() (ui/plugin_page_mixin.py)
unconditionally clears self._workers, dropping the only Python reference to
still-running, unparented QThreads. _start_full_scan() itself unconditionally
reassigns self._prescan_worker with no isRunning()/_is_scanning guard.

_launch_modules_impl() is only reachable via _start_full_scan() -> PreScanWorker
.done -> _launch_modules() -> _launch_modules_impl(), so a single guard at the
top of _start_full_scan() closes every re-entrancy path (tray "Run scan now",
empty-state CTA buttons, guided-tour timer, page scan_requested signals) --
they all call _start_full_scan() directly or via a connected signal.

Exercises the real Dashboard method against a lightweight double instead of
constructing the full widget tree (RULE-T7 / RULE-TP4-DASH), mirroring the
pattern in tests/test_dashboard_scan_watchdog.py.
"""
from unittest.mock import MagicMock

import pytest

try:
    from ui.dashboard import Dashboard
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _fake_dashboard(is_scanning: bool) -> MagicMock:
    fake = MagicMock()
    fake._is_scanning = is_scanning
    return fake


def test_start_full_scan_noop_while_already_scanning():
    """Calling _start_full_scan while a scan is in flight must not touch
    scan state -- it must return before resetting tables or reassigning
    _prescan_worker, so the in-flight PreScanWorker / M1-M5 workers survive."""
    fake = _fake_dashboard(is_scanning=True)

    Dashboard._start_full_scan(fake)

    fake._set_scanning.assert_not_called()
    fake._verdict.update.assert_not_called()
    fake._graph.reset.assert_not_called()
    fake._scan_watchdog.start.assert_not_called()


def test_start_full_scan_proceeds_when_idle(monkeypatch):
    """The guard must not block a normal scan start when idle."""
    fake = _fake_dashboard(is_scanning=False)

    class _FakePreScanWorker:
        def __init__(self, *a, **kw):
            self.status = MagicMock()
            self.done = MagicMock()
            self.error = MagicMock()

        def start(self):
            pass

    monkeypatch.setattr("workers.scan_worker.PreScanWorker", _FakePreScanWorker)

    Dashboard._start_full_scan(fake)

    fake._set_scanning.assert_called_once_with(True)
    fake._verdict.update.assert_called_once()
    fake._graph.reset.assert_called_once()
    fake._scan_watchdog.start.assert_called_once_with(120_000)
    assert isinstance(fake._prescan_worker, _FakePreScanWorker)

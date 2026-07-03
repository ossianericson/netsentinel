"""G5 regression tests — Dashboard._on_scan_watchdog_timeout.

Covers the scan-watchdog guard added in Sprint 3: if a full scan hangs
(pre-scan or a module worker never fires done/error), the UI must not be
stuck showing "Scanning…" forever. Exercises the real Dashboard method
against a lightweight double instead of constructing the full widget tree
(RULE-T7 allows "a mock of the dashboard" for exactly this reason — building
the real Dashboard requires a live QApplication plus every page/worker it
wires at __init__ time).
"""
from unittest.mock import MagicMock

import pytest

try:
    from ui.dashboard import Dashboard
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _fake_dashboard(is_scanning: bool, active_count: int = 2) -> MagicMock:
    fake = MagicMock()
    fake._is_scanning = is_scanning
    fake._active_count = active_count
    return fake


def test_watchdog_noop_when_scan_already_finished():
    """A stale timer firing after the scan already completed normally must
    not touch UI state — _on_worker_done already cancels the timer on the
    happy path, but a race (timeout queued just before cancel) must be safe."""
    fake = _fake_dashboard(is_scanning=False, active_count=0)

    Dashboard._on_scan_watchdog_timeout(fake)

    fake._set_scanning.assert_not_called()
    fake._verdict.update.assert_not_called()


def test_watchdog_clears_scanning_state_when_scan_hangs():
    """The core G5 guarantee: if the scan is still marked scanning when the
    120s watchdog fires, clear it instead of leaving a permanent spinner."""
    fake = _fake_dashboard(is_scanning=True, active_count=3)

    Dashboard._on_scan_watchdog_timeout(fake)

    assert fake._active_count == 0
    fake._set_scanning.assert_called_once_with(False)
    fake._verdict.update.assert_called_once()
    args, _kwargs = fake._verdict.update.call_args
    assert "took too long" in args[0].lower()
    assert args[1] == "UNKNOWN"

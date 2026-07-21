"""G5 regression tests — Dashboard._on_scan_watchdog_timeout.

Covers the scan-watchdog guard added in Sprint 3: if a full scan hangs
(pre-scan or a module worker never fires done/error), the UI must not be
stuck showing "Scanning…" forever. Exercises the real Dashboard method
against a lightweight double instead of constructing the full widget tree
(RULE-T7 allows "a mock of the dashboard" for exactly this reason — building
the real Dashboard requires a live QApplication plus every page/worker it
wires at __init__ time).

Part 1/C3 extends this: the office-VPN bug report was the watchdog firing
("Scan took too long and was stopped") while the scan workers were, in fact,
still alive and delivering a complete result a minute later. The fix: only
declare failure when nothing is actually running any more (or the 15-minute
hard ceiling is hit) — while real workers are alive, extend the deadline and
say so honestly instead of claiming a stop that never happens.
"""
import time
from unittest.mock import MagicMock

import pytest

try:
    from ui.dashboard import Dashboard
    from ui.plugin_page_mixin import (
        _PluginPageMixin, _WATCHDOG_BASE_MS, _WATCHDOG_PER_DEVICE_MS, _WATCHDOG_CEILING_MS,
    )
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _fake_dashboard(is_scanning: bool, active_count: int = 2, workers=None,
                     scan_started_at: float = None, status_msg: str = "",
                     bind_budget_helpers: bool = False) -> MagicMock:
    fake = MagicMock()
    fake._is_scanning = is_scanning
    fake._active_count = active_count
    fake._workers = workers if workers is not None else []
    fake._scan_started_at = scan_started_at if scan_started_at is not None else time.time()
    fake._status_bar.currentMessage.return_value = status_msg
    if bind_budget_helpers:
        # self.foo() inside the real method resolves against fake's own type
        # (MagicMock), not the Dashboard class -- bind the real implementations
        # explicitly so an integration test can exercise the full chain.
        fake._known_device_count_hint = lambda: _PluginPageMixin._known_device_count_hint(fake)
        fake._scan_watchdog_budget_ms = lambda: _PluginPageMixin._scan_watchdog_budget_ms(fake)
    return fake


# ── _known_device_count_hint / _scan_watchdog_budget_ms (direct unit tests) ──

def test_known_device_count_hint_extracts_total_from_status_bar():
    fake = MagicMock()
    fake._status_bar.currentMessage.return_value = "Identifying devices: 210/715…"
    assert _PluginPageMixin._known_device_count_hint(fake) == 715


def test_known_device_count_hint_zero_when_no_count_in_message():
    fake = MagicMock()
    fake._status_bar.currentMessage.return_value = "Scanning for rogue bridges…"
    assert _PluginPageMixin._known_device_count_hint(fake) == 0


def _fake_with_status(msg: str) -> MagicMock:
    fake = MagicMock()
    fake._status_bar.currentMessage.return_value = msg
    # self._known_device_count_hint() inside _scan_watchdog_budget_ms() resolves
    # against fake's own type (MagicMock), not _PluginPageMixin -- bind for real.
    fake._known_device_count_hint = lambda: _PluginPageMixin._known_device_count_hint(fake)
    return fake


def test_scan_watchdog_budget_scales_with_known_device_count():
    fake = _fake_with_status("Identifying devices: 5/715…")
    budget = _PluginPageMixin._scan_watchdog_budget_ms(fake)
    assert budget == _WATCHDOG_BASE_MS + 715 * _WATCHDOG_PER_DEVICE_MS


def test_scan_watchdog_budget_clamped_to_ceiling():
    fake = _fake_with_status("Identifying devices: 1/100000…")
    assert _PluginPageMixin._scan_watchdog_budget_ms(fake) == _WATCHDOG_CEILING_MS


def test_scan_watchdog_budget_is_base_when_no_hint():
    fake = _fake_with_status("")
    assert _PluginPageMixin._scan_watchdog_budget_ms(fake) == _WATCHDOG_BASE_MS


def _running_worker() -> MagicMock:
    w = MagicMock()
    w.isRunning.return_value = True
    return w


def _finished_worker() -> MagicMock:
    w = MagicMock()
    w.isRunning.return_value = False
    return w


def test_watchdog_noop_when_scan_already_finished():
    """A stale timer firing after the scan already completed normally must
    not touch UI state — _on_worker_done already cancels the timer on the
    happy path, but a race (timeout queued just before cancel) must be safe."""
    fake = _fake_dashboard(is_scanning=False, active_count=0)

    Dashboard._on_scan_watchdog_timeout(fake)

    fake._set_scanning.assert_not_called()
    fake._verdict.update.assert_not_called()
    fake._scan_watchdog.start.assert_not_called()


def test_watchdog_clears_scanning_state_when_no_workers_are_alive():
    """No live workers left -- the scan is genuinely stuck, not merely slow.
    This is the only case that still declares a stop."""
    fake = _fake_dashboard(is_scanning=True, active_count=3, workers=[])

    Dashboard._on_scan_watchdog_timeout(fake)

    assert fake._active_count == 0
    fake._set_scanning.assert_called_once_with(False)
    fake._verdict.update.assert_called_once()
    args, _kwargs = fake._verdict.update.call_args
    assert "took too long" in args[0].lower()
    assert args[1] == "UNKNOWN"
    fake._scan_watchdog.start.assert_not_called()


def test_watchdog_extends_instead_of_stopping_when_workers_still_alive():
    """The direct fix for the reported bug: workers are still running (this is
    exactly the office-VPN scenario -- 715 devices, still resolving names) and
    the ceiling has not been hit -- must NOT clear scanning state or claim a
    stop, must extend the deadline instead."""
    fake = _fake_dashboard(
        is_scanning=True, active_count=1, workers=[_running_worker()],
        scan_started_at=time.time(),  # just started
        status_msg="Identifying devices: 210/715…",
        bind_budget_helpers=True,
    )

    Dashboard._on_scan_watchdog_timeout(fake)

    fake._set_scanning.assert_not_called()
    fake._verdict.update.assert_not_called()
    assert fake._active_count == 1  # untouched
    fake._scan_watchdog.start.assert_called_once()
    status_calls = [c.args[0] for c in fake._set_status.call_args_list]
    assert any("still scanning" in s.lower() for s in status_calls), status_calls
    assert any("715" in s for s in status_calls), (
        "the honest status must carry the real device count when known"
    )
    assert not any("took too long" in s.lower() for s in status_calls), (
        "must never claim a stop while a worker is actually still running"
    )


def test_watchdog_extends_without_device_count_when_unknown():
    """Modules 2-5 don't report a count -- the honest message must still make
    sense without one (no fabricated number)."""
    fake = _fake_dashboard(
        is_scanning=True, workers=[_running_worker()],
        scan_started_at=time.time(), status_msg="Scanning for rogue bridges…",
    )

    Dashboard._on_scan_watchdog_timeout(fake)

    fake._set_scanning.assert_not_called()
    fake._scan_watchdog.start.assert_called_once()


def test_watchdog_declares_failure_once_ceiling_is_hit_even_if_still_running():
    """A worker alive forever must not extend the deadline forever -- once the
    hard 15-minute ceiling is exceeded, stop waiting, but say what actually
    happened (a worker may still be running) rather than a false "stopped"."""
    started = time.time() - (_WATCHDOG_CEILING_MS / 1000.0) - 5
    fake = _fake_dashboard(
        is_scanning=True, workers=[_running_worker()],
        scan_started_at=started, status_msg="Identifying devices: 700/715…",
    )

    Dashboard._on_scan_watchdog_timeout(fake)

    fake._set_scanning.assert_called_once_with(False)
    fake._scan_watchdog.start.assert_not_called()
    args, _kwargs = fake._verdict.update.call_args
    assert "took too long" not in args[0].lower(), (
        "past the ceiling with a worker still alive, the message must say so "
        "honestly instead of falsely claiming the scan was stopped"
    )
    assert "background" in args[0].lower() or "still" in args[0].lower()

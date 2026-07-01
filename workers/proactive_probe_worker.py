"""
workers/proactive_probe_worker.py — generic interval-loop QThread for future
proactive background probes (Sprint 2 foundation).

Modeled on workers/report_scheduler_worker.py's interval-loop pattern, but
generalized over an injected probe callable so Sprints 3+ (e.g. scheduled
speed tests) share one worker implementation instead of each writing their
own timer loop.

Inert scaffolding as of Sprint 2 — nothing in app.py instantiates this yet.
"""
from __future__ import annotations

import time
from typing import Callable

from PyQt6.QtCore import QThread, pyqtSignal


_DEFAULT_INTERVAL_S = 3600  # 1 hour


class ProactiveProbeWorker(QThread):
    """
    Background QThread that calls an injected probe callable on a fixed interval.

    Signals
    -------
    probe_done(object)
        Emitted with whatever the probe callable returns.
    error(str)
        Emitted on any exception raised by the probe callable.
    """

    probe_done = pyqtSignal(object)
    error      = pyqtSignal(str)

    def __init__(
        self,
        probe: Callable[[], object],
        interval_s: int = _DEFAULT_INTERVAL_S,
        parent=None,
    ):
        super().__init__(parent)
        self._probe      = probe
        self._interval_s = interval_s
        self._running    = False
        self._force_now  = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_interval(self, interval_s: int) -> None:
        self._interval_s = interval_s

    def trigger_now(self) -> None:
        """Request an immediate probe run, bypassing the remaining wait."""
        self._force_now = True

    def stop(self) -> None:
        self._running = False

    # ── QThread run ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        while self._running:
            self._force_now = False
            try:
                result = self._probe()
                self.probe_done.emit(result)
            except Exception as exc:
                self.error.emit(str(exc))

            # Interruptible sleep — check every second for stop/force signals
            for _ in range(self._interval_s):
                if not self._running or self._force_now:
                    break
                time.sleep(1)

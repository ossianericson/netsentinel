"""
ReportSchedulerWorker — QThread that fires ReportScheduler on a timer (T2#9).

Checks schedule every minute; calls run_if_due() when interval has elapsed.
Emits report_saved(str) with the file path after each successful report.
Supports immediate trigger via trigger_now().
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QThread, pyqtSignal

from modules.report_scheduler import ReportConfig, ReportScheduler
from modules.metric_store import MetricStore


_CHECK_INTERVAL_S = 60   # wake up every minute to check if report is due


class ReportSchedulerWorker(QThread):
    """
    Background QThread that drives the ReportScheduler on a configurable interval.

    Signals
    -------
    report_saved(str)
        Emitted with the absolute path of the saved report file.
    error(str)
        Emitted on any exception during report generation.
    """

    report_saved = pyqtSignal(str)
    error        = pyqtSignal(str)

    def __init__(
        self,
        store: MetricStore,
        config: ReportConfig | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._store     = store
        self._config    = config or ReportConfig()
        self._scheduler = ReportScheduler(
            store  = self._store,
            config = self._config,
            on_saved = lambda p: self.report_saved.emit(str(p)),
        )
        self._running    = False
        self._force_now  = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_config(self, config: ReportConfig) -> None:
        """Update schedule settings while the worker is running."""
        self._config = config
        self._scheduler.set_config(config)

    def get_config(self) -> ReportConfig:
        return self._config

    def trigger_now(self) -> None:
        """Request an immediate report on the next loop iteration."""
        self._force_now = True

    def stop(self) -> None:
        self._running = False

    # ── QThread run ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                if self._force_now:
                    self._force_now = False
                    self._scheduler.generate_now()
                else:
                    self._scheduler.run_if_due()
            except Exception as exc:
                self.error.emit(str(exc))

            # Interruptible sleep — check every second for stop/force signals
            for _ in range(_CHECK_INTERVAL_S):
                if not self._running or self._force_now:
                    break
                time.sleep(1)

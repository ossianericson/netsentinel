"""
workers/health_worker.py — Ambient health score polling worker.

Runs HealthScoreCalculator every 60 seconds against the live MetricStore.
No new network traffic is generated — pure computation over already-collected data.

Emits:
  result_ready(object)  — HealthSnapshot
  error(str)            — error description (non-fatal; worker continues)

Stop mechanism: threading.Event-based.  stop() sets the event; run() exits
after the current computation + emit completes.  This avoids the _running-flag
race where stop() is called before run() sets _running = True.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from modules.health_score import HealthScoreCalculator


class HealthWorker(QThread):
    """60-second polling worker that emits ambient health snapshots."""

    result_ready = pyqtSignal(object)   # HealthSnapshot
    error        = pyqtSignal(str)

    _INTERVAL_S = 60

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self._store      = store
        self._calculator = HealthScoreCalculator()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                snapshot = self._calculator.compute(self._store)
                self.result_ready.emit(snapshot)
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            # wait() returns True when the event is set (stop requested),
            # False when it times out (next polling interval).
            if self._stop_event.wait(timeout=self._INTERVAL_S):
                break

    def stop(self) -> None:
        self._stop_event.set()

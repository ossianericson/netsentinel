"""
workers/app_traffic_worker.py — QThread wrapper for AppTrafficMonitor.

Runs the Scapy-based per-host protocol classifier in a background thread
and emits AppTrafficSnapshot objects every *interval_s* seconds.

Signals
-------
snapshot_ready(object)
    An AppTrafficSnapshot from modules.app_traffic_classifier.
error(str)
    Emitted when Scapy is unavailable or packet capture fails.
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal


class AppTrafficWorker(QThread):
    """Per-host application-layer traffic classifier worker."""

    snapshot_ready: pyqtSignal = pyqtSignal(object)
    error:          pyqtSignal = pyqtSignal(str)

    def __init__(self, interval_s: float = 10.0, parent=None) -> None:
        super().__init__(parent)
        self._interval   = interval_s
        self._stop_event = threading.Event()
        self._label_map: dict = {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_label_map(self, label_map: dict) -> None:
        """Update MAC → display-label mapping (thread-safe)."""
        self._label_map = dict(label_map)

    def stop(self) -> None:
        """Signal the monitor loop to exit; call wait() to join."""
        self._stop_event.set()

    # ── QThread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        self._stop_event.clear()
        try:
            from modules.app_traffic_classifier import AppTrafficMonitor
        except ImportError:
            self.error.emit(
                "app_traffic_classifier could not be imported — "
                "ensure modules/app_traffic_classifier.py is present."
            )
            return

        monitor = AppTrafficMonitor(
            interval_s=self._interval,
            on_snapshot=self.snapshot_ready.emit,
            on_error=self.error.emit,
            label_map=self._label_map,
            stop_event=self._stop_event,
        )
        monitor.run()   # blocks until _stop_event is set

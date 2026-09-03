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
        self._monitor = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_label_map(self, label_map: dict) -> None:
        """Update MAC → display-label mapping (thread-safe).

        The running AppTrafficMonitor holds its own reference to the map it was
        constructed with, so rebinding `self._label_map` alone would silently
        discard every update made after start() — leaving a session that began
        monitoring before its first scan stamping bare MACs onto every snapshot
        for as long as it ran. Push the new map onto the live monitor too.
        """
        self._label_map = dict(label_map)
        monitor = self._monitor
        if monitor is not None:
            monitor.label_map = self._label_map

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
        self._monitor = monitor
        try:
            monitor.run()   # blocks until _stop_event is set
        except Exception as exc:  # noqa: BLE001 — reported via the error signal
            # A `finally` with no `except` still lets the exception escape run().
            self.error.emit(str(exc))
        finally:
            self._monitor = None

"""
workers/bandwidth_worker.py — QThread wrapper for BandwidthMonitor.

Runs the Scapy-based per-MAC sniffer in a background thread and emits
BandwidthSnapshot objects every *interval_s* seconds.

Signals
-------
snapshot_ready(object)
    A BandwidthSnapshot from modules.bandwidth_monitor.  Dict of
    {mac: total_bps} is available via snapshot.entries.
error(str)
    Emitted when Scapy is unavailable or packet capture fails (not admin /
    no Npcap).  The overlay simply stays hidden in this case.

Usage
-----
    worker = BandwidthOverlayWorker(interval_s=5.0)
    worker.snapshot_ready.connect(my_slot)
    worker.error.connect(my_error_slot)
    worker.start()
    ...
    worker.stop()
    worker.wait()
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal


class BandwidthOverlayWorker(QThread):
    """Per-MAC bandwidth sniffer for the topology traffic overlay."""

    snapshot_ready: pyqtSignal = pyqtSignal(object)
    error:          pyqtSignal = pyqtSignal(str)

    def __init__(self, interval_s: float = 5.0, parent=None) -> None:
        super().__init__(parent)
        self._interval   = interval_s
        self._stop_event = threading.Event()

    # ── Public API ─────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the monitor loop to exit; call wait() to join."""
        self._stop_event.set()

    # ── QThread entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        self._stop_event.clear()
        try:
            from modules.bandwidth_monitor import BandwidthMonitor
        except ImportError:
            self.error.emit(
                "bandwidth_monitor could not be imported — "
                "ensure modules/bandwidth_monitor.py is present."
            )
            return

        monitor = BandwidthMonitor(
            interval_s=self._interval,
            on_snapshot=self.snapshot_ready.emit,
            on_error=self.error.emit,
            stop_event=self._stop_event,
        )
        try:
            monitor.run()   # blocks until _stop_event is set
        except Exception as exc:  # noqa: BLE001 — reported via the error signal
            # Scapy-backed and therefore the likeliest worker to raise something
            # unexpected. An escape from run() is routed through sys.excepthook on
            # THIS thread, where the crash handler would try to build a widget.
            self.error.emit(str(exc))

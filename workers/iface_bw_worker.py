"""
workers/iface_bw_worker.py — Interface-level bandwidth poller
==============================================================
Polls ``psutil.net_io_counters(pernic=True)`` once per second and converts
byte-delta to Mbps.  Runs in a background QThread so the GUI stays smooth.

Signals
-------
stats_ready(dict)
    ``{ iface_name: {"up_mbps": float, "down_mbps": float,
                     "up_bytes": int, "down_bytes": int} }``
    Only emits for interfaces that are actually moving data *or* were
    previously active (so the chart always has the same set of keys).
error(str)
    Emitted when psutil is unavailable or an unexpected exception occurs.

Usage
-----
    worker = IfaceBwPoller()
    worker.stats_ready.connect(my_slot)
    worker.start()
    ...
    worker.stop()   # non-blocking; thread will exit after ≤1 s
"""

from __future__ import annotations

import time
from typing import Dict, Optional

from PyQt6.QtCore import QThread, pyqtSignal


class IfaceBwPoller(QThread):
    """Continuously poll interface I/O counters; emit per-second Mbps."""

    stats_ready: pyqtSignal = pyqtSignal(dict)
    error:       pyqtSignal = pyqtSignal(str)

    def __init__(
        self,
        interval_s: float = 1.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._interval = interval_s
        self._running  = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        try:
            import psutil
        except ImportError:
            self.error.emit("psutil is not installed — bandwidth polling unavailable")
            return

        self._running = True
        prev: Optional[Dict] = None
        prev_time: float = 0.0

        while self._running:
            now = time.monotonic()
            try:
                current = psutil.net_io_counters(pernic=True)
            except Exception as exc:
                self.error.emit(str(exc))
                time.sleep(self._interval)
                continue

            if prev is not None:
                elapsed = now - prev_time
                if elapsed <= 0:
                    elapsed = self._interval

                result: dict = {}
                for iface, cnt in current.items():
                    p = prev.get(iface)
                    if p is None:
                        continue
                    up_bytes   = max(0, cnt.bytes_sent - p.bytes_sent)
                    down_bytes = max(0, cnt.bytes_recv - p.bytes_recv)
                    result[iface] = {
                        "up_mbps":   (up_bytes   * 8) / (elapsed * 1_000_000),
                        "down_mbps": (down_bytes * 8) / (elapsed * 1_000_000),
                        "up_bytes":  up_bytes,
                        "down_bytes": down_bytes,
                    }
                self.stats_ready.emit(result)

            prev      = current
            prev_time = now
            time.sleep(self._interval)

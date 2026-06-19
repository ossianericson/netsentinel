"""
ServiceWorker — QThread wrapper for the TCP service heartbeat monitor (T2#7).

Runs service checks immediately on start, then every interval_s seconds.

Signals
-------
check_done(list)   — emitted after each run: list of ServiceResult-style dicts
error(str)         — human-readable error message

Usage
-----
    worker = ServiceWorker(store=metric_store,
                           targets=[ServiceTarget("192.168.1.1", 80, "Router HTTP")])
    worker.check_done.connect(my_page.on_check_done)
    worker.start()
    ...
    worker.stop()
    worker.wait()
"""

from __future__ import annotations

import time
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.service_monitor import ServiceMonitor, ServiceTarget
from modules.metric_store import MetricStore


class ServiceWorker(QThread):
    """Background QThread that runs TCP service checks on a fixed interval."""

    check_done = pyqtSignal(list)   # list of ServiceResult-style dicts
    error      = pyqtSignal(str)

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[ServiceTarget]] = None,
        interval_s: int = 60,
        parent=None,
    ):
        super().__init__(parent)
        self._stop_requested = False
        self._check_now      = False   # set True to break the sleep and run immediately
        self._interval_s     = interval_s
        self._monitor        = ServiceMonitor(store=store, targets=targets or [])

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[ServiceTarget]) -> None:
        self._monitor.set_targets(targets)

    def check_now(self) -> None:
        """Wake the worker early so it runs a check on the next iteration."""
        self._check_now = True

    def stop(self) -> None:
        self._stop_requested = True

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._stop_requested = False
        while not self._stop_requested:
            try:
                results = self._monitor.run_check()
                self.check_done.emit([
                    {
                        "host":   r.host,
                        "port":   r.port,
                        "label":  r.label,
                        "up":     r.up,
                        "rtt_ms": r.rtt_ms,
                        "error":  r.error,
                        "ts":     r.ts,
                    }
                    for r in results
                ])
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            self._check_now = False
            elapsed = 0
            while elapsed < self._interval_s and not self._stop_requested and not self._check_now:
                time.sleep(1)
                elapsed += 1

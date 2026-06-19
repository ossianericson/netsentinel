"""
CertWorker — QThread wrapper for the TLS certificate monitor (T2#6).

Runs cert checks immediately on start, then every interval_s seconds.

Signals
-------
check_done(list)   — emitted after each run: list of CertInfo-style dicts
error(str)         — human-readable error message

Usage
-----
    worker = CertWorker(store=metric_store, targets=[CertTarget("example.com")])
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

from modules.cert_monitor import CertMonitor, CertTarget
from modules.metric_store import MetricStore


class CertWorker(QThread):
    """Background QThread that runs TLS certificate checks on a fixed interval."""

    check_done = pyqtSignal(list)   # list of CertInfo-style dicts
    error      = pyqtSignal(str)

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[CertTarget]] = None,
        interval_s: int = 3600,
        parent=None,
    ):
        super().__init__(parent)
        self._stop_requested = False
        self._interval_s     = interval_s
        self._monitor        = CertMonitor(store=store, targets=targets or [])

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[CertTarget]) -> None:
        self._monitor.set_targets(targets)

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
                        "host":           r.host,
                        "port":           r.port,
                        "days_remaining": r.days_remaining,
                        "subject":        r.subject,
                        "issuer":         r.issuer,
                        "not_after":      r.not_after,
                        "is_expired":     r.is_expired,
                        "is_self_signed": r.is_self_signed,
                        "error":          r.error,
                        "verdict":        r.verdict,
                    }
                    for r in results
                ])
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))

            # Interruptible sleep — checks stop flag every second
            elapsed = 0
            while elapsed < self._interval_s and not self._stop_requested:
                time.sleep(1)
                elapsed += 1

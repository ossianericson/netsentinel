"""
CertWorker — QThread wrapper for the TLS certificate monitor (T2#6).

Runs cert checks immediately on start, then every interval_s seconds.

Signals
-------
check_done(list)   — emitted after each run: list of CertInfo-style dicts
error(str)         — inherited from BaseWorker

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

import threading
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal

from modules.cert_monitor import CertMonitor, CertTarget
from modules.metric_store import MetricStore
from workers.base_worker import BaseWorker


class CertWorker(BaseWorker):
    """Background QThread that runs TLS certificate checks on a fixed interval."""

    check_done = pyqtSignal(list)   # list of CertInfo-style dicts

    def __init__(
        self,
        store: MetricStore,
        targets: Optional[List[CertTarget]] = None,
        interval_s: int = 3600,
        parent=None,
    ):
        super().__init__(parent)
        self._interval_s = interval_s
        self._monitor    = CertMonitor(store=store, targets=targets or [])
        self._run_now_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_targets(self, targets: List[CertTarget]) -> None:
        self._monitor.set_targets(targets)

    def run_now(self) -> None:
        """Interrupt the interval sleep and run a check immediately (F-02)."""
        self._run_now_event.set()

    # ── Thread body ───────────────────────────────────────────────────────────

    def work(self) -> None:
        while not self._should_stop():
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
                        "not_testable":        r.not_testable,
                        "not_testable_reason": r.not_testable_reason,
                    }
                    for r in results
                ])
            except Exception as exc:  # noqa: BLE001 — one failed check must not kill the monitor loop
                self.error.emit(str(exc))

            # Interruptible sleep — checks stop flag every second, and wakes
            # immediately (without waiting out the full interval) if run_now()
            # is called (F-02: on-demand trigger from the Security Scan panel).
            elapsed = 0
            while elapsed < self._interval_s and not self._should_stop():
                if self._run_now_event.wait(timeout=1):
                    self._run_now_event.clear()
                    break
                elapsed += 1

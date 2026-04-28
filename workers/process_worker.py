"""
workers/process_worker.py — QThread workers for process-to-socket mapping.

Workers
-------
ConnectionSnapshotWorker
    One-shot snapshot of all active connections.
    Emits: snapshot_ready(list), error(str)

ConnectionPollerWorker
    Continuous poller — re-snapshots every `interval` seconds.
    Emits: snapshot_ready(list), error(str)
    Call .stop() to terminate.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal


class ConnectionSnapshotWorker(QThread):
    snapshot_ready = pyqtSignal(list)
    error          = pyqtSignal(str)

    def __init__(self, include_listen: bool = False,
                 geo_enrich: bool = False, parent=None):
        super().__init__(parent)
        self._include_listen = include_listen
        self._geo_enrich     = geo_enrich

    def run(self):
        try:
            from modules.process_monitor import snapshot
            conns = snapshot(
                include_listen=self._include_listen,
                geo_enrich=self._geo_enrich,
            )
            self.snapshot_ready.emit(conns)
        except Exception as exc:
            self.error.emit(str(exc))


class ConnectionPollerWorker(QThread):
    snapshot_ready = pyqtSignal(list)
    error          = pyqtSignal(str)

    def __init__(self, interval: int = 5, include_listen: bool = False,
                 parent=None):
        super().__init__(parent)
        self._interval       = interval
        self._include_listen = include_listen
        self._running        = False

    def run(self):
        import time
        from modules.process_monitor import snapshot
        self._running = True
        while self._running:
            try:
                conns = snapshot(include_listen=self._include_listen)
                self.snapshot_ready.emit(conns)
            except Exception as exc:
                self.error.emit(str(exc))
            # Sleep in small chunks so stop() is responsive
            for _ in range(self._interval * 4):
                if not self._running:
                    break
                time.sleep(0.25)

    def stop(self):
        self._running = False

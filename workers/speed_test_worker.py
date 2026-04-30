"""
Speed test QThread workers.

FetchServersWorker  — fetches nearby Ookla-compatible servers in the background
SpeedTestWorker     — runs a full download / upload / ping test
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


class FetchServersWorker(QThread):
    """Fetches nearby Ookla servers and their latencies."""

    servers_ready = pyqtSignal(list)   # list[dict] — serialised SpeedServer
    error         = pyqtSignal(str)

    def __init__(self, limit: int = 20, parent=None):
        super().__init__(parent)
        self._limit = limit

    def run(self) -> None:
        try:
            from modules.speed_tester import fetch_servers
            servers = fetch_servers(self._limit)
            self.servers_ready.emit([
                {
                    "id":         s.id,
                    "name":       s.name,
                    "city":       s.city,
                    "country":    s.country,
                    "host":       s.host,
                    "latency_ms": s.latency_ms,
                }
                for s in servers
            ])
        except Exception as exc:
            self.error.emit(str(exc))


class SpeedTestWorker(QThread):
    """Runs a full speed test against the chosen server (or auto-best)."""

    # (phase, message)  phase ∈ {"connecting", "ping", "download", "upload", "done"}
    phase_changed = pyqtSignal(str, str)
    # Live throughput sample: (mbps, phase) — emitted during download and upload
    speed_sample  = pyqtSignal(float, str)
    result_ready  = pyqtSignal(object)   # SpeedTestResult
    error         = pyqtSignal(str)

    def __init__(self, server_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._server_id = server_id

    def run(self) -> None:
        try:
            from modules.speed_tester import run_test
            result = run_test(
                server_id=self._server_id,
                on_progress=lambda phase, msg: self.phase_changed.emit(phase, msg),
                on_sample=lambda mbps, phase: self.speed_sample.emit(mbps, phase),
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

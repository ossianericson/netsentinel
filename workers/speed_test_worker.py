"""
Speed test QThread workers.

FetchServersWorker  — fetches nearby Ookla-compatible servers in the background
SpeedTestWorker     — runs a full download / upload / ping test

ZTE enrichment
--------------
Pass zte_host + zte_password to SpeedTestWorker to capture a modem signal
snapshot immediately before the test starts.  The snapshot is attached to
SpeedTestResult.zte_signal (a plain dict).  If the ZTE fetch fails for any
reason the speed test still runs — the snapshot is silently omitted.
"""

from __future__ import annotations

import dataclasses
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

    def __init__(
        self,
        server_id:    Optional[str] = None,
        zte_host:     Optional[str] = None,
        zte_password: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._server_id   = server_id
        self._zte_host    = zte_host
        self._zte_password = zte_password

    def run(self) -> None:
        # ── 1. Capture ZTE signal snapshot before the test stresses the link ──
        zte_snapshot: Optional[dict] = None
        if self._zte_host and self._zte_password:
            import time as _t
            for _attempt in range(3):
                try:
                    from modules.zte_client import ZteMC889Client
                    client = ZteMC889Client(self._zte_host)
                    client.login(self._zte_password)
                    signal = client.get_signal_data()
                    zte_snapshot = dataclasses.asdict(signal)
                    break
                except Exception:
                    if _attempt < 2:
                        _t.sleep(2.0)  # ZteWorker may still hold the session; retry

        # ── 2. Run the speed test ─────────────────────────────────────────────
        try:
            from modules.speed_tester import run_test
            result = run_test(
                server_id=self._server_id,
                on_progress=lambda phase, msg: self.phase_changed.emit(phase, msg),
                on_sample=lambda mbps, phase: self.speed_sample.emit(mbps, phase),
            )
            result.zte_signal = zte_snapshot
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

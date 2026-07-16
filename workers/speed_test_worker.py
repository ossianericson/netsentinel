"""
Speed test QThread workers.

FetchServersWorker  — fetches nearby Ookla-compatible servers in the background
SpeedTestWorker     — runs a full download / upload / ping test

Modem enrichment
----------------
Two paths — whichever applies is used; ZTE live fetch takes priority:

1. ZTE live fetch: pass zte_host + zte_password. A signal snapshot is captured
   immediately before the test starts via ZteMC889Client. Requires a live ZTE
   session; retried up to 3 times if the ZteWorker still holds the session.

2. Plugin snapshot fallback: pass modem_snapshot (a dict from hw_state or any
   plugin modem result). Used when no ZTE credentials are available. No network
   call — the snapshot is attached directly to the result.

If neither source is configured the test still runs; SpeedTestResult.modem_signal
is None.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from PyQt6.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


class FetchServersWorker(BaseWorker):
    """Fetches nearby Ookla servers and their latencies."""

    servers_ready  = pyqtSignal(list)   # list[dict] — serialised SpeedServer
    status_changed = pyqtSignal(str)    # progress message for the UI

    def __init__(self, limit: int = 20, preferred_location: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._limit = limit
        self._preferred_location = preferred_location

    def work(self) -> None:
        from modules.speed_tester import fetch_servers
        servers = fetch_servers(
            self._limit,
            on_status=lambda msg: self.status_changed.emit(msg),
            preferred_location=self._preferred_location,
        )
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


class SpeedTestWorker(BaseWorker):
    """Runs a full speed test against the chosen server (or auto-best)."""

    # (phase, message)  phase ∈ {"connecting", "ping", "download", "upload", "done"}
    phase_changed = pyqtSignal(str, str)
    # Live throughput sample: (mbps, phase) — emitted during download and upload
    speed_sample  = pyqtSignal(float, str)
    result_ready  = pyqtSignal(object)   # SpeedTestResult

    def __init__(
        self,
        server_id:      Optional[str]  = None,
        zte_host:       Optional[str]  = None,
        zte_password:   Optional[str]  = None,
        modem_snapshot: Optional[dict] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._server_id      = server_id
        self._zte_host       = zte_host
        self._zte_password   = zte_password
        self._modem_snapshot = modem_snapshot

    def work(self) -> None:
        # ── 1. Capture modem signal snapshot before the test stresses the link ─
        modem_snapshot: Optional[dict] = None

        if self._zte_host and self._zte_password:
            # ZTE path: live fetch so we get current signal, not a stale cache
            import time as _t
            for _attempt in range(3):
                try:
                    from modules.zte_client import ZteMC889Client
                    client = ZteMC889Client(self._zte_host)
                    client.login(self._zte_password)
                    signal = client.get_signal_data()
                    modem_snapshot = dataclasses.asdict(signal)
                    break
                except Exception:
                    if _attempt < 2:
                        _t.sleep(2.0)  # ZteWorker may still hold the session; retry
        elif self._modem_snapshot:
            # Plugin path: use the last known snapshot from hw_state
            modem_snapshot = self._modem_snapshot

        # ── 2. Run the speed test (errors → BaseWorker.run() → error signal) ───
        from modules.speed_tester import run_test
        result = run_test(
            server_id=self._server_id,
            on_progress=lambda phase, msg: self.phase_changed.emit(phase, msg),
            on_sample=lambda mbps, phase: self.speed_sample.emit(mbps, phase),
        )
        result.modem_signal = modem_snapshot
        self.result_ready.emit(result)

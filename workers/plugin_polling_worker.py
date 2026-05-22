"""
PluginPollingWorker — persistent hardware plugin poller.

Mirrors the ZteWorker / DecoMeshWorker pattern: runs in a QThread,
executes the plugin subprocess repeatedly on a tuned interval, and
emits result / error signals just like the native workers.

Intervals (tuned by hardware type):
    modem     60 s   — frequent signal updates for Overview / Modem page
    router   120 s   — frequent enough for device tracking / enrichment
    ap       120 s
    switch   300 s
    other    300 s

Manual refresh: call trigger_now() to wake the sleep immediately.
Stop: call stop() then wait().
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class PluginPollingWorker(QThread):

    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    _INTERVALS: dict[str, int] = {
        "modem":  60,
        "router": 120,
        "ap":     120,
        "switch": 300,
    }
    _DEFAULT_INTERVAL = 300
    _SUBPROCESS_TIMEOUT = 90   # seconds

    def __init__(self, path: str, hw_type: str, parent=None) -> None:
        super().__init__(parent)
        self._path       = path
        self._hw_type    = hw_type
        self._interval_s = self._INTERVALS.get(hw_type, self._DEFAULT_INTERVAL)
        self._stop       = False
        self._trigger    = threading.Event()

    # ── Public interface ──────────────────────────────────────────────────────

    def stop(self) -> None:
        """Request graceful shutdown. Call wait() afterwards."""
        self._stop = True
        self._trigger.set()

    def trigger_now(self) -> None:
        """Wake the inter-poll sleep immediately — runs plugin right away."""
        self._trigger.set()

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        while not self._stop:
            self._trigger.clear()
            self._run_once()

            if not self._stop:
                # Interruptible sleep — wakes within 0.5 s of stop() or trigger_now()
                self._trigger.wait(timeout=self._interval_s)

    # Repo root (workers/ → parent) so plugins can do `from modules.xxx import`
    _NS_ROOT = str(Path(__file__).parent.parent)

    def _run_once(self) -> None:
        try:
            env = os.environ.copy()
            # Ensure plugins can import NetSentinel modules regardless of cwd
            existing = env.get("PYTHONPATH", "")
            paths = [self._NS_ROOT] + ([existing] if existing else [])
            env["PYTHONPATH"] = os.pathsep.join(paths)

            proc = subprocess.run(
                [sys.executable, self._path, "--netsentinel"],
                capture_output=True,
                text=True,
                timeout=self._SUBPROCESS_TIMEOUT,
                env=env,
            )
            if self._stop:
                return
            if proc.returncode == 0 and proc.stdout.strip():
                try:
                    data = json.loads(proc.stdout.strip())
                    self.result.emit(data)
                except json.JSONDecodeError as exc:
                    self.error.emit(f"JSON parse error: {exc}")
            else:
                # Surface the last non-empty stderr line
                lines = [l for l in (proc.stderr or "").splitlines() if l.strip()]
                msg = lines[-1] if lines else f"plugin exited {proc.returncode}"
                self.error.emit(msg)
        except subprocess.TimeoutExpired:
            self.error.emit(f"Plugin timed out after {self._SUBPROCESS_TIMEOUT} s")
        except Exception as exc:
            self.error.emit(str(exc))

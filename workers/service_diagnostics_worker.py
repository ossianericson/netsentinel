"""
ServiceDiagnosticsWorker — QThread wrapper for DiagnosticEngine.run() (Sprint 4).

Signals
-------
result_ready(object)  — emitted with a ServiceDiagnosticResult on success
error(str)            — human-readable error message
progress(str)         — status updates during the probe sequence
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from modules.service_diagnostics import DiagnosticEngine


class ServiceDiagnosticsWorker(QThread):
    """Runs DiagnosticEngine.run() off the main thread for a single service."""

    result_ready = pyqtSignal(object)   # ServiceDiagnosticResult
    error        = pyqtSignal(str)
    progress     = pyqtSignal(str)

    def __init__(
        self,
        service_id: Optional[str] = None,
        traceroute: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._service_id      = service_id
        self._traceroute      = traceroute
        self._stop_requested  = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_service(self, service_id: str, traceroute: bool = False) -> None:
        self._service_id = service_id
        self._traceroute = traceroute

    def stop(self) -> None:
        self._stop_requested = True

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        self._stop_requested = False
        if not self._service_id:
            self.error.emit("No service selected.")
            return

        try:
            name = self._service_id
            self.progress.emit(f"Probing {name} — DNS resolution…")
            engine = DiagnosticEngine()
            # DiagnosticEngine.run() is blocking; emitting progress before is enough
            # as the engine itself runs quickly (traceroute aside, ~5-10 s total).
            result = engine.run(self._service_id, traceroute=self._traceroute)
            if not self._stop_requested:
                self.progress.emit("Done.")
                self.result_ready.emit(result)
        except Exception as exc:  # noqa: BLE001
            if not self._stop_requested:
                self.error.emit(
                    f"Diagnostics failed for '{self._service_id}': {exc}. "
                    "Check your network connection and try again."
                )

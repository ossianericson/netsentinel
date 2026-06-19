"""
dns_zone_worker.py — QThread worker for DNS zone scanning.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from modules.dns_zone_scanner import DnsZoneResult, scan as _scan


class DnsZoneWorker(QThread):
    """
    Runs dns_zone_scanner.scan() off the main thread.

    Signals:
        result_ready(DnsZoneResult) — emits the completed result object
        progress(str)               — emits human-readable status messages
        error(str)                  — emits an error message string
    """

    result_ready: pyqtSignal = pyqtSignal(object)
    progress:     pyqtSignal = pyqtSignal(str)
    error:        pyqtSignal = pyqtSignal(str)

    def __init__(
        self,
        axfr_server: str  = "",
        axfr_domain: str  = "",
        axfr_timeout: float = 10.0,
        mdns_timeout: float = 3.0,
        parent=None,
    ):
        super().__init__(parent)
        self._axfr_server  = axfr_server
        self._axfr_domain  = axfr_domain
        self._axfr_timeout = axfr_timeout
        self._mdns_timeout = mdns_timeout

    def run(self) -> None:
        try:
            result: DnsZoneResult = _scan(
                axfr_server=self._axfr_server,
                axfr_domain=self._axfr_domain,
                axfr_timeout=self._axfr_timeout,
                mdns_timeout=self._mdns_timeout,
                progress_cb=self.progress.emit,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

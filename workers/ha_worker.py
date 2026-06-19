"""
Home Automation workers.

HaScanWorker     — background HA protocol/OUI detection scan
MacLookupWorker  — single background MAC vendor lookup (online)
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import QThread, pyqtSignal


class HaScanWorker(QThread):
    """
    Runs ha_detector.scan() against a list of host dicts in the background.
    Emits results_ready with the full list of HaMatch objects.
    """

    status       = pyqtSignal(str)
    results_ready = pyqtSignal(list)   # list[HaMatch]
    error        = pyqtSignal(str)

    def __init__(
        self,
        hosts: List[dict],
        port_timeout: float = 1.5,
        http_timeout: float = 3.0,
        parent=None,
    ):
        super().__init__(parent)
        self._hosts        = hosts
        self._port_timeout = port_timeout
        self._http_timeout = http_timeout

    def run(self) -> None:
        try:
            from modules.ha_detector import scan
            matches = scan(
                self._hosts,
                progress_cb=lambda msg: self.status.emit(msg),
                port_timeout=self._port_timeout,
                http_timeout=self._http_timeout,
            )
            self.results_ready.emit(matches)
        except Exception as exc:
            self.error.emit(str(exc))


class MacLookupWorker(QThread):
    """
    Resolves a single MAC address to a vendor name using mac_lookup.lookup_vendor().
    Intended for right-click "Look up online" from any table row.
    """

    result_ready = pyqtSignal(str, str)   # (mac, vendor_or_empty)
    error        = pyqtSignal(str)

    def __init__(self, mac: str, parent=None):
        super().__init__(parent)
        self._mac = mac

    def run(self) -> None:
        try:
            from modules.mac_lookup import lookup_vendor
            vendor = lookup_vendor(self._mac) or ""
            self.result_ready.emit(self._mac, vendor)
        except Exception as exc:
            self.error.emit(str(exc))

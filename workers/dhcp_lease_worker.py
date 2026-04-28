"""
dhcp_lease_worker.py — QThread worker for DHCP lease scanning.
"""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

import modules.dhcp_lease_scanner as _scanner
from modules.dhcp_lease_scanner import DhcpLease
from typing import List


class DhcpLeaseWorker(QThread):
    """
    Runs dhcp_lease_scanner.scan() off the main thread.

    Signals:
        result_ready(list)  — emits the list of DhcpLease objects
        error(str)          — emits an error message string
    """

    result_ready: pyqtSignal = pyqtSignal(list)
    error:        pyqtSignal = pyqtSignal(str)

    def run(self) -> None:
        try:
            leases: List[DhcpLease] = _scanner.scan()
            self.result_ready.emit(leases)
        except Exception as exc:
            self.error.emit(str(exc))

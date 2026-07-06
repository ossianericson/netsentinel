"""
dhcp_lease_worker.py — QThread worker for DHCP lease scanning.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtCore import pyqtSignal

from modules.dhcp_lease_scanner import DhcpLease, scan as _scan
from workers.base_worker import BaseWorker


class DhcpLeaseWorker(BaseWorker):
    """
    Runs dhcp_lease_scanner.scan() off the main thread.

    Signals:
        result_ready(list)  — emits the list of DhcpLease objects
        error(str)          — inherited from BaseWorker
    """

    result_ready: pyqtSignal = pyqtSignal(list)

    def work(self) -> None:
        leases: List[DhcpLease] = _scan()
        self.result_ready.emit(leases)

"""
LldpWorker — QThread wrapper for modules.lldp_scanner.scan_lldp_neighbors.

Emits:
  result_ready(list)  — list[LldpNeighbor], always fired (empty on no frames)
  error(str)          — human-readable message for hard failures
  progress(str)       — status updates every ~3 s during the sniff window

"No LLDP frames seen" is a non-error result (empty list, no error signal).
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


class LldpWorker(QThread):
    """Background LLDP neighbor discovery worker."""

    result_ready = pyqtSignal(list)   # list[LldpNeighbor]
    error        = pyqtSignal(str)
    progress     = pyqtSignal(str)

    # total sniff duration; worker emits progress every _SLICE_S seconds
    _TOTAL_S = 15
    _SLICE_S = 3

    def __init__(
        self,
        iface: str,
        passive: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._iface   = iface
        self._passive = passive

    def run(self) -> None:
        try:
            from modules.utils import is_admin
        except ImportError:
            is_admin = lambda: False  # noqa: E731 — fallback for test environments

        if not is_admin():
            self.progress.emit(
                "LLDP: admin privileges required — passive sniff skipped. "
                "Run as administrator to discover managed switches."
            )
            self.result_ready.emit([])
            return

        try:
            from modules.lldp_scanner import scan_lldp_neighbors
        except ImportError:
            self.result_ready.emit([])
            return

        try:
            neighbors = scan_lldp_neighbors(
                iface=self._iface,
                timeout=self._TOTAL_S,
                passive=self._passive,
                progress_cb=self.progress.emit,
            )
            self.result_ready.emit(neighbors)
        except ImportError:
            # scapy LLDP not available on this platform
            self.result_ready.emit([])
        except Exception as exc:
            log.exception("LldpWorker: unexpected error on %s", self._iface)
            self.error.emit(
                f"LLDP discovery failed on {self._iface}: {exc}.\n"
                "Check that Npcap is installed and try running as administrator."
            )
            self.result_ready.emit([])

"""
HwDetectWorker — one-shot QThread that probes the gateway and matches
it against the hardware catalogue.

Emits detected(list[dict]) where each dict is a detect() result entry::

    {
        "plugin":     <catalogue entry>,
        "confidence": 0.0 – 1.0,
        "signals":    ["..."],
    }

Sorted by descending confidence; only entries >= 0.4 are included.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal

from workers.base_worker import BaseWorker


class HwDetectWorker(BaseWorker):
    """Probe *ip* once against the hardware catalogue, emit results."""

    detected = pyqtSignal(list)

    def __init__(
        self,
        ip: str,
        gateway_mac: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._ip          = ip
        self._gateway_mac = gateway_mac

    def work(self) -> None:
        from modules.hw_detect import detect, load_catalogue
        catalogue = load_catalogue(try_remote=False)
        matches   = detect(self._ip, self._gateway_mac, catalogue)
        self.detected.emit(matches)

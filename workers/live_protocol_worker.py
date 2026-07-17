"""
LiveProtocolWorker — QThread wrapper around modules.live_protocol_feed.LiveProtocolFeed.

Runs until stop()/request_stop() is called (long-lived loop, not a bounded
scan) — Protocol Visualizer's Live Mode toggle starts/stops this worker.
Checks is_admin() and is_npcap_available() up front and emits a translated
progress() message instead of attempting the capture, matching
workers/lldp_worker.py — never surfaces a raw scapy/permission error to the UI.

Signals:
  frame_event(object)  — LiveFrameEvent, emitted per captured packet
  error(str)           — inherited from BaseWorker
  progress(str)        — inherited from BaseWorker; heartbeat >= every 5s (RULE-AH2)
"""
from __future__ import annotations

import time

from PyQt6.QtCore import pyqtSignal

from workers.base_worker import BaseWorker

_HEARTBEAT_S = 5.0
_POLL_MS = 200


class LiveProtocolWorker(BaseWorker):
    """Long-lived live packet feed for one protocol (ARP or DNS)."""

    frame_event = pyqtSignal(object)   # LiveFrameEvent
    # error(str) and progress(str) are inherited from BaseWorker.

    def __init__(self, protocol: str, parent=None) -> None:
        super().__init__(parent)
        self._protocol = protocol
        self._feed = None

    def work(self) -> None:
        from modules.utils import is_admin, is_npcap_available

        if not is_admin():
            self.progress.emit(
                "Live capture requires administrator/root privileges — "
                "run NetSentinel as Administrator to enable it."
            )
            return
        if not is_npcap_available():
            self.progress.emit(
                "Live capture requires Npcap (Windows) or libpcap (macOS/Linux) — "
                "install the packet-capture driver to enable it."
            )
            return

        from modules.live_protocol_feed import LiveProtocolFeed

        self._feed = LiveProtocolFeed(
            protocol=self._protocol,
            on_event=self.frame_event.emit,
            on_error=self.error.emit,
        )
        self._feed.start()

        last_heartbeat = time.monotonic()
        while not self._should_stop():
            self.msleep(_POLL_MS)
            now = time.monotonic()
            if now - last_heartbeat >= _HEARTBEAT_S:
                self.progress.emit(
                    f"Live {self._protocol} capture running "
                    f"({self._feed.event_count} events)…"
                )
                last_heartbeat = now

        self._feed.stop()

    def stop(self) -> None:
        """Stop the sniffer immediately, then request the work() loop to exit."""
        if self._feed is not None:
            self._feed.stop()
        super().stop()

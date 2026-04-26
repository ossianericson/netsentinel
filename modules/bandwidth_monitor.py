"""
Per-device bandwidth monitor.

Uses Scapy AsyncSniffer to count bytes per source/destination MAC address.
No routing or flow export needed — works on any LAN by watching raw frames.

Each sample window (default 5 s) emits a snapshot dict:
    { mac: {"rx_bps": float, "tx_bps": float, "rx_bytes": int, "tx_bytes": int} }

"tx" = frames originating FROM this MAC (src == mac)
"rx" = frames destined  TO   this MAC (dst == mac, excluding broadcasts)

Requires Scapy + admin / root + Npcap (Windows).
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import AsyncSniffer, Ether  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class BandwidthEntry:
    mac: str
    ip: str = ""
    label: str = ""           # hostname or vendor label supplied by caller
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_bps: float = 0.0
    tx_bps: float = 0.0

    @property
    def total_bps(self) -> float:
        return self.rx_bps + self.tx_bps

    @property
    def total_mbps(self) -> float:
        return self.total_bps / 1_000_000


@dataclass
class BandwidthSnapshot:
    entries: List[BandwidthEntry] = field(default_factory=list)
    window_s: float = 5.0
    timestamp: float = field(default_factory=time.time)

    @property
    def top_talker(self) -> Optional[BandwidthEntry]:
        return max(self.entries, key=lambda e: e.total_bps, default=None)


# ── Counter sniffer ───────────────────────────────────────────────────────────

class BandwidthSniffer:
    """
    Counts bytes per MAC in rolling windows.
    Call snapshot() to get the current window and reset counters.
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._tx: Dict[str, int] = {}   # mac → bytes sent
        self._rx: Dict[str, int] = {}   # mac → bytes received
        self._sniffer = None

    def _handle(self, pkt):
        try:
            if not pkt.haslayer(Ether):
                return
            size = len(pkt)
            src  = pkt[Ether].src.lower()
            dst  = pkt[Ether].dst.lower()
            # Skip broadcast/multicast
            with self._lock:
                self._tx[src] = self._tx.get(src, 0) + size
                if dst and not dst.startswith("ff:") and not dst.startswith("01:"):
                    self._rx[dst] = self._rx.get(dst, 0) + size
        except Exception:
            pass

    def start(self):
        if not SCAPY_AVAILABLE:
            return False
        try:
            self._sniffer = AsyncSniffer(
                prn=self._handle,
                store=False,
            )
            self._sniffer.start()
            return True
        except Exception:
            return False

    def stop(self):
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass

    def snapshot(self, window_s: float, label_map: Dict[str, str]) -> BandwidthSnapshot:
        """
        Grab current counters, reset them, and return a BandwidthSnapshot.
        *label_map* is {mac: label_string} for display purposes.
        """
        with self._lock:
            tx = dict(self._tx)
            rx = dict(self._rx)
            self._tx.clear()
            self._rx.clear()

        all_macs = set(tx) | set(rx)
        entries: List[BandwidthEntry] = []
        for mac in all_macs:
            tx_b = tx.get(mac, 0)
            rx_b = rx.get(mac, 0)
            entries.append(BandwidthEntry(
                mac=mac,
                label=label_map.get(mac, mac),
                tx_bytes=tx_b,
                rx_bytes=rx_b,
                tx_bps=tx_b / window_s if window_s > 0 else 0,
                rx_bps=rx_b / window_s if window_s > 0 else 0,
            ))
        entries.sort(key=lambda e: e.total_bps, reverse=True)
        return BandwidthSnapshot(entries=entries, window_s=window_s)


# ── Continuous monitor (used by worker) ──────────────────────────────────────

class BandwidthMonitor:
    """
    Runs a BandwidthSniffer and emits a new BandwidthSnapshot every
    *interval_s* seconds until stop() is called.
    """

    def __init__(
        self,
        interval_s: float = 5.0,
        on_snapshot: Optional[Callable[[BandwidthSnapshot], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        label_map: Optional[Dict[str, str]] = None,
        stop_event: Optional[threading.Event] = None,
    ):
        self.interval_s = interval_s
        self.on_snapshot = on_snapshot or (lambda s: None)
        self.on_error    = on_error    or (lambda m: None)
        self.label_map   = label_map   or {}
        self.stop_event  = stop_event  or threading.Event()

    def run(self):
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy not available — bandwidth monitoring requires:\n"
                "  pip install scapy\n"
                "  Windows: Npcap from https://npcap.com (run as Administrator)"
            )
            return

        sniffer = BandwidthSniffer()
        if not sniffer.start():
            self.on_error(
                "Failed to start packet capture. "
                "Run as Administrator/root with Npcap installed."
            )
            return

        try:
            while not self.stop_event.is_set():
                self.stop_event.wait(timeout=self.interval_s)
                snap = sniffer.snapshot(self.interval_s, self.label_map)
                self.on_snapshot(snap)
        finally:
            sniffer.stop()

    def stop(self):
        self.stop_event.set()

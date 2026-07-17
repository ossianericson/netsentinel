"""
Module — Live protocol feed for Protocol Visualizer "Live Mode" (Phase A5).

Wraps a scapy ``AsyncSniffer`` per protocol (ARP, DNS) and emits normalized
``LiveFrameEvent`` objects. Pattern-matches the ``ARPSniffer`` in
modules/arp_monitor.py (``AsyncSniffer(filter=..., prn=..., store=False)``),
but runs until ``stop()`` is called rather than for a fixed duration — Live
Mode is a user-toggled stream, not a scan with a bounded window.

Rate-limited to <=4 events/sec so the canvas stays readable; events beyond
that in the same 1s window are dropped and counted (``overflow_count``).
Gracefully degrades when Scapy is unavailable, same as arp_monitor.py.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import ARP, DNS, DNSQR, IP, Ether, AsyncSniffer  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal


SUPPORTED_PROTOCOLS = ("ARP", "DNS")

_BPF_FILTERS = {
    "ARP": "arp",
    "DNS": "udp port 53",
}

_MAX_EVENTS_PER_SEC = 4


@dataclass
class LiveFrameEvent:
    protocol: str        # "ARP" | "DNS"
    src_ip: str
    src_mac: str
    dst_ip: str
    summary: str
    is_reply: bool
    is_broadcast: bool
    ts: float


class LiveProtocolFeed:
    """Runs a live per-protocol packet capture until :meth:`stop` is called."""

    def __init__(
        self,
        protocol: str,
        on_event: Callable[[LiveFrameEvent], None],
        on_error: Callable[[str], None],
    ):
        if protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"unsupported protocol for live feed: {protocol!r}")
        self.protocol = protocol
        self.on_event = on_event
        self.on_error = on_error
        self._sniffer: Optional[Any] = None   # AsyncSniffer when SCAPY_AVAILABLE; untyped (no stubs)
        self.event_count = 0
        self.overflow_count = 0
        self._window_start = 0.0
        self._window_count = 0

    # ── Rate limiting ────────────────────────────────────────────────────────

    def _rate_limited(self) -> bool:
        """True if this event should be dropped (>4 already this 1s window)."""
        now = time.monotonic()
        if now - self._window_start >= 1.0:
            self._window_start = now
            self._window_count = 0
        self._window_count += 1
        if self._window_count > _MAX_EVENTS_PER_SEC:
            self.overflow_count += 1
            return True
        return False

    # ── Packet handlers ──────────────────────────────────────────────────────

    def _handle_arp(self, pkt) -> None:
        try:
            if not (pkt.haslayer(ARP) and pkt.haslayer(Ether)):
                return
            arp = pkt[ARP]
            if arp.op not in (1, 2):
                return
            if self._rate_limited():
                return
            is_broadcast = arp.op == 1   # gratuitous / request ARPs radiate
            src_mac = arp.hwsrc.lower()
            evt = LiveFrameEvent(
                protocol="ARP",
                src_ip=arp.psrc,
                src_mac=src_mac,
                dst_ip=arp.pdst,
                summary=(
                    f"Who has {arp.pdst}? Tell {arp.psrc}" if is_broadcast
                    else f"{arp.psrc} is at {src_mac}"
                ),
                is_reply=(arp.op == 2),
                is_broadcast=is_broadcast,
                ts=time.time(),
            )
            self.event_count += 1
            self.on_event(evt)
        except Exception:
            pass  # non-fatal — a malformed packet must never kill the sniffer

    def _handle_dns(self, pkt) -> None:
        try:
            if not (pkt.haslayer(DNS) and pkt.haslayer(IP)):
                return
            dns = pkt[DNS]
            ip = pkt[IP]
            if self._rate_limited():
                return
            is_reply = dns.qr == 1
            qname = ""
            if dns.qdcount and pkt.haslayer(DNSQR):
                try:
                    qname = pkt[DNSQR].qname.decode("utf-8", errors="replace").rstrip(".")
                except Exception:
                    qname = ""  # non-fatal — malformed question section
            if qname:
                summary = f"Response for {qname}" if is_reply else f"Query for {qname}"
            else:
                summary = "DNS response" if is_reply else "DNS query"
            evt = LiveFrameEvent(
                protocol="DNS",
                src_ip=ip.src,
                src_mac=(pkt[Ether].src.lower() if pkt.haslayer(Ether) else ""),
                dst_ip=ip.dst,
                summary=summary,
                is_reply=is_reply,
                is_broadcast=False,
                ts=time.time(),
            )
            self.event_count += 1
            self.on_event(evt)
        except Exception:
            pass  # non-fatal — a malformed packet must never kill the sniffer

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy is not installed. Install it with: pip install scapy\n"
                "On Windows you also need Npcap from https://npcap.com"
            )
            return
        handler = self._handle_arp if self.protocol == "ARP" else self._handle_dns
        try:
            self._sniffer = AsyncSniffer(
                filter=_BPF_FILTERS[self.protocol],
                prn=handler,
                store=False,
            )
            self._sniffer.start()
        except Exception as exc:
            self.on_error(
                f"Failed to start live {self.protocol} capture: {exc}\n"
                "Run as Administrator/root with Npcap installed."
            )

    def stop(self) -> None:
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal — sniffer may already be stopped

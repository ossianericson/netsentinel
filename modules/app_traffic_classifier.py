"""
modules/app_traffic_classifier.py — Port-to-application traffic classifier.

Tracks per-host per-protocol bandwidth using Scapy packet capture.
No nDPI / deep-packet-inspection required — uses well-known port heuristics
to classify TCP/UDP flows into named application categories.

Categories: Web, DNS, Streaming, SSH/Admin, Email, Gaming, VPN, P2P,
            File Share, Database, IoT, System, Discovery, VoIP, Other

Requires Scapy + admin/root + Npcap (Windows).  Degrades gracefully when
Scapy is absent — callers check SCAPY_AVAILABLE before starting.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from modules.cdn_ranges import classify_cdn_ip

SCAPY_AVAILABLE = False
try:
    from scapy.all import AsyncSniffer, Ether, IP, TCP, UDP  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal — feature degrades gracefully


# ── Port → (category, app_name) mapping ──────────────────────────────────────

_PORT_MAP: Dict[Tuple[str, int], Tuple[str, str]] = {
    # Web
    ("tcp", 80):    ("Web", "HTTP"),
    ("tcp", 443):   ("Web", "HTTPS"),
    ("tcp", 8080):  ("Web", "HTTP-Alt"),
    ("tcp", 8443):  ("Web", "HTTPS-Alt"),
    ("tcp", 8888):  ("Web", "HTTP-Alt"),
    # DNS
    ("udp", 53):    ("DNS", "DNS"),
    ("tcp", 53):    ("DNS", "DNS/TCP"),
    ("tcp", 853):   ("DNS", "DNS-over-TLS"),
    # Streaming
    ("tcp", 1935):  ("Streaming", "RTMP"),
    ("tcp", 32400): ("Streaming", "Plex"),
    ("tcp", 8096):  ("Streaming", "Jellyfin"),
    ("tcp", 8324):  ("Streaming", "Plex-GDM"),
    ("tcp", 32469): ("Streaming", "Plex-DLNA"),
    ("udp", 1234):  ("Streaming", "VLC-Multicast"),
    # SSH / Remote admin
    ("tcp", 22):    ("SSH/Admin", "SSH"),
    ("tcp", 3389):  ("SSH/Admin", "RDP"),
    ("tcp", 5900):  ("SSH/Admin", "VNC"),
    ("tcp", 5901):  ("SSH/Admin", "VNC"),
    ("tcp", 23):    ("SSH/Admin", "Telnet"),
    # Email
    ("tcp", 25):    ("Email", "SMTP"),
    ("tcp", 587):   ("Email", "SMTP-Submit"),
    ("tcp", 465):   ("Email", "SMTPS"),
    ("tcp", 143):   ("Email", "IMAP"),
    ("tcp", 993):   ("Email", "IMAPS"),
    ("tcp", 110):   ("Email", "POP3"),
    ("tcp", 995):   ("Email", "POP3S"),
    # Gaming
    ("udp", 3074):  ("Gaming", "Xbox"),
    ("tcp", 3074):  ("Gaming", "Xbox"),
    ("udp", 3478):  ("Gaming", "PlayStation"),
    ("udp", 3479):  ("Gaming", "PlayStation"),
    ("udp", 7777):  ("Gaming", "Game-Server"),
    ("udp", 27015): ("Gaming", "Steam"),
    ("tcp", 27015): ("Gaming", "Steam"),
    ("udp", 27016): ("Gaming", "Steam"),
    ("udp", 4380):  ("Gaming", "Steam"),
    ("tcp", 2099):  ("Gaming", "EA-Origin"),
    # VPN
    ("udp", 500):   ("VPN", "IKE"),
    ("udp", 4500):  ("VPN", "IPSec-NAT-T"),
    ("tcp", 1723):  ("VPN", "PPTP"),
    ("udp", 1194):  ("VPN", "OpenVPN"),
    ("tcp", 1194):  ("VPN", "OpenVPN"),
    ("udp", 51820): ("VPN", "WireGuard"),
    ("tcp", 443):   ("Web", "HTTPS"),   # WireGuard also uses 443 but HTTP wins
    # P2P / BitTorrent
    ("tcp", 6881):  ("P2P", "BitTorrent"),
    ("udp", 6881):  ("P2P", "BitTorrent"),
    ("tcp", 6882):  ("P2P", "BitTorrent"),
    ("tcp", 6883):  ("P2P", "BitTorrent"),
    ("tcp", 6884):  ("P2P", "BitTorrent"),
    ("tcp", 6885):  ("P2P", "BitTorrent"),
    ("tcp", 6886):  ("P2P", "BitTorrent"),
    ("tcp", 6887):  ("P2P", "BitTorrent"),
    ("tcp", 6888):  ("P2P", "BitTorrent"),
    ("tcp", 6889):  ("P2P", "BitTorrent"),
    # File share
    ("tcp", 445):   ("File Share", "SMB"),
    ("tcp", 139):   ("File Share", "NetBIOS"),
    ("tcp", 21):    ("File Share", "FTP"),
    ("tcp", 990):   ("File Share", "FTPS"),
    ("tcp", 2049):  ("File Share", "NFS"),
    # Database
    ("tcp", 3306):  ("Database", "MySQL"),
    ("tcp", 5432):  ("Database", "PostgreSQL"),
    ("tcp", 1433):  ("Database", "MSSQL"),
    ("tcp", 27017): ("Database", "MongoDB"),
    ("tcp", 6379):  ("Database", "Redis"),
    ("tcp", 5984):  ("Database", "CouchDB"),
    # IoT / Smart Home
    ("tcp", 1883):  ("IoT", "MQTT"),
    ("tcp", 8883):  ("IoT", "MQTT-TLS"),
    ("udp", 5683):  ("IoT", "CoAP"),
    ("tcp", 4443):  ("IoT", "HomeKit"),
    # System
    ("udp", 123):   ("System", "NTP"),
    ("udp", 161):   ("System", "SNMP"),
    ("udp", 162):   ("System", "SNMP-Trap"),
    ("tcp", 161):   ("System", "SNMP"),
    ("tcp", 514):   ("System", "Syslog"),
    ("udp", 514):   ("System", "Syslog"),
    # Discovery
    ("udp", 1900):  ("Discovery", "SSDP"),
    ("udp", 5353):  ("Discovery", "mDNS"),
    ("tcp", 5357):  ("Discovery", "WS-Discovery"),
    # VoIP
    ("udp", 5060):  ("VoIP", "SIP"),
    ("tcp", 5060):  ("VoIP", "SIP"),
    ("tcp", 5061):  ("VoIP", "SIP-TLS"),
    ("udp", 4569):  ("VoIP", "IAX2"),
    ("udp", 3478):  ("VoIP", "STUN"),
}

# Ordered list of canonical categories (display order in charts)
CATEGORY_ORDER: List[str] = [
    "Web", "DNS", "Streaming", "SSH/Admin", "Email",
    "Gaming", "VPN", "P2P", "File Share", "Database",
    "IoT", "System", "Discovery", "VoIP", "Other",
]


def classify_port(proto: str, port: int) -> Tuple[str, str]:
    """Return (category, app_name) for a given protocol + port number."""
    return _PORT_MAP.get((proto.lower(), port), ("Other", f"Port {port}"))


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class AppFlowEntry:
    mac: str
    category: str
    app: str
    bytes_total: int = 0
    label: str = ""   # display label (hostname or IP)
    cdn: Optional[str] = None   # known CDN/streaming provider, if recognised (S6-2)


@dataclass
class AppHostSnapshot:
    mac: str
    label: str
    flows: List[AppFlowEntry] = field(default_factory=list)
    total_bytes: int = 0
    window_s: float = 10.0

    def category_totals(self) -> Dict[str, int]:
        """Return {category: bytes} mapping."""
        out: Dict[str, int] = {}
        for f in self.flows:
            out[f.category] = out.get(f.category, 0) + f.bytes_total
        return out


@dataclass
class AppTrafficSnapshot:
    hosts: List[AppHostSnapshot] = field(default_factory=list)
    window_s: float = 10.0
    timestamp: float = field(default_factory=time.time)

    @property
    def top_host(self) -> Optional[AppHostSnapshot]:
        return max(self.hosts, key=lambda h: h.total_bytes, default=None)


# ── Sniffer ───────────────────────────────────────────────────────────────────

class AppTrafficSniffer:
    """
    Scapy AsyncSniffer that counts bytes per source-MAC per (category, app).
    Thread-safe; call snapshot() each window to drain and reset counters.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {mac: {(category, app, cdn): bytes}}
        self._flows: Dict[str, Dict[Tuple[str, str, Optional[str]], int]] = {}
        self._sniffer: Optional[Any] = None

    def _handle(self, pkt) -> None:
        try:
            if not pkt.haslayer(Ether) or not pkt.haslayer(IP):
                return
            src_mac = pkt[Ether].src.lower()
            size = len(pkt)
            dest_ip = pkt[IP].dst

            if pkt.haslayer(TCP):
                cat, app = classify_port("tcp", pkt[TCP].dport)
            elif pkt.haslayer(UDP):
                cat, app = classify_port("udp", pkt[UDP].dport)
            else:
                cat, app = "Other", "Other"

            cdn = classify_cdn_ip(dest_ip)

            with self._lock:
                if src_mac not in self._flows:
                    self._flows[src_mac] = {}
                key = (cat, app, cdn)
                self._flows[src_mac][key] = self._flows[src_mac].get(key, 0) + size
        except Exception:
            pass  # non-fatal — malformed or truncated packet

    def start(self) -> bool:
        if not SCAPY_AVAILABLE:
            return False
        try:
            self._sniffer = AsyncSniffer(
                filter="ip",
                prn=self._handle,
                store=False,
            )
            self._sniffer.start()
            return True
        except Exception:
            return False

    def stop(self) -> None:
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal

    def snapshot(self, window_s: float, label_map: Dict[str, str]) -> AppTrafficSnapshot:
        """Drain current counters and return a snapshot, resetting state."""
        with self._lock:
            raw = {mac: dict(flows) for mac, flows in self._flows.items()}
            self._flows.clear()

        hosts: List[AppHostSnapshot] = []
        for mac, flow_dict in raw.items():
            total = sum(flow_dict.values())
            if total == 0:
                continue
            entries = [
                AppFlowEntry(
                    mac=mac,
                    category=cat,
                    app=app,
                    bytes_total=b,
                    label=label_map.get(mac, mac),
                    cdn=cdn,
                )
                for (cat, app, cdn), b in sorted(flow_dict.items(), key=lambda x: -x[1])
            ]
            hosts.append(AppHostSnapshot(
                mac=mac,
                label=label_map.get(mac, mac),
                flows=entries,
                total_bytes=total,
                window_s=window_s,
            ))

        hosts.sort(key=lambda h: h.total_bytes, reverse=True)
        return AppTrafficSnapshot(hosts=hosts, window_s=window_s)


# ── Continuous monitor (used by worker) ──────────────────────────────────────

class AppTrafficMonitor:
    """
    Runs AppTrafficSniffer in a loop and calls on_snapshot every interval_s.
    Blocks until stop_event is set.
    """

    def __init__(
        self,
        interval_s: float = 10.0,
        on_snapshot: Optional[Callable[[AppTrafficSnapshot], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        label_map: Optional[Dict[str, str]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self.interval_s = interval_s
        self.on_snapshot = on_snapshot or (lambda s: None)
        self.on_error    = on_error    or (lambda m: None)
        self.label_map   = label_map   or {}
        self.stop_event  = stop_event  or threading.Event()

    def run(self) -> None:
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy not available — app traffic analysis requires:\n"
                "  pip install scapy\n"
                "  Windows: Npcap from https://npcap.com (run as Administrator)"
            )
            return

        sniffer = AppTrafficSniffer()
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

    def stop(self) -> None:
        self.stop_event.set()

"""
Module 9 — ARP Spoof / MITM Detector

Builds a trusted MAC→IP baseline from the current ARP table, then sniffs
live ARP replies to detect:

  1. IP takeover  — a new MAC claims an IP that already has an owner
  2. Gateway MAC  — any device advertising the gateway IP with a different MAC
  3. Gratuitous ARP flood — a device repeatedly broadcasting its own MAC
     (common stealth-MITM technique)  4. MAC clone / dual-claim — the same MAC appears on two different IP
     addresses simultaneously (possible MAC cloning or spoof)
Requires Scapy + admin / root for raw packet capture.
Gracefully degrades when Scapy is unavailable.
"""

import platform
import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import AsyncSniffer, ARP, Ether  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SpoofEvent:
    event_type: str          # "IP_TAKEOVER" | "GATEWAY_HIJACK" | "GRAT_FLOOD"
    attacker_mac: str
    attacker_ip: str
    victim_ip: str           # IP that was stolen / hijacked
    original_mac: str        # MAC that previously owned victim_ip (empty for flood)
    is_rogue: bool = True
    verdict: str = ""


@dataclass
class ARPScanResult:
    events: List[SpoofEvent] = field(default_factory=list)
    baseline: Dict[str, str] = field(default_factory=dict)   # ip → mac
    total_arp_packets: int = 0
    plain_verdict: str = ""


# ── Baseline builder ──────────────────────────────────────────────────────────

def _build_baseline() -> Dict[str, str]:
    """Read the current ARP cache and return {ip: mac}."""
    system = platform.system()
    extra: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if system == "Windows" else {}
    baseline: Dict[str, str] = {}
    try:
        raw = subprocess.check_output(["arp", "-a"], text=True, timeout=10, **extra)
        for line in raw.splitlines():
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F:–-]{17})", line)
            if m:
                ip  = m.group(1)
                mac = m.group(2).replace("-", ":").lower()
                if mac != "ff:ff:ff:ff:ff:ff":
                    baseline[ip] = mac
    except Exception:
        pass  # non-fatal
    return baseline


# ── Sniffer ───────────────────────────────────────────────────────────────────

class ARPSniffer:
    def __init__(
        self,
        baseline: Dict[str, str],
        gateway_ip: Optional[str],
        on_event: Callable[[SpoofEvent], None],
        on_error: Callable[[str], None],
        duration: int = 30,
        stop_event: Optional[threading.Event] = None,
    ):
        self.baseline   = dict(baseline)   # mutable working copy
        self.gateway_ip = gateway_ip
        self.on_event   = on_event
        self.on_error   = on_error
        self.duration   = duration
        self.stop_event = stop_event or threading.Event()
        self._sniffer   = None
        self._grat_count: Dict[str, int] = {}   # mac → gratuitous count
        self._mac_to_ips: Dict[str, set]  = {}   # mac → set of seen IPs
        self._mac_clone_alerted: set      = set() # macs already fired MAC_CLONE
        self.packet_count = 0

    def _handle(self, pkt):
        try:
            if not (pkt.haslayer(ARP) and pkt.haslayer(Ether)):
                return
            arp = pkt[ARP]
            # Only care about ARP replies (op=2) and gratuitous ARPs (op=1 where src==dst)
            if arp.op not in (1, 2):
                return

            self.packet_count += 1
            src_ip  = arp.psrc
            src_mac = arp.hwsrc.lower()

            # Gratuitous ARP: sender and target IP are the same
            if arp.op == 1 and arp.psrc == arp.pdst:
                self._grat_count[src_mac] = self._grat_count.get(src_mac, 0) + 1
                if self._grat_count[src_mac] == 5:   # threshold: 5 in the scan window
                    evt = SpoofEvent(
                        event_type="GRAT_FLOOD",
                        attacker_mac=src_mac,
                        attacker_ip=src_ip,
                        victim_ip=src_ip,
                        original_mac="",
                        verdict=(
                            f"GRATUITOUS ARP FLOOD: {src_mac} ({src_ip}) is sending "
                            "repeated unprompted ARP announcements — common MITM/stealth "
                            "poisoning technique. Investigate this device."
                        ),
                    )
                    self.on_event(evt)
                return

            if arp.op != 2:
                return

            # ARP Reply — check for IP takeover
            known_mac = self.baseline.get(src_ip)

            if known_mac and known_mac != src_mac:
                # Is this the gateway being hijacked?
                if self.gateway_ip and src_ip == self.gateway_ip:
                    etype = "GATEWAY_HIJACK"
                    msg   = (
                        f"GATEWAY HIJACK: {src_mac} is now claiming gateway IP "
                        f"{src_ip} which was previously owned by {known_mac}. "
                        "All your traffic may be passing through this device. "
                        "FIX: Run as Administrator, check device list immediately."
                    )
                else:
                    etype = "IP_TAKEOVER"
                    msg   = (
                        f"ARP SPOOF: {src_mac} is claiming {src_ip}, previously "
                        f"owned by {known_mac}. Classic MITM attack pattern."
                    )
                evt = SpoofEvent(
                    event_type=etype,
                    attacker_mac=src_mac,
                    attacker_ip=src_ip,
                    victim_ip=src_ip,
                    original_mac=known_mac,
                    verdict=msg,
                )
                self.on_event(evt)

            # Update working baseline with what we see
            self.baseline[src_ip] = src_mac

            # ── MAC clone / dual-claim detection ─────────────────────────
            if src_mac not in self._mac_to_ips:
                self._mac_to_ips[src_mac] = set()
            prev_ips = self._mac_to_ips[src_mac]
            if prev_ips and src_ip not in prev_ips and src_mac not in self._mac_clone_alerted:
                other_ip = next(iter(prev_ips))
                evt = SpoofEvent(
                    event_type="MAC_CLONE",
                    attacker_mac=src_mac,
                    attacker_ip=src_ip,
                    victim_ip=other_ip,
                    original_mac=src_mac,
                    verdict=(
                        f"MAC CLONE/DUAL-CLAIM: {src_mac} is seen on both {src_ip} and "
                        f"{other_ip} simultaneously. Possible MAC cloning attack or "
                        "misconfigured VM/container. Investigate both addresses."
                    ),
                )
                self.on_event(evt)
                self._mac_clone_alerted.add(src_mac)
            self._mac_to_ips[src_mac].add(src_ip)

        except Exception:
            pass  # non-fatal

    def start(self):
        if not SCAPY_AVAILABLE:
            self.on_error(
                "Scapy is not installed. Install it with: pip install scapy\n"
                "On Windows you also need Npcap from https://npcap.com"
            )
            return
        try:
            self._sniffer = AsyncSniffer(
                filter="arp",
                prn=self._handle,
                store=False,
                timeout=self.duration,
            )
            self._sniffer.start()
        except Exception as exc:
            self.on_error(
                f"Failed to start ARP capture: {exc}\n"
                "Run as Administrator/root with Npcap installed."
            )

    def stop(self):
        try:
            if self._sniffer:
                self._sniffer.stop()
        except Exception:
            pass  # non-fatal


# ── Public scan entry point ───────────────────────────────────────────────────

def scan(
    gateway_ip: Optional[str] = None,
    on_event: Optional[Callable[[SpoofEvent], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    duration: int = 30,
    progress_cb: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> ARPScanResult:
    """
    Blocking scan — builds ARP baseline then listens for spoofing events
    for *duration* seconds.  Returns ARPScanResult summary.
    """
    _cb  = progress_cb or (lambda m: None)
    _err = on_error    or (lambda m: None)
    _evt = on_event    or (lambda e: None)

    if not SCAPY_AVAILABLE:
        msg = (
            "Scapy not available — ARP spoof detection requires:\n"
            "  pip install scapy\n"
            "  Windows: Npcap from https://npcap.com (run as Administrator)"
        )
        _err(msg)
        result = ARPScanResult()
        result.plain_verdict = msg
        return result

    _cb("Building ARP baseline from current cache…")
    baseline = _build_baseline()
    _cb(f"Baseline: {len(baseline)} known IP→MAC mappings. Monitoring for spoofing…")

    events: list = []
    lock = threading.Lock()

    def _collect(evt: SpoofEvent):
        with lock:
            events.append(evt)
        _evt(evt)

    sniffer = ARPSniffer(
        baseline=baseline,
        gateway_ip=gateway_ip,
        on_event=_collect,
        on_error=_err,
        duration=duration,
        stop_event=stop_event,
    )
    sniffer.start()

    import time
    for i in range(duration):
        if stop_event and stop_event.is_set():
            _cb("ARP monitor cancelled.")
            break
        time.sleep(1)
        remaining = duration - i - 1
        _cb(f"ARP monitor: {remaining}s remaining…")

    sniffer.stop()

    hijack   = [e for e in events if e.event_type == "GATEWAY_HIJACK"]
    takeover = [e for e in events if e.event_type == "IP_TAKEOVER"]
    flood    = [e for e in events if e.event_type == "GRAT_FLOOD"]
    clone    = [e for e in events if e.event_type == "MAC_CLONE"]

    if hijack:
        plain = (
            f"CRITICAL: Gateway MAC hijack detected! "
            + " | ".join(e.verdict for e in hijack[:2])
        )
    elif takeover:
        plain = (
            f"{len(takeover)} ARP spoofing event(s) detected. "
            + " | ".join(e.verdict for e in takeover[:2])
        )
    elif clone:
        plain = (
            f"{len(clone)} MAC clone/dual-claim event(s) detected. "
            + " | ".join(e.verdict for e in clone[:2])
        )
    elif flood:
        plain = (
            f"{len(flood)} device(s) sending gratuitous ARP floods — investigate."
        )
    else:
        plain = (
            f"No ARP spoofing detected. "
            f"Monitored {sniffer.packet_count} ARP packet(s) over {duration}s."
        )

    return ARPScanResult(
        events=events,
        baseline=baseline,
        total_arp_packets=sniffer.packet_count,
        plain_verdict=plain,
    )

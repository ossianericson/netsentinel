"""
Module 3 — Broadcast & Multicast Storm Analyser

Samples all interfaces for a configurable number of seconds using Scapy.
Calculates broadcast/multicast packet rates and identifies top offenders.
Requires administrator / root privileges and Scapy.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SCAPY_AVAILABLE = False
try:
    from scapy.all import AsyncSniffer, Ether  # type: ignore
    SCAPY_AVAILABLE = True
except ImportError:
    pass  # non-fatal

BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"

# Default thresholds (packets / second)
THRESHOLD_WARNING = 50
THRESHOLD_STORM = 150


@dataclass
class StormResult:
    duration_seconds: int = 0
    total_broadcast: int = 0
    total_multicast: int = 0
    total_unicast: int = 0
    bcast_per_sec: float = 0.0
    mcast_per_sec: float = 0.0
    bcast_ratio: float = 0.0          # broadcast / total
    top_sources: List[tuple] = field(default_factory=list)  # [(mac, count)]
    storm_level: str = "CLEAN"        # CLEAN / WARNING / STORM
    plain_verdict: str = ""
    rogue_matches: List[str] = field(default_factory=list)  # MACs appearing in both Module1 & this


def scan(
    duration: int = 10,
    warn_threshold: int = THRESHOLD_WARNING,
    storm_threshold: int = THRESHOLD_STORM,
    known_rogue_macs: Optional[List[str]] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> StormResult:
    """
    Sniff all packets for `duration` seconds and return a StormResult.
    """
    result = StormResult(duration_seconds=duration)
    _on_error = on_error or (lambda m: None)

    if not SCAPY_AVAILABLE:
        msg = (
            "Scapy is not installed — storm analysis unavailable.\n"
            "Install: pip install scapy\n"
            "Windows also needs Npcap: https://npcap.com"
        )
        _on_error(msg)
        result.plain_verdict = msg
        result.storm_level = "UNKNOWN"
        return result

    bcast_count: int = 0
    mcast_count: int = 0
    unicast_count: int = 0
    src_counter: Dict[str, int] = defaultdict(int)
    lock = threading.Lock()

    def _handle(pkt):
        nonlocal bcast_count, mcast_count, unicast_count
        try:
            if not pkt.haslayer(Ether):
                return
            eth = pkt[Ether]
            dst = eth.dst.lower()
            src = eth.src.lower()
            with lock:
                if dst == BROADCAST_MAC:
                    bcast_count += 1
                    src_counter[src] += 1
                elif dst.startswith(("01:", "03:", "33:")):
                    mcast_count += 1
                    src_counter[src] += 1
                else:
                    unicast_count += 1
        except Exception:
            pass  # non-fatal

    sniffer = AsyncSniffer(prn=_handle, store=False)
    try:
        sniffer.start()
    except Exception as exc:
        msg = (
            f"Failed to start packet capture: {exc}\n"
            "Run as Administrator/root and ensure Npcap is installed."
        )
        _on_error(msg)
        result.plain_verdict = msg
        result.storm_level = "UNKNOWN"
        return result

    for i in range(duration):
        time.sleep(1)
        if progress_cb:
            progress_cb(f"Storm analysis: {duration - i - 1}s remaining...")

    sniffer.stop()

    total = bcast_count + mcast_count + unicast_count
    bps = bcast_count / max(duration, 1)
    mps = mcast_count / max(duration, 1)
    ratio = bcast_count / max(total, 1)

    top5 = sorted(src_counter.items(), key=lambda x: x[1], reverse=True)[:5]

    rogue_matches: List[str] = []
    if known_rogue_macs:
        rogue_set = {m.lower() for m in known_rogue_macs}
        rogue_matches = [mac for mac, _ in top5 if mac in rogue_set]

    # Determine storm level
    if bps >= storm_threshold:
        level = "STORM"
    elif bps >= warn_threshold:
        level = "WARNING"
    else:
        level = "CLEAN"

    # Plain verdict
    if level == "STORM":
        verdict = (
            f"BROADCAST STORM DETECTED: {bps:.1f} broadcast packets/sec "
            f"(threshold: {storm_threshold}/s). "
            "Your network is being flooded, which will cause severe slowdowns and outages."
        )
    elif level == "WARNING":
        verdict = (
            f"Elevated broadcast traffic: {bps:.1f} packets/sec "
            f"(warning threshold: {warn_threshold}/s). "
            "Monitor closely — this can degrade network performance."
        )
    else:
        verdict = (
            f"Broadcast traffic is normal: {bps:.1f} packets/sec. "
            f"Multicast: {mps:.1f}/sec. No storm conditions detected."
        )

    if rogue_matches:
        verdict += (
            f" CONFIRMED: The following MACs appear as both known-rogue devices "
            f"AND top broadcast sources: {', '.join(rogue_matches)}. "
            "This confirms active network sabotage."
        )

    result.total_broadcast = bcast_count
    result.total_multicast = mcast_count
    result.total_unicast = unicast_count
    result.bcast_per_sec = round(bps, 2)
    result.mcast_per_sec = round(mps, 2)
    result.bcast_ratio = round(ratio, 4)
    result.top_sources = top5
    result.storm_level = level
    result.rogue_matches = rogue_matches
    result.plain_verdict = verdict
    return result

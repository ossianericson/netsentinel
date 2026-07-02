"""
arp_watch — opt-in background ARP spoof watch cycle (V6 Sprint 4.1).

Thin wrapper around modules.arp_monitor.scan() so a ProactiveProbeWorker can
run a bounded-duration ARP baseline+listen cycle on a fixed interval instead
of only while the ARP Spoof Watch page is open. No new detection logic here
— arp_monitor.py already builds the baseline and classifies IP_TAKEOVER /
GATEWAY_HIJACK / GRAT_FLOOD / MAC_CLONE events; this module just exposes a
result shape evaluate_arp_watch_checks() in alert_engine_checks4.py can
consume, same reuse pattern as modules/exposure_watch.py (V6 Sprint 3.4).

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from modules import arp_monitor
from modules.arp_monitor import SpoofEvent


@dataclass
class ArpWatchReport:
    """Result of one background ARP watch cycle."""
    events: List[SpoofEvent] = field(default_factory=list)


def run_arp_watch_cycle(gateway_ip: Optional[str] = None, duration: int = 20) -> ArpWatchReport:
    """
    Run one bounded ARP baseline+listen cycle and return any spoofing events
    detected during the window. Each cycle rebuilds its own baseline from the
    current ARP cache (arp_monitor.scan()'s own behaviour) — no cross-cycle
    diffing is needed since every SpoofEvent is already a "this happened
    right now" detection.
    """
    result = arp_monitor.scan(gateway_ip=gateway_ip, duration=duration)
    return ArpWatchReport(events=list(result.events))

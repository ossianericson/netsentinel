"""
dhcp_watch — opt-in background rogue-DHCP watch cycle (V6 Sprint 4.2).

Thin wrapper around modules.dhcp_detector.scan() so a ProactiveProbeWorker
can send a DHCPDISCOVER probe and collect offers on a fixed interval instead
of only when the DHCP Rogue Monitor page is manually triggered. No new
detection logic here — dhcp_detector.py already classifies is_rogue offers;
this module just exposes a result shape evaluate_dhcp_watch_checks() in
alert_engine_checks4.py can consume, same reuse pattern as
modules/exposure_watch.py (V6 Sprint 3.4).

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from modules import dhcp_detector
from modules.dhcp_detector import DHCPOffer


@dataclass
class DhcpWatchReport:
    """Result of one background DHCP watch cycle."""
    offers: List[DHCPOffer] = field(default_factory=list)
    rogue_offers: List[DHCPOffer] = field(default_factory=list)


def run_dhcp_watch_cycle(known_dhcp_server: Optional[str] = None, duration: int = 8) -> DhcpWatchReport:
    """
    Send one DHCPDISCOVER probe and collect offers for *duration* seconds.
    Returns all offers plus the subset dhcp_detector already flagged rogue
    (server IP different from known_dhcp_server).
    """
    result = dhcp_detector.scan(known_dhcp_server=known_dhcp_server, duration=duration)
    offers = list(result.offers)
    return DhcpWatchReport(offers=offers, rogue_offers=[o for o in offers if o.is_rogue])

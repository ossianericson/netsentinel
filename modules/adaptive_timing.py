"""
Adaptive timing — derive name-resolution timeouts from measured gateway RTT.

Every timeout in the name-resolution path (rDNS, NetBIOS, mDNS) was a hard-coded
constant tuned for a home LAN. Over a VPN or corporate network, tunnel latency
alone can exceed those budgets before a real answer arrives — the device is then
recorded as nameless when it actually replied. See .apm/instructions/ Part 2/L1.

Pure Python, no PyQt, no new dependencies.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from modules.utils_net import icmp_ping

# Constant floors — today's hard-coded timeouts. A home LAN's ~1ms RTT never
# clears these, so derive_profile() reproduces pre-Sprint-2 behaviour exactly.
_RDNS_FLOOR = 1.0
_NETBIOS_FLOOR = 3.0
_MDNS_FLOOR = 1.5

# Ceilings — an extreme/broken RTT measurement must not stall a single host
# indefinitely.
_RDNS_CEILING = 5.0
_NETBIOS_CEILING = 8.0
_MDNS_CEILING = 5.0

# How hard RTT scales each timeout. Chosen so a home LAN's ~1ms baseline stays
# far below every floor, while a 200-250ms VPN RTT (the range cited from the
# office walk-through) noticeably relaxes rDNS and mDNS.
_RTT_MULTIPLIER = 8.0

# Fallback baseline (ms) used when the gateway is unknown or unreachable —
# equals a home LAN's typical RTT, so the resulting profile matches today's
# constants unchanged. Safe default when a corporate firewall blocks ICMP.
_HOME_BASELINE_RTT_MS = 1.0

_GATEWAY_PING_TIMEOUT = 1.0


@dataclass
class TimingProfile:
    rtt_base_ms: float
    rdns_timeout: float      # seconds
    netbios_timeout: float   # seconds
    mdns_timeout: float      # seconds
    label: str                # plain-English summary for the status bar (RULE-A1)


def derive_profile(rtt_base_ms: float) -> TimingProfile:
    """Pure function: timeout = max(floor, rtt_base_ms/1000 * K), capped at a ceiling."""
    scaled = max(rtt_base_ms, 0.0) / 1000.0 * _RTT_MULTIPLIER

    rdns_timeout = min(max(_RDNS_FLOOR, scaled), _RDNS_CEILING)
    netbios_timeout = min(max(_NETBIOS_FLOOR, scaled), _NETBIOS_CEILING)
    mdns_timeout = min(max(_MDNS_FLOOR, scaled), _MDNS_CEILING)

    relaxed = (
        rdns_timeout > _RDNS_FLOOR
        or netbios_timeout > _NETBIOS_FLOOR
        or mdns_timeout > _MDNS_FLOOR
    )
    if relaxed:
        label = f"Timing: relaxed (gateway RTT {rtt_base_ms:.0f} ms)"
    else:
        label = f"Timing: normal (gateway RTT {rtt_base_ms:.0f} ms)"

    return TimingProfile(
        rtt_base_ms=rtt_base_ms,
        rdns_timeout=rdns_timeout,
        netbios_timeout=netbios_timeout,
        mdns_timeout=mdns_timeout,
        label=label,
    )


def measure_gateway_rtt(gateway_ip: str | None, samples: int = 3, ping_fn=icmp_ping) -> float:
    """
    Ping the gateway up to *samples* times and return the median RTT (ms) of the
    successful samples. Falls back to a home-equivalent baseline — reproducing
    today's constants unchanged — when there's no gateway to probe or every
    sample fails (e.g. a corporate firewall blocking ICMP).

    *ping_fn* is injectable so tests never touch the real network; production
    callers use the default modules.utils_net.icmp_ping.
    """
    if not gateway_ip:
        return _HOME_BASELINE_RTT_MS

    successes = []
    for _ in range(samples):
        rtt = ping_fn(gateway_ip, timeout=_GATEWAY_PING_TIMEOUT)
        if rtt is not None and rtt >= 0:
            successes.append(rtt)

    if not successes:
        return _HOME_BASELINE_RTT_MS
    return statistics.median(successes)

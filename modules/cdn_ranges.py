"""
modules/cdn_ranges.py — Static CDN/streaming-provider IP range classifier.

Identifies which well-known streaming or content-delivery network a
destination IP belongs to, using publicly documented IP prefix blocks.
No external lookups — pure stdlib `ipaddress`, safe to call from a packet
capture hot path (modules/app_traffic_classifier.py).

This is intentionally coarse: it covers the largest, most stable prefix
blocks for a handful of well-known consumer services (S6-2). It is not
a substitute for a full IP-to-ASN database and will return None for any
address it does not recognise — callers should treat that as "Other"/
"Unknown CDN", never as an error.
"""
from __future__ import annotations

import ipaddress
from typing import Dict, List, Optional, Tuple, Union

# (CIDR, provider name) — ordered roughly by traffic volume.
# Sources: provider-published ASN/IP range documentation.
_CDN_PREFIXES: List[Tuple[str, str]] = [
    # Netflix (Open Connect)
    ("45.57.0.0/17", "Netflix"),
    ("23.246.0.0/18", "Netflix"),
    ("198.38.96.0/19", "Netflix"),
    ("198.45.48.0/20", "Netflix"),
    ("37.77.184.0/21", "Netflix"),
    # Google / YouTube
    ("142.250.0.0/15", "YouTube"),
    ("172.217.0.0/16", "YouTube"),
    ("74.125.0.0/16", "YouTube"),
    ("216.58.192.0/19", "YouTube"),
    # Amazon / Twitch / Prime Video (AWS CloudFront ranges overlap; this is
    # a coarse heuristic, not an authoritative AWS IP-range import)
    ("23.160.0.0/16", "Twitch"),
    ("185.42.204.0/22", "Twitch"),
    ("199.9.248.0/21", "Twitch"),
    # Disney+ / Hulu (BAMTech / Akamai-fronted, partial ranges)
    ("23.0.0.0/12", "Disney+"),
]

_IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

_NETWORKS: List[Tuple[_IPNetwork, str]] = [
    (ipaddress.ip_network(cidr), name) for cidr, name in _CDN_PREFIXES
]


def classify_cdn_ip(ip: Optional[str]) -> Optional[str]:
    """Return the provider name for a destination IP, or None if unrecognised."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for network, name in _NETWORKS:
        if addr.version == network.version and addr in network:
            return name
    return None


def cdn_breakdown_label(cdn_totals: Dict[str, int]) -> str:
    """Format a {provider: bytes} dict as a short 'Netflix (62%), YouTube (38%)' string."""
    total = sum(cdn_totals.values())
    if total <= 0:
        return ""
    parts = sorted(cdn_totals.items(), key=lambda kv: -kv[1])
    pct = [(name, b / total * 100) for name, b in parts]
    return ", ".join(f"{name} ({p:.0f}%)" for name, p in pct[:4])

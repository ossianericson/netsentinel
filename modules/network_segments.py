"""
network_segments.py — Network segment/zone grouping for device inventory.

Identifies distinct /24 subnets from a device scan and classifies each
device into the tightest CIDR match. Segment records are persisted in
the network_segments table (MetricStore schema v11).

Architecture rules observed:
  • Pure Python — no PyQt imports.
  • No direct DB writes — callers use MetricStore.upsert_segment().
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional

# ── Segment colour palette (assigned round-robin to auto-detected subnets) ────
SEGMENT_PALETTE: list[str] = [
    "#0078D4",  # blue
    "#2E7D32",  # green
    "#D93025",  # red
    "#F59E0B",  # amber
    "#6B21A8",  # purple
    "#0E7490",  # teal
    "#C2410C",  # orange
    "#1D4ED8",  # indigo
]


@dataclass
class NetworkSegment:
    """One network zone / VLAN segment."""

    id: int               # DB primary key; 0 if not yet persisted
    name: str             # Human-readable label, e.g. "Main Network (192.168.1.x)"
    cidr: str             # CIDR notation, e.g. "192.168.1.0/24"
    color: str            # Hex colour from SEGMENT_PALETTE or user-chosen
    description: str = ""
    auto_created: int = 0  # 1 = created by auto-detection; 0 = user-defined


def auto_detect_segments(
    devices: list,
    gateway_ip: str = "",
) -> list[NetworkSegment]:
    """Return one NetworkSegment per distinct /24 subnet present in *devices*.

    Only IPv4 addresses are considered.  The returned segments have id=0 and
    auto_created=1 — callers must upsert them into MetricStore so they receive
    a real primary key.

    User-defined segments (auto_created=0) stored in MetricStore are never
    touched by this function — callers should merge the returned list against
    the stored list before upserting.
    """
    subnet_ips: dict[str, list[str]] = {}

    for d in devices:
        ip = (d.ip if not isinstance(d, dict) else d.get("ip", "")) or ""
        ip = ip.strip()
        if not ip or ip in ("?", "0.0.0.0"):
            continue
        try:
            net = ipaddress.IPv4Network(ip + "/24", strict=False)
            cidr = str(net)
            subnet_ips.setdefault(cidr, []).append(ip)
        except (ValueError, TypeError):
            pass  # non-IPv4 or invalid — skip

    segments: list[NetworkSegment] = []
    for idx, cidr in enumerate(sorted(subnet_ips)):
        name = _segment_name(cidr, gateway_ip)
        color = SEGMENT_PALETTE[idx % len(SEGMENT_PALETTE)]
        segments.append(NetworkSegment(
            id=0,
            name=name,
            cidr=cidr,
            color=color,
            auto_created=1,
        ))
    return segments


def classify_device_segment(
    ip: str,
    segments: list[NetworkSegment],
) -> Optional[NetworkSegment]:
    """Return the tightest CIDR match for *ip*, or None.

    When multiple segments match (e.g. /16 and /24), the one with the longer
    prefix length (more specific) wins.
    """
    if not ip or not segments:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None

    best: Optional[NetworkSegment] = None
    best_prefix = -1
    for seg in segments:
        try:
            net = ipaddress.ip_network(seg.cidr, strict=False)
            if addr in net:
                prefix = net.prefixlen
                if prefix > best_prefix:
                    best_prefix = prefix
                    best = seg
        except ValueError:
            pass  # non-fatal — skip malformed CIDR
    return best


def merge_segments(
    detected: list[NetworkSegment],
    stored: list[NetworkSegment],
) -> list[NetworkSegment]:
    """Merge auto-detected segments with DB-persisted ones.

    Rules:
      • User-defined segments (auto_created=0) are always kept unchanged.
      • Auto-detected segments whose CIDR already exists in *stored* are
        dropped — the stored record wins (it may have a user-edited name).
      • New CIDRs from *detected* are appended.

    Returns the combined list; callers must upsert any entry with id==0.
    """
    stored_cidrs = {s.cidr for s in stored}
    result = list(stored)
    for seg in detected:
        if seg.cidr not in stored_cidrs:
            result.append(seg)
            stored_cidrs.add(seg.cidr)
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _segment_name(cidr: str, gateway_ip: str) -> str:
    """Generate a human-readable segment name from a CIDR block."""
    try:
        net = ipaddress.IPv4Network(cidr, strict=False)
        prefix = ".".join(str(net.network_address).split(".")[:3])
    except ValueError:
        return f"Network ({cidr})"

    # If gateway is in this subnet, it's most likely the primary LAN
    if gateway_ip:
        try:
            gw = ipaddress.ip_address(gateway_ip.strip())
            if gw in net:
                return f"Main Network ({prefix}.x)"
        except ValueError:
            pass  # non-fatal — bad gateway IP

    # RFC 1918 ranges → friendly names
    if prefix.startswith("192.168."):
        return f"Local Network ({prefix}.x)"
    if prefix.startswith("10."):
        return f"Internal Network ({prefix}.x)"
    if prefix.startswith("172."):
        return f"Private Network ({prefix}.x)"

    return f"Network ({prefix}.x)"

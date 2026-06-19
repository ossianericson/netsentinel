"""
topology_layout.py — Persistent node positions for the Network Topology map.

Layout is UI-state, not metric data — stored as JSON under get_app_data_dir(),
not in MetricStore.  Each distinct network layout is keyed by a "scan signature"
derived from the sorted set of /24 subnets present in the device list.

Architecture rules:
  • Pure Python — no PyQt imports.
  • No direct DB writes — JSON file only.
  • All writes go through get_app_data_dir() (ARCH RULE 23).
"""

from __future__ import annotations

import ipaddress
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict

from modules.utils import get_app_data_dir

log = logging.getLogger(__name__)

_LAYOUT_FILE = "topology_layout.json"
_MAX_SCAN_IDS = 20  # prune oldest entries if file grows beyond this


@dataclass
class NodePosition:
    """Saved position for one topology node."""

    node_id: str    # device IP or MAC (same key used in _pos_map)
    x: float        # data coordinate — 0.0–1.0 range
    y: float        # data coordinate — 0.0–1.0 range
    pinned: bool = False


@dataclass
class TopologyEdge:
    """Live health data for one gateway ↔ device edge."""

    src_ip: str
    dst_ip: str
    latency_ms: float | None      # most recent RTT (ms); None = no data
    packet_loss: float | None     # 0.0–1.0 fraction; None = no data
    bandwidth_mbps: float | None  # interface bandwidth; None = unknown
    status: str                   # "up" | "degraded" | "down" | "unknown"


# ── I/O helpers ────────────────────────────────────────────────────────────────

def _layout_path() -> Path:
    return get_app_data_dir() / _LAYOUT_FILE


def _read_raw() -> dict:
    path = _layout_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_layout(scan_id: str) -> Dict[str, NodePosition]:
    """Return saved positions for *scan_id*, or {} when none exist.

    Only entries whose data is valid (has node_id, x, y) are returned.
    Malformed entries are silently skipped.
    """
    raw = _read_raw()
    entries: dict = raw.get(scan_id, {})
    result: Dict[str, NodePosition] = {}
    for key, val in entries.items():
        try:
            result[key] = NodePosition(
                node_id=str(val["node_id"]),
                x=float(val["x"]),
                y=float(val["y"]),
                pinned=bool(val.get("pinned", False)),
            )
        except (KeyError, TypeError, ValueError):
            pass  # non-fatal — skip corrupted entry
    return result


def save_layout(scan_id: str, positions: Dict[str, NodePosition]) -> None:
    """Persist *positions* for *scan_id* into the layout file.

    Older scan_id entries are pruned when the file exceeds _MAX_SCAN_IDS
    entries to prevent unbounded growth.
    """
    existing = _read_raw()

    # Prune oldest entries before adding the new one
    if scan_id not in existing and len(existing) >= _MAX_SCAN_IDS:
        oldest_key = next(iter(existing))
        del existing[oldest_key]

    existing[scan_id] = {k: asdict(v) for k, v in positions.items()}

    try:
        _layout_path().write_text(
            json.dumps(existing, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("topology_layout: could not save positions: %s", exc)


def clear_layout(scan_id: str) -> None:
    """Remove saved positions for *scan_id*.  No-op when absent."""
    existing = _read_raw()
    if scan_id not in existing:
        return
    del existing[scan_id]
    try:
        _layout_path().write_text(
            json.dumps(existing, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        log.warning("topology_layout: could not clear layout: %s", exc)


# ── Scan-ID computation ─────────────────────────────────────────────────────────

def compute_scan_id(devices: list) -> str:
    """Derive a stable string signature from the /24 subnets in *devices*.

    The same set of subnets always produces the same key, regardless of
    device order or host counts.  Falls back to "default" when no valid
    IPv4 addresses are found.
    """
    subnets: set[str] = set()
    for d in devices:
        ip = (
            d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
        ) or ""
        ip = ip.strip()
        if not ip or ip in ("?", "0.0.0.0"):
            continue
        try:
            net = ipaddress.IPv4Network(ip + "/24", strict=False)
            subnets.add(str(net))
        except (ValueError, TypeError):
            pass  # non-fatal — non-IPv4 or malformed
    return "_".join(sorted(subnets)) or "default"

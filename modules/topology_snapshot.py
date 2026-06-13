"""
topology_snapshot.py — Point-in-time topology capture and change detection.

Stores a compact snapshot of the current network topology (device IPs, MACs,
and gateway→device edges) in MetricStore after each scan.  The diff between
the current and previous snapshot drives the "Show Changes" overlay on the
Network Map.

Architecture:
  • Pure Python — no PyQt imports.
  • MetricStore access via _execute_write / _execute_read (no direct SQL).
  • Keeps only the last 10 snapshots per store (pruned on every save).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

log = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TopologySnapshot:
    """Serialisable point-in-time topology state captured after a scan."""

    timestamp: datetime
    device_ips: frozenset
    device_macs: frozenset
    edges: list  # list[tuple[str, str]] — (src_ip, dst_ip)


@dataclass
class TopologyDiff:
    """What changed in topology between two consecutive scans."""

    added_ips: List[str]   = field(default_factory=list)
    removed_ips: List[str] = field(default_factory=list)
    added_edges: list      = field(default_factory=list)  # list[tuple[str, str]]
    removed_edges: list    = field(default_factory=list)  # list[tuple[str, str]]

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_ips or self.removed_ips
            or self.added_edges or self.removed_edges
        )

    @property
    def summary(self) -> str:
        """Human-readable one-liner: "3 new · 1 gone", or empty string."""
        parts: list = []
        if self.added_ips:
            parts.append(f"{len(self.added_ips)} new")
        if self.removed_ips:
            parts.append(f"{len(self.removed_ips)} gone")
        return "  ·  ".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────

def build_snapshot(
    devices: List[Any],
    gateway_ip: str | None = None,
) -> TopologySnapshot:
    """Construct a TopologySnapshot from a scan device list."""
    ips: set = set()
    macs: set = set()
    for d in devices:
        ip  = d.get("ip",  "") if isinstance(d, dict) else getattr(d, "ip",  "")
        mac = d.get("mac", "") if isinstance(d, dict) else getattr(d, "mac", "")
        if ip and ip not in ("?", "0.0.0.0", "255.255.255.255"):
            ips.add(ip)
        if mac:
            macs.add(mac.lower())

    edges: list = []
    if gateway_ip:
        for ip in sorted(ips):
            if ip != gateway_ip:
                edges.append((gateway_ip, ip))

    return TopologySnapshot(
        timestamp=datetime.now(),
        device_ips=frozenset(ips),
        device_macs=frozenset(macs),
        edges=edges,
    )


def save_snapshot(snapshot: TopologySnapshot, store: "MetricStore") -> None:
    """Persist *snapshot* to the topology_snapshots table in *store*."""
    data = {
        "device_ips":  sorted(snapshot.device_ips),
        "device_macs": sorted(snapshot.device_macs),
        "edges": [list(e) for e in snapshot.edges],
    }
    try:
        store._execute_write(
            "INSERT INTO topology_snapshots (ts, data_json) VALUES (?, ?)",
            (int(snapshot.timestamp.timestamp()), json.dumps(data)),
        )
        # Prune: keep only the 10 most recent rows
        store._execute_write(
            "DELETE FROM topology_snapshots WHERE id NOT IN "
            "(SELECT id FROM topology_snapshots ORDER BY ts DESC LIMIT 10)",
            (),
        )
    except Exception:
        log.debug("topology_snapshot.save_snapshot failed", exc_info=True)


def load_last_snapshot(store: "MetricStore") -> TopologySnapshot | None:
    """Return the most recent snapshot from *store*, or None if none exists."""
    try:
        rows = store._execute_read(
            "SELECT ts, data_json FROM topology_snapshots ORDER BY ts DESC LIMIT 1",
        )
    except Exception:
        return None
    if not rows:
        return None
    ts_int, data_json = rows[0]
    try:
        data = json.loads(data_json)
        return TopologySnapshot(
            timestamp=datetime.fromtimestamp(ts_int),
            device_ips=frozenset(data.get("device_ips", [])),
            device_macs=frozenset(data.get("device_macs", [])),
            edges=[tuple(e) for e in data.get("edges", [])],
        )
    except Exception:
        log.debug("topology_snapshot.load_last_snapshot parse failed", exc_info=True)
        return None


def diff_snapshots(
    current: TopologySnapshot,
    previous: TopologySnapshot,
) -> TopologyDiff:
    """Return what changed between *previous* and *current* snapshots."""
    added_ips   = sorted(current.device_ips  - previous.device_ips)
    removed_ips = sorted(previous.device_ips - current.device_ips)

    cur_edges  = {tuple(e) for e in current.edges}
    prev_edges = {tuple(e) for e in previous.edges}
    added_edges   = sorted(cur_edges  - prev_edges)
    removed_edges = sorted(prev_edges - cur_edges)

    return TopologyDiff(
        added_ips=list(added_ips),
        removed_ips=list(removed_ips),
        added_edges=list(added_edges),
        removed_edges=list(removed_edges),
    )

"""
port_sweep — nightly port-scan sweep of known inventory devices (V6 Sprint 3.1).

Sweeps every device already in known_device, snapshots the resulting open
ports via modules.config_baseline (label="posture_port_sweep"), and diffs
against the last sweep with that same label to surface newly opened ports.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected at call time — never instantiated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from modules import port_scanner
from modules.config_baseline import (
    ConfigSnapshot,
    DeviceEntry,
    build_snapshot_from_scan,
    diff_snapshots,
    latest_snapshot_with_label,
    store_snapshot,
)
from modules.metric_store import MetricStore

SWEEP_LABEL = "posture_port_sweep"


@dataclass
class PortSweepReport:
    """Result of one nightly port sweep run."""
    new_ports: List[Tuple[str, int]] = field(default_factory=list)   # (ip, port)
    all_devices: List[DeviceEntry] = field(default_factory=list)
    snapshot: Optional[ConfigSnapshot] = None


def run_nightly_port_sweep(store: MetricStore) -> PortSweepReport:
    """
    Port-scan every known device, store a labeled snapshot, and diff against
    the prior sweep to find newly opened ports.
    """
    devices = store.query_known_devices_summary()
    entries: List[DeviceEntry] = []
    for d in devices:
        ip = d.get("ip") or ""
        if not ip:
            continue
        result = port_scanner.scan(ip)
        entries.append(DeviceEntry(
            ip=ip,
            mac=d.get("mac", ""),
            hostname=d.get("hostname", ""),
            open_ports=[r.port for r in result.open_ports],
            vendor=d.get("vendor", ""),
            device_type=d.get("device_type", ""),
        ))

    prior = latest_snapshot_with_label(store, SWEEP_LABEL)

    new_snap = build_snapshot_from_scan([e.to_dict() for e in entries], label=SWEEP_LABEL)
    stored = store_snapshot(store, new_snap)

    if prior is None:
        return PortSweepReport(new_ports=[], all_devices=entries, snapshot=stored)

    diff = diff_snapshots(prior, stored)
    new_ports = [
        (ip, port)
        for ip, delta in diff.changed_ports.items()
        for port in delta.get("added", [])
    ]
    return PortSweepReport(new_ports=new_ports, all_devices=entries, snapshot=stored)


def port_label(port: int) -> str:
    """Friendly service name for a port number, for alert messages."""
    return port_scanner.PORT_NAMES.get(port, f"port {port}")

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
from modules.service_mapper import is_expected_port
from modules.utils_net import icmp_ping

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
        open_ports = [r.port for r in result.open_ports]
        # S2 #1: zero open ports is only meaningful if the device actually
        # answered. A device asleep or Wi-Fi power-saving during this sweep
        # also scans to zero open ports -- indistinguishable from "genuinely
        # nothing open" without an independent liveness check, which is
        # exactly the gap that made the *next* successful sweep report every
        # port as newly opened.
        not_testable = not open_ports and icmp_ping(ip) < 0
        entries.append(DeviceEntry(
            ip=ip,
            mac=d.get("mac", ""),
            hostname=d.get("hostname", ""),
            open_ports=open_ports,
            vendor=d.get("vendor", ""),
            device_type=d.get("device_type", ""),
            not_testable=not_testable,
        ))

    prior = latest_snapshot_with_label(store, SWEEP_LABEL)

    new_snap = build_snapshot_from_scan([e.to_dict() for e in entries], label=SWEEP_LABEL)
    stored = store_snapshot(store, new_snap)

    if prior is None:
        return PortSweepReport(new_ports=[], all_devices=entries, snapshot=stored)

    diff = diff_snapshots(prior, stored)
    device_type_by_ip = {e.ip: e.device_type for e in entries}
    new_ports = [
        (ip, port)
        for ip, delta in diff.changed_ports.items()
        for port in delta.get("added", [])
        # S2 #3: a port that's normal, expected behaviour for this device's
        # type (UPnP SSDP on a streaming stick, 8443 on a Chromecast, an
        # HTTP admin UI on a Smart TV) is how the device works, not a
        # security-relevant change worth alerting on.
        if not is_expected_port(device_type_by_ip.get(ip, ""), port)
    ]
    return PortSweepReport(new_ports=new_ports, all_devices=entries, snapshot=stored)


def port_label(port: int) -> str:
    """Friendly service name for a port number, for alert messages."""
    return port_scanner.PORT_NAMES.get(port, f"port {port}")

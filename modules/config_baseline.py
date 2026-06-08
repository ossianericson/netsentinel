"""
config_baseline — configuration snapshot and diff engine.

Takes point-in-time snapshots of the network device inventory (IP, MAC,
hostname, open ports) and SNMP polling results, stores them in MetricStore,
and computes structured diffs between any two snapshots.

Architecture rules:
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected at call time — never instantiated here.
  • No blocking I/O other than the MetricStore write (which is already
    serialised internally via a threading.Lock).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.metric_store import MetricStore


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class DeviceEntry:
    """Represents one device in a snapshot."""
    ip:         str
    mac:        str              = ""
    hostname:   str              = ""
    open_ports: List[int]        = field(default_factory=list)
    vendor:     str              = ""
    device_type: str             = ""

    def to_dict(self) -> dict:
        return {
            "ip":          self.ip,
            "mac":         self.mac,
            "hostname":    self.hostname,
            "open_ports":  sorted(self.open_ports),
            "vendor":      self.vendor,
            "device_type": self.device_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DeviceEntry":
        return cls(
            ip=d.get("ip", ""),
            mac=d.get("mac", ""),
            hostname=d.get("hostname", ""),
            open_ports=d.get("open_ports", []),
            vendor=d.get("vendor", ""),
            device_type=d.get("device_type", ""),
        )


@dataclass
class ConfigSnapshot:
    """In-memory snapshot. Persisted in MetricStore as JSON."""
    id:          int                    # MetricStore row id (0 before stored)
    ts:          int                    # Unix timestamp
    label:       str                    # user-defined description
    devices:     List[DeviceEntry]      = field(default_factory=list)
    snmp_data:   Dict[str, dict]        = field(default_factory=dict)
    # ip → {oid_name: value}

    def to_json(self) -> str:
        return json.dumps({
            "devices":   [d.to_dict() for d in self.devices],
            "snmp_data": self.snmp_data,
        })

    @classmethod
    def from_row(cls, row: dict) -> "ConfigSnapshot":
        data = json.loads(row.get("data_json") or "{}")
        return cls(
            id=row["id"],
            ts=row["ts"],
            label=row.get("label", ""),
            devices=[DeviceEntry.from_dict(d) for d in data.get("devices", [])],
            snmp_data=data.get("snmp_data", {}),
        )


@dataclass
class SnapshotDiff:
    """
    Structured diff between two snapshots.

    Fields
    ------
    added_devices:   IPs present in *new* but not in *old*.
    removed_devices: IPs present in *old* but not in *new*.
    changed_ports:   ip → {"added": [ports], "removed": [ports]}
    changed_snmp:    ip → {oid_name: {"old": v1, "new": v2}}
    changed_fields:  ip → {field_name: {"old": v1, "new": v2}}
                     e.g. hostname, mac, vendor
    """
    old_id:           int
    new_id:           int
    added_devices:    List[str]          = field(default_factory=list)
    removed_devices:  List[str]          = field(default_factory=list)
    changed_ports:    Dict[str, dict]    = field(default_factory=dict)
    changed_snmp:     Dict[str, dict]    = field(default_factory=dict)
    changed_fields:   Dict[str, dict]    = field(default_factory=dict)

    @property
    def has_drift(self) -> bool:
        return bool(
            self.added_devices or self.removed_devices or
            self.changed_ports or self.changed_snmp or self.changed_fields
        )

    def summary(self) -> str:
        """One-line plain-English summary."""
        parts = []
        if self.added_devices:
            parts.append(f"{len(self.added_devices)} device(s) added")
        if self.removed_devices:
            parts.append(f"{len(self.removed_devices)} device(s) removed")
        if self.changed_ports:
            parts.append(f"{len(self.changed_ports)} device(s) with port changes")
        if self.changed_snmp:
            parts.append(f"{len(self.changed_snmp)} device(s) with SNMP changes")
        if self.changed_fields:
            parts.append(f"{len(self.changed_fields)} device(s) with attribute changes")
        return ", ".join(parts) if parts else "No drift detected"


# ── Core functions ────────────────────────────────────────────────────────────

def build_snapshot_from_scan(
    devices: List[dict],
    snmp_results: Optional[Dict[str, dict]] = None,
    label: str = "",
) -> ConfigSnapshot:
    """
    Build a ConfigSnapshot from raw scan / port-scanner results.

    Parameters
    ----------
    devices : list of device dicts from combined_discovery / port_scanner.
        Expected keys per device: ip, mac, hostname, ports (list of int),
        vendor, device_type.  Missing keys are defaulted to empty.
    snmp_results : ip → {oid_name: value} dict from snmp_poller.  Optional.
    label : human-readable label for the snapshot.

    Returns
    -------
    ConfigSnapshot with id=0 (not yet stored). Call store_snapshot() to persist.
    """
    entries = []
    for d in devices:
        # Accept both 'ports' and 'open_ports' key names for flexibility
        ports = d.get("open_ports") or d.get("ports") or []
        if isinstance(ports, dict):
            # port_scanner sometimes returns {port: {"state": ...}} dicts
            ports = [int(p) for p in ports.keys()]
        entries.append(DeviceEntry(
            ip=d.get("ip", ""),
            mac=d.get("mac", ""),
            hostname=d.get("hostname", ""),
            open_ports=sorted(int(p) for p in ports if str(p).isdigit() or isinstance(p, int)),
            vendor=d.get("vendor", ""),
            device_type=d.get("device_type", ""),
        ))

    return ConfigSnapshot(
        id=0,
        ts=int(time.time()),
        label=label,
        devices=entries,
        snmp_data=snmp_results or {},
    )


def store_snapshot(store: MetricStore, snapshot: ConfigSnapshot) -> ConfigSnapshot:
    """
    Persist a ConfigSnapshot to MetricStore and return it with the assigned id.
    """
    row_id = store.store_snapshot(
        ts=snapshot.ts,
        label=snapshot.label,
        data_json=snapshot.to_json(),
    )
    snapshot.id = row_id
    return snapshot


def load_snapshot(store: MetricStore, snapshot_id: int) -> Optional[ConfigSnapshot]:
    """Load a single snapshot from MetricStore by id."""
    row = store.load_snapshot(snapshot_id)
    if row is None:
        return None
    return ConfigSnapshot.from_row(row)


def list_snapshots(store: MetricStore, limit: int = 100) -> List[ConfigSnapshot]:
    """Return up to `limit` most recent snapshots (newest first)."""
    rows = store.list_snapshots(limit=limit)
    return [ConfigSnapshot.from_row(r) for r in rows]


def delete_snapshot(store: MetricStore, snapshot_id: int) -> None:
    """Delete a snapshot from MetricStore."""
    store.delete_snapshot(snapshot_id)


def diff_snapshots(old: ConfigSnapshot, new: ConfigSnapshot) -> SnapshotDiff:
    """
    Compute a SnapshotDiff between two ConfigSnapshot objects.

    Compares devices by IP address, then compares ports and SNMP values.
    Field changes (hostname, MAC, vendor) are also tracked.
    """
    diff = SnapshotDiff(old_id=old.id, new_id=new.id)

    old_by_ip: Dict[str, DeviceEntry] = {d.ip: d for d in old.devices}
    new_by_ip: Dict[str, DeviceEntry] = {d.ip: d for d in new.devices}

    old_ips = set(old_by_ip)
    new_ips = set(new_by_ip)

    diff.added_devices   = sorted(new_ips - old_ips)
    diff.removed_devices = sorted(old_ips - new_ips)

    for ip in old_ips & new_ips:
        od = old_by_ip[ip]
        nd = new_by_ip[ip]

        # Port diff
        old_ports = set(od.open_ports)
        new_ports = set(nd.open_ports)
        added_ports   = sorted(new_ports - old_ports)
        removed_ports = sorted(old_ports - new_ports)
        if added_ports or removed_ports:
            diff.changed_ports[ip] = {"added": added_ports, "removed": removed_ports}

        # Field diff (hostname, mac, vendor, device_type)
        field_diff = {}
        for attr in ("mac", "hostname", "vendor", "device_type"):
            ov = getattr(od, attr, "")
            nv = getattr(nd, attr, "")
            if ov != nv and (ov or nv):  # ignore blank→blank
                field_diff[attr] = {"old": ov, "new": nv}
        if field_diff:
            diff.changed_fields[ip] = field_diff

    # SNMP diff — compare per-IP OID values
    old_snmp = old.snmp_data or {}
    new_snmp = new.snmp_data or {}
    all_snmp_ips = set(old_snmp) | set(new_snmp)
    for ip in all_snmp_ips:
        od_snmp = old_snmp.get(ip, {})
        nd_snmp = new_snmp.get(ip, {})
        oid_diff = {}
        for k in set(od_snmp) | set(nd_snmp):
            ov = od_snmp.get(k)
            nv = nd_snmp.get(k)
            if ov != nv:
                oid_diff[k] = {"old": ov, "new": nv}
        if oid_diff:
            diff.changed_snmp[ip] = oid_diff

    return diff

"""
DeviceTracker — new/disappeared device detection backed by MetricStore (T1#3).

Compares each scan result against the known-device inventory stored in
MetricStore.known_devices. Emits JOINED events for new MACs and LEFT events
for devices that have been absent for longer than `gone_threshold_s`.

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports.
  • MetricStore injected as constructor parameter.
  • All DB access through MetricStore public API.
"""

from __future__ import annotations

import datetime
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.device_stability import update_stability_for_device as _update_stability
from modules.metric_store import MetricStore
from modules.service_mapper import get_services as _get_services


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class TrackedDevice:
    """Normalised device record extracted from a scan result dict."""
    mac:         str
    ip:          str
    hostname:    str
    vendor:      str
    device_type: str


@dataclass
class TrackerResult:
    """Returned by DeviceTracker.process_scan() after each scan."""
    new_devices:     List[TrackedDevice] = field(default_factory=list)
    gone_devices:    List[TrackedDevice] = field(default_factory=list)
    total_known:     int = 0
    scan_ts:         int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

_VENDOR_UNKNOWN = frozenset({"unknown", "unknown vendor", "unknown device"})


def _normalise(d) -> Optional[TrackedDevice]:
    """Convert a scan device (dict or object) to a TrackedDevice, or None if no MAC."""
    if isinstance(d, dict):
        mac = d.get("mac", "")
        ip  = d.get("ip", "") or ""
        hn  = d.get("hostname", "") or ""
        vnd = d.get("vendor", "") or ""
        dt  = d.get("device_type", "") or d.get("connection_type", "") or ""
    else:
        mac = getattr(d, "mac", "") or ""
        ip  = getattr(d, "ip",  "") or ""
        hn  = getattr(d, "hostname", "") or ""
        vnd = getattr(d, "vendor",  "") or ""
        dt  = getattr(d, "device_type", "") or getattr(d, "connection_type", "") or ""
    mac = mac.lower().strip()
    if not mac or mac in ("?", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
        return None
    # Treat placeholder strings as "no info" so upsert_known_device receives vendor=None.
    # COALESCE(NULL, existing) preserves a previously resolved vendor; COALESCE("Unknown",
    # existing) = "Unknown" — clobbering it.  The same logic applies to device_type.
    if vnd.lower() in _VENDOR_UNKNOWN:
        vnd = ""
    if dt.lower() in ("unknown device", "unknown"):
        dt = ""
    return TrackedDevice(mac=mac, ip=ip, hostname=hn, vendor=vnd, device_type=dt)


# ── Main class ────────────────────────────────────────────────────────────────

class DeviceTracker:
    """
    Stateful tracker that compares scan results against MetricStore inventory.

    Parameters
    ----------
    store : MetricStore
        Injected MetricStore singleton.
    gone_threshold_s : int
        Seconds since last_seen before a device is considered "gone" and a LEFT
        event is written. Default: 3600 (1 hour). Set to 0 to disable LEFT events.
    """

    def __init__(
        self,
        store: MetricStore,
        gone_threshold_s: int = 3600,
    ):
        self._store             = store
        self._gone_threshold_s  = gone_threshold_s

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_scan(self, devices) -> TrackerResult:
        """
        Diff `devices` (list of scan dicts or objects) against MetricStore.

        Side effects:
          • Upserts every valid device into known_devices.
          • Writes a JOINED event for devices not previously seen.
          • Writes a LEFT event for known devices absent longer than gone_threshold_s.

        Returns a TrackerResult describing what changed.
        """
        now     = int(time.time())
        result  = TrackerResult(scan_ts=now)
        known   = self._store.get_known_devices()           # dict: mac → KnownDevice
        seen_macs: set[str] = set()

        for raw in devices:
            td = _normalise(raw)
            if td is None:
                continue
            seen_macs.add(td.mac)
            is_new = td.mac not in known

            services_json: Optional[str] = None
            if td.device_type and td.device_type != "Unknown Device":
                svc_list = _get_services(
                    device_type=td.device_type or "",
                    vendor=td.vendor or "",
                    hostname=td.hostname or "",
                )
                if svc_list:
                    services_json = json.dumps([s.name for s in svc_list])

            self._store.upsert_known_device(
                mac=td.mac,
                ip=td.ip or None,
                hostname=td.hostname or None,
                vendor=td.vendor or None,
                device_type=td.device_type or None,
                is_authorized=None,   # do not override existing flag
                ts=now,
                services=services_json,
            )

            # Record this IP observation in device_ip_history (feeds stability scoring)
            if td.ip:
                try:
                    record_ip_observation(td.mac, td.ip, self._store)
                except Exception:
                    pass  # non-fatal — history table may not exist on first run

            if is_new:
                self._store.record_device_event(
                    ip=td.ip or td.mac,
                    event_type="JOINED",
                    mac=td.mac,
                    detail=f"New device: {td.vendor or 'Unknown'} / {td.device_type or '—'}",
                    ts=now,
                )
                try:
                    record_event(
                        mac=td.mac,
                        event_type="first_seen",
                        old_value="",
                        new_value=td.ip or "",
                        source="scan",
                        store=self._store,
                    )
                except Exception:
                    pass  # non-fatal — audit table may not exist on schema upgrade
                result.new_devices.append(td)

        # ── Stability scoring ─────────────────────────────────────────────────
        # Recompute ip_stability, scan_count, and inferred_role for every device
        # seen in this scan.  Done after the upsert loop so ip_history is up to date.
        # Build mac→td map once to avoid O(n²) re-normalisation.
        _seen_td: Dict[str, TrackedDevice] = {}
        for raw in devices:
            _td = _normalise(raw)
            if _td is not None:
                _seen_td[_td.mac] = _td

        # One DB read for all custom_names (avoid N queries inside the loop)
        _fresh_known = self._store.get_known_devices()

        for mac, td_ref in _seen_td.items():
            _kd = _fresh_known.get(mac)
            _custom = _kd.custom_name if _kd else None
            try:
                _update_stability(
                    mac=mac,
                    ip=td_ref.ip or None,
                    device_type=td_ref.device_type or None,
                    custom_name=_custom,
                    store=self._store,
                )
            except Exception:
                pass  # non-fatal — stability columns may not exist on old schema

        # ── Gone detection ────────────────────────────────────────────────────
        if self._gone_threshold_s > 0:
            for mac, kd in known.items():
                if mac in seen_macs:
                    continue
                last_seen = kd.last_seen or 0
                if now - last_seen >= self._gone_threshold_s:
                    # Only emit LEFT once — suppress if we already emitted it
                    # (detect by checking if the most recent event for this MAC
                    #  within the threshold window is already LEFT)
                    recent_events = self._store.query_device_events(
                        hours=int(self._gone_threshold_s / 3600) + 1,
                        ip=kd.ip or mac,
                        event_types=["LEFT"],
                    )
                    already_emitted = any(
                        e.mac == mac and (now - e.ts) < self._gone_threshold_s
                        for e in recent_events
                    )
                    if not already_emitted:
                        self._store.record_device_event(
                            ip=kd.ip or mac,
                            event_type="LEFT",
                            mac=mac,
                            detail=(
                                f"Not seen for ≥{self._gone_threshold_s // 60} min: "
                                f"{kd.vendor or 'Unknown'}"
                            ),
                            ts=now,
                        )
                        result.gone_devices.append(TrackedDevice(
                            mac=mac,
                            ip=kd.ip or "",
                            hostname=kd.hostname or "",
                            vendor=kd.vendor or "",
                            device_type=kd.device_type or "",
                        ))

        result.total_known = len(self._store.get_known_devices())
        return result


# ── Module-level annotation / IP-history helpers (Sprint 2) ──────────────────

def _utcnow() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def record_ip_observation(mac: str, ip: str, store: "MetricStore") -> None:
    """Upsert mac+ip combo into device_ip_history."""
    if not mac or not ip:
        return
    now = _utcnow()
    store._execute_write(
        """
        INSERT INTO device_ip_history (mac, ip, first_seen, last_seen, seen_count)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(mac, ip) DO UPDATE SET
            last_seen  = excluded.last_seen,
            seen_count = seen_count + 1
        """,
        (mac.lower(), ip, now, now),
    )


def get_ip_history(mac: str, store: "MetricStore") -> List[Dict]:
    """Return [{ip, first_seen, last_seen, seen_count}] sorted by last_seen desc."""
    rows = store._execute_read(
        """
        SELECT ip, first_seen, last_seen, seen_count
        FROM device_ip_history
        WHERE mac = ?
        ORDER BY last_seen DESC
        """,
        (mac.lower(),),
    )
    return [
        {"ip": r[0], "first_seen": r[1], "last_seen": r[2], "seen_count": r[3]}
        for r in rows
    ]


def save_annotations(mac: str, store: "MetricStore", **kwargs) -> None:
    """Upsert user_label/location/owner/notes/asset_tag for a MAC."""
    now = _utcnow()
    store._execute_write(
        """
        INSERT INTO device_annotations (mac, user_label, location, owner, notes, asset_tag, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mac) DO UPDATE SET
            user_label = excluded.user_label,
            location   = excluded.location,
            owner      = excluded.owner,
            notes      = excluded.notes,
            asset_tag  = excluded.asset_tag,
            updated_at = excluded.updated_at
        """,
        (
            mac.lower(),
            kwargs.get("user_label", ""),
            kwargs.get("location", ""),
            kwargs.get("owner", ""),
            kwargs.get("notes", ""),
            kwargs.get("asset_tag", ""),
            now,
        ),
    )


def get_annotations(mac: str, store: "MetricStore") -> Dict:
    """Return annotation dict for a MAC; empty dict if not found."""
    rows = store._execute_read(
        "SELECT user_label, location, owner, notes, asset_tag, updated_at "
        "FROM device_annotations WHERE mac = ?",
        (mac.lower(),),
    )
    if not rows:
        return {}
    r = rows[0]
    return {
        "user_label": r[0] or "",
        "location":   r[1] or "",
        "owner":      r[2] or "",
        "notes":      r[3] or "",
        "asset_tag":  r[4] or "",
        "updated_at": r[5] or "",
    }


def record_event(
    mac: str,
    event_type: str,
    old_value: str,
    new_value: str,
    source: str,
    store: "MetricStore",
) -> None:
    """Write a row to the device_events audit table."""
    if not mac:
        return
    now = _utcnow()
    store._execute_write(
        """
        INSERT INTO device_events (mac, event_type, old_value, new_value, source, ts)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (mac.lower(), event_type, old_value or "", new_value or "", source or "", now),
    )


def get_device_events(
    mac: str,
    store: "MetricStore",
    limit: int = 50,
) -> List[Dict]:
    """Return [{event_type, old_value, new_value, source, ts}] newest-first."""
    rows = store._execute_read(
        """
        SELECT event_type, old_value, new_value, source, ts
        FROM device_events
        WHERE mac = ?
        ORDER BY ts DESC
        LIMIT ?
        """,
        (mac.lower(), limit),
    )
    return [
        {
            "event_type": r[0],
            "old_value":  r[1] or "",
            "new_value":  r[2] or "",
            "source":     r[3] or "",
            "ts":         r[4],
        }
        for r in rows
    ]


def get_all_device_events(
    store: "MetricStore",
    limit: int = 500,
    hours: int = 168,
) -> List[Dict]:
    """Return recent device change events across all MACs, newest-first."""
    rows = store._execute_read(
        """
        SELECT mac, event_type, old_value, new_value, source, ts
        FROM device_events
        WHERE ts >= datetime('now', ? || ' hours')
        ORDER BY ts DESC
        LIMIT ?
        """,
        (f"-{hours}", limit),
    )
    return [
        {
            "mac":        r[0],
            "event_type": r[1],
            "old_value":  r[2] or "",
            "new_value":  r[3] or "",
            "source":     r[4] or "",
            "ts":         r[5],
        }
        for r in rows
    ]


def get_all_annotations(store: "MetricStore") -> Dict[str, Dict]:
    """Return {mac: annotation_dict} for all annotated devices."""
    rows = store._execute_read(
        "SELECT mac, user_label, location, owner, notes, asset_tag, updated_at "
        "FROM device_annotations",
        (),
    )
    result: Dict[str, Dict] = {}
    for r in rows:
        result[r[0]] = {
            "user_label": r[1] or "",
            "location":   r[2] or "",
            "owner":      r[3] or "",
            "notes":      r[4] or "",
            "asset_tag":  r[5] or "",
            "updated_at": r[6] or "",
        }
    return result

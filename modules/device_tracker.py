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

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from modules.device_stability import update_stability_for_device as _update_stability
from modules.metric_store import KnownDevice, MetricStore
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

    def process_scan(
        self,
        devices,
        known: Optional[Dict[str, KnownDevice]] = None,
    ) -> TrackerResult:
        """
        Diff `devices` (list of scan dicts or objects) against MetricStore.

        Side effects:
          • Upserts every valid device into known_devices.
          • Writes a JOINED event for devices not previously seen.
          • Writes a LEFT event for known devices absent longer than gone_threshold_s.

        Returns a TrackerResult describing what changed.

        `known` (Phase B2 / F4): an optional pre-fetched get_known_devices()
        snapshot. When the caller (ui/scan_wiring.py) already read known_device
        earlier in the same scan-result handler, passing it here avoids a
        second full-table SELECT — safe because nothing below writes to
        custom_name, and the final row set is fully derivable from this
        snapshot plus the MACs upserted in this call (see known_macs below).
        Defaults to a fresh read when omitted, matching the pre-B2 behaviour.

        Single-writer invariant (Phase 3c): this is the ONLY place scan-driven
        known_device.last_seen / scan_count / ip_stability / inferred_role are
        written. Callers must never call record_ip_observation() or update
        those columns directly for scan results — route through process_scan()
        instead (see MetricStore module docstring for the full invariant).
        A prior bug had ui/scan_wiring.py call record_ip_observation() directly
        in addition to this method for the same scan, doubling seen_count.
        """
        now     = int(time.time())
        result  = TrackerResult(scan_ts=now)
        known   = known if known is not None else self._store.get_known_devices()  # dict: mac → KnownDevice
        # Mirrors known_device's mac set through this scan's upserts so total_known
        # (below) never needs a second live read of the table.
        known_macs: set[str] = set(known)
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
            known_macs.add(td.mac)

            # Record this IP observation in device_ip_history (feeds stability scoring).
            # Uses the same `now` as upsert_known_device() above so
            # known_device.last_seen == MAX(device_ip_history.last_seen) holds exactly.
            if td.ip:
                try:
                    self._store.record_ip_observation(td.mac, td.ip, ts=now)
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

        # custom_name lookup reuses `known` rather than re-querying: upsert_known_device()
        # (above) never writes custom_name, so the pre-scan/injected snapshot is still
        # accurate for every pre-existing mac; a mac upserted for the first time this
        # scan has no custom_name yet (NULL default) — `known.get(mac)` returning None
        # resolves to the same _custom=None a fresh read would give (Phase B2 / F4).
        for mac, td_ref in _seen_td.items():
            _kd = known.get(mac)
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

        # known_macs already mirrors the final known_device row set: gone-detection
        # (above) only writes device_events, never known_device, so no third read
        # is needed (Phase B2 / F4).
        result.total_known = len(known_macs)
        return result


# ── Module-level annotation / IP-history helpers (Sprint 2) ──────────────────

def record_ip_observation(mac: str, ip: str, store: "MetricStore") -> None:
    """Upsert mac+ip combo into device_ip_history. Delegates to MetricStore's
    public API — kept as a module-level function so external callers/tests
    don't break (see MetricStore.record_ip_observation for the write)."""
    store.record_ip_observation(mac, ip)


def get_ip_history(mac: str, store: "MetricStore") -> List[Dict]:
    """Return [{ip, first_seen, last_seen, seen_count}] sorted by last_seen desc."""
    return store.get_ip_history(mac)


def save_annotations(mac: str, store: "MetricStore", **kwargs) -> None:
    """Upsert user_label/location/owner/notes/asset_tag for a MAC."""
    store.save_device_annotations(mac, **kwargs)


def get_annotations(mac: str, store: "MetricStore") -> Dict:
    """Return annotation dict for a MAC; empty dict if not found."""
    return store.get_device_annotations(mac)


def record_event(
    mac: str,
    event_type: str,
    old_value: str,
    new_value: str,
    source: str,
    store: "MetricStore",
) -> None:
    """Write a row to the device_events audit table."""
    store.record_device_change_event(mac, event_type, old_value, new_value, source)


def get_device_events(
    mac: str,
    store: "MetricStore",
    limit: int = 50,
) -> List[Dict]:
    """Return [{event_type, old_value, new_value, source, ts}] newest-first."""
    return store.get_device_change_events(mac, limit)


def get_all_device_events(
    store: "MetricStore",
    limit: int = 500,
    hours: int = 168,
) -> List[Dict]:
    """Return recent device change events across all MACs, newest-first."""
    return store.get_all_device_change_events(limit, hours)


def get_all_annotations(store: "MetricStore") -> Dict[str, Dict]:
    """Return {mac: annotation_dict} for all annotated devices."""
    return store.get_all_device_annotations()

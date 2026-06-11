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
from typing import List, Optional

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

            if is_new:
                self._store.record_device_event(
                    ip=td.ip or td.mac,
                    event_type="JOINED",
                    mac=td.mac,
                    detail=f"New device: {td.vendor or 'Unknown'} / {td.device_type or '—'}",
                    ts=now,
                )
                result.new_devices.append(td)

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

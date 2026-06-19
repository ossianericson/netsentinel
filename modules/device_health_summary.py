"""
modules/device_health_summary.py — per-device Online / Offline / Slow / Unusual
classification for the Devices page top-line summary (S5-3).

Pure function, no PyQt imports, no DB writes. Derives state from data already
present on each scanned device (display_state, risk_level) plus recent alerts
already recorded in MetricStore — no new persisted columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

STATE_ONLINE = "Online"
STATE_OFFLINE = "Offline"
STATE_SLOW = "Slow"
STATE_UNUSUAL = "Unusual"

_OFFLINE_DISPLAY_STATES = {"cached", "stale"}
_UNUSUAL_RISK_LEVELS = {"HIGH", "STORM"}
_SLOW_RISK_LEVELS = {"MEDIUM", "WARNING"}


@dataclass
class DeviceHealth:
    mac: str
    ip: str
    state: str    # one of STATE_*
    reason: str    # short plain-English reason


def _get(d, key: str, default=""):
    return d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)


def classify_device(device, alerted_hosts: Iterable[str] = ()) -> DeviceHealth:
    """Classify a single scanned device into Online/Offline/Slow/Unusual."""
    mac = (_get(device, "mac", "") or "").strip()
    ip = (_get(device, "ip", "") or "").strip()
    display_state = (_get(device, "display_state", "") or "").strip()
    risk_level = (_get(device, "risk_level", "") or "UNKNOWN").strip().upper()

    is_offline = display_state in _OFFLINE_DISPLAY_STATES
    alerted = bool(ip) and ip in set(alerted_hosts)

    if risk_level in _UNUSUAL_RISK_LEVELS or alerted:
        return DeviceHealth(mac, ip, STATE_UNUSUAL, "Recent suspicious or high-risk activity")
    if is_offline:
        return DeviceHealth(mac, ip, STATE_OFFLINE, "Not seen in the latest scan")
    if risk_level in _SLOW_RISK_LEVELS:
        return DeviceHealth(mac, ip, STATE_SLOW, "Elevated latency or packet loss")
    return DeviceHealth(mac, ip, STATE_ONLINE, "Responding normally")


def summarize_devices(devices: list, recent_alerts: Optional[List[dict]] = None) -> List[DeviceHealth]:
    """Classify every device; recent_alerts is the get_recent_alerts() output."""
    alerted_hosts = {
        (a.get("host") or "").strip()
        for a in (recent_alerts or [])
        if a.get("severity") in ("High", "Critical")
    }
    return [classify_device(d, alerted_hosts) for d in devices]


def summary_counts(results: List[DeviceHealth]) -> Dict[str, int]:
    counts = {STATE_ONLINE: 0, STATE_OFFLINE: 0, STATE_SLOW: 0, STATE_UNUSUAL: 0}
    for r in results:
        counts[r.state] = counts.get(r.state, 0) + 1
    return counts


def summary_line(results: List[DeviceHealth]) -> str:
    """Plain-English top-line summary, e.g. '3 of your 12 devices need attention'."""
    total = len(results)
    if total == 0:
        return "No devices yet — run a scan to get started"
    counts = summary_counts(results)
    needs_attention = counts[STATE_UNUSUAL] + counts[STATE_SLOW]
    if needs_attention == 0:
        return f"All {total} devices look healthy"
    return f"{needs_attention} of your {total} devices need attention"

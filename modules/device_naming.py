"""
modules/device_naming.py — smart name suggestions for newly discovered devices (S5-1).

Pure function, no PyQt imports, no DB writes. Callers persist the accepted
name via modules.device_tracker.save_annotations(mac, store, user_label=...).
"""

from __future__ import annotations

_UNHELPFUL_HOSTNAMES = {"", "?", "unknown", "localhost"}
_UNKNOWN_TYPES = {"", "unknown device", "unknown"}


def suggest_device_name(hostname: str, vendor: str, device_type: str) -> str:
    """Return the best-effort human-readable name for a newly seen device.

    Priority: real hostname > "vendor type" > vendor > type > generic fallback.
    """
    hostname = (hostname or "").strip()
    vendor = (vendor or "").strip()
    device_type = (device_type or "").strip()

    if hostname and hostname.lower() not in _UNHELPFUL_HOSTNAMES:
        return hostname
    if vendor and device_type and device_type.lower() not in _UNKNOWN_TYPES:
        return f"{vendor} {device_type}"
    if vendor:
        return vendor
    if device_type and device_type.lower() not in _UNKNOWN_TYPES:
        return device_type
    return "Unnamed Device"

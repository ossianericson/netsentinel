"""
Service Mapper — infer likely cloud/online services from device type and vendor.

Loads data/service_map.json (bundled with the app) lazily on first call.
Returns a list of ServiceInfo objects — zero to many per device.

Matching rules:
  - A service entry matches when:
      1. device_types is non-empty and device_type is in the list
         (or device_types is empty, meaning "any device type")
      2. vendor_patterns is non-empty and at least one pattern is a
         substring of the vendor string (case-insensitive)
         (or vendor_patterns is empty, meaning "any vendor")
      3. hostname_patterns is non-empty and at least one pattern is
         found as a regex in the hostname (or hostname_patterns is empty)
  - All three conditions must hold simultaneously.
  - Duplicate IDs are deduplicated — first match wins.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ServiceInfo:
    id: str
    name: str
    category: str
    icon: str = ""


_LOADED: Optional[list] = None


def _load() -> list:
    global _LOADED
    if _LOADED is not None:
        return _LOADED
    if hasattr(sys, "_MEIPASS"):
        path = Path(sys._MEIPASS) / "data" / "service_map.json"
    else:
        path = Path(__file__).parent.parent / "data" / "service_map.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _LOADED = data.get("services", [])
    except Exception:
        _LOADED = []  # graceful degradation if file missing or corrupt
    return _LOADED


def _matches(entry: dict, device_type: str, vendor: str, hostname: str) -> bool:
    match = entry.get("match", {})
    dt_lower       = device_type.lower()
    vendor_lower   = vendor.lower()
    hostname_lower = hostname.lower()

    # device_types — if non-empty, device_type must be in the list
    dtypes = [t.lower() for t in match.get("device_types", [])]
    if dtypes and dt_lower not in dtypes:
        return False

    # vendor_patterns — if non-empty, at least one must be a substring of vendor
    vpats = match.get("vendor_patterns", [])
    if vpats:
        if not any(p.lower() in vendor_lower for p in vpats):
            return False

    # hostname_patterns — if non-empty, at least one must match via regex
    hpats = match.get("hostname_patterns", [])
    if hpats:
        if not any(re.search(p, hostname_lower) for p in hpats):
            return False

    # Must have matched at least one discriminator (don't return everything
    # for a fully empty match block)
    if not dtypes and not vpats and not hpats:
        return False

    return True


def get_services(
    device_type: str = "",
    vendor: str = "",
    hostname: str = "",
    model: str = "",
) -> list[ServiceInfo]:
    """
    Return a list of ServiceInfo for online services likely used by this device.

    Parameters are all optional; providing more parameters yields more precise
    results. Returns an empty list when no services can be inferred.

    Parameters
    ----------
    device_type : Classified device type (e.g. "Games Console", "Smart TV").
    vendor      : Device vendor string (e.g. "Sony Interactive Entertainment").
    hostname    : Resolved hostname (used for service-specific disambiguation).
    model       : Model name (treated the same as hostname for pattern matching).
    """
    entries = _load()
    results: list[ServiceInfo] = []
    seen_names: set[str] = set()
    combined_hostname = f"{hostname} {model}".strip()

    for entry in entries:
        name = entry.get("name", "")
        if name in seen_names:
            continue
        if _matches(entry, device_type, vendor, combined_hostname):
            results.append(ServiceInfo(
                id=entry.get("id", ""),
                name=name,
                category=entry.get("category", ""),
                icon=entry.get("icon", ""),
            ))
            seen_names.add(name)

    return results


# ── Expected local ports per device type (S2: NEW_OPEN_PORT suppression) ──────
# Keyed by device_type (case-insensitive) -> port numbers that are normal,
# expected local-network behaviour for that class of device -- not a
# security-relevant "newly opened port" event. Distinct from
# get_services()/service_map.json (cloud services, no port data): this is
# local LAN discovery/casting/streaming-protocol ports, seen live on the
# exact device classes generating NEW_OPEN_PORT noise (Google streaming
# sticks, Chromecasts, a Samsung Smart TV).
_EXPECTED_PORTS_BY_DEVICE_TYPE: dict[str, frozenset[int]] = {
    "streaming stick": frozenset({8008, 8009, 8443, 1900, 49152}),  # Cast protocol + UPnP SSDP
    "smart tv":         frozenset({80, 8080, 8001, 8002, 9080, 1900, 8443}),
    "smart speaker":    frozenset({8008, 8009, 1900}),
    "games console":    frozenset({80, 443, 3074}),
}


def is_expected_port(device_type: str, port: int) -> bool:
    """True when *port* is normal, expected behaviour for this device_type
    (e.g. UPnP SSDP on a streaming stick, 8443 on a Chromecast, or 80/8080
    on a Smart TV's own web UI). Used to suppress NEW_OPEN_PORT noise for
    device classes that legitimately advertise these ports as part of
    normal operation."""
    return port in _EXPECTED_PORTS_BY_DEVICE_TYPE.get((device_type or "").strip().lower(), frozenset())

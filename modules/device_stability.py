"""
Device stability scoring and role inference engine.

Reads device_ip_history to compute how stable a device's IP address is over
time (ip_stability 0.0–1.0) and infers a human-readable role (gateway, printer,
server, infrastructure, workstation, iot) from behavioral patterns.

Pure Python — no PyQt imports. Called from DeviceTracker after each scan.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Role inference constants ──────────────────────────────────────────────────

_GATEWAY_OCTETS = {"1", "254"}
_INFRASTRUCTURE_TYPES = {"router", "access point", "switch", "firewall", "gateway", "wireless ap"}
_SERVER_TYPES = {"server", "nas", "storage"}
_PRINTER_TYPES = {"printer", "mfp", "scanner"}
_PRINTER_PORTS = {9100, 515, 631}
_IOT_TYPES = {"iot", "smart home", "camera", "ip camera", "smart tv", "thermostat", "hub"}
_WORKSTATION_TYPES = {"phone", "laptop", "tablet", "desktop", "pc", "computer", "workstation"}


def _type_matches(dt_lower: str, types) -> bool:
    """Word-boundary aware check — prevents 'ap' matching inside 'laptop'."""
    padded = f" {dt_lower} "
    return any(f" {t} " in padded for t in types)


# ── Public API ────────────────────────────────────────────────────────────────

def compute_ip_stability(mac: str, store: "MetricStore") -> float:
    """
    Return IP stability score (0.0–1.0) for a MAC.

    Stability = seen_count_at_canonical_ip / total_seen_count.
    Canonical IP = the IP with the highest seen_count in device_ip_history.
    Returns 0.0 for unknown MACs or when only one scan has been recorded.
    """
    rows = store.get_ip_history_stats(mac)
    if not rows:
        return 0.0
    total = sum(int(r[1] or 0) for r in rows)
    if total == 0:
        return 0.0
    canonical_count = max(int(r[1] or 0) for r in rows)
    return canonical_count / total


def infer_role(
    ip: Optional[str],
    device_type: Optional[str],
    custom_name: Optional[str],
    scan_count: int,
    ip_stability: float,
    open_ports: Optional[List[int]] = None,
) -> Optional[str]:
    """
    Infer device role from behavioral patterns. Returns role string or None.

    Priority order (first match wins):
    1. custom_name is set → None (user label takes precedence; no inference override)
    2. Last IP octet is .1 or .254 → "gateway"
    3. device_type in infrastructure set → "infrastructure"
    4. High stability + many scans + server type → "server"
    5. High stability + many scans + printer type or ports → "printer"
    6. High stability + many scans + unknown → "infrastructure" (always-on)
    7. device_type in workstation set → "workstation"
    8. device_type in IoT set → "iot"
    9. default → None
    """
    if custom_name:
        return None

    dt_lower = (device_type or "").lower()

    if ip and "." in ip:
        last_octet = ip.rsplit(".", 1)[-1]
        if last_octet in _GATEWAY_OCTETS:
            return "gateway"

    if _type_matches(dt_lower, _INFRASTRUCTURE_TYPES):
        return "infrastructure"

    if scan_count >= 5 and ip_stability >= 0.9:
        if _type_matches(dt_lower, _SERVER_TYPES):
            return "server"

    if scan_count >= 3 and ip_stability >= 0.85:
        if _type_matches(dt_lower, _PRINTER_TYPES):
            return "printer"
        if open_ports and any(p in _PRINTER_PORTS for p in open_ports):
            return "printer"

    # Always-on device with unknown type that hasn't changed IP
    if scan_count >= 10 and ip_stability >= 0.9:
        return "infrastructure"

    if _type_matches(dt_lower, _WORKSTATION_TYPES):
        return "workstation"

    if _type_matches(dt_lower, _IOT_TYPES):
        return "iot"

    return None


def is_static_candidate(
    ip_stability: float,
    scan_count: int,
    inferred_role: Optional[str],
    is_pinned: bool = False,
) -> bool:
    """
    Return True if this device should be persistently displayed even when offline.

    Static candidates are: pinned devices, infrastructure roles (gateway, printer,
    server, infrastructure), and any device seen 3+ times with stable IP.
    """
    if is_pinned:
        return True
    if inferred_role in ("gateway", "printer", "server", "infrastructure"):
        return True
    return ip_stability >= 0.85 and scan_count >= 3


def update_stability_for_device(
    mac: str,
    ip: Optional[str],
    device_type: Optional[str],
    custom_name: Optional[str],
    store: "MetricStore",
) -> None:
    """
    Recompute and persist ip_stability, scan_count, and inferred_role for one MAC.

    Called by DeviceTracker after each scan for every device that was seen.
    Uses device_ip_history as the authoritative source for scan_count and stability.
    Never overwrites inferred_role if the device has a custom_name (user label wins).
    """
    stability = compute_ip_stability(mac, store)
    scan_count = store.get_total_seen_count(mac)

    role = infer_role(
        ip=ip,
        device_type=device_type,
        custom_name=custom_name,
        scan_count=scan_count,
        ip_stability=stability,
    )

    # Only update inferred_role when we have a non-None result — never clear an
    # existing inference (e.g. if device_type is temporarily blank after a scan).
    store.update_device_stability(
        mac=mac,
        scan_count=scan_count,
        ip_stability=stability,
        inferred_role=role,
    )

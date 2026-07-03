"""
cert_auto_enroll — derive TLS cert-check targets from port-sweep results
(V6 Sprint 3.3).

Any device the nightly port sweep (modules.port_sweep) found with 443 or
8443 open is a candidate TLS target. This is a pure function — persistence
of the merged target list and of user-excluded hosts is the caller's
responsibility (ui/pages/cert_page.py via QSettings, same as manually
added targets, RULE-FW1).

Architecture rules observed:
  • Pure Python — no PyQt6, no ui/ imports, no I/O (ARCH RULE 3).
"""

from __future__ import annotations

from typing import Iterable, List, Set

from modules.cert_monitor import CertTarget
from modules.config_baseline import DeviceEntry

_TLS_PORTS = (443, 8443)


def auto_enroll_from_sweep(
    entries: List[DeviceEntry],
    existing: List[CertTarget],
    excluded: Iterable[str] = (),
) -> List[CertTarget]:
    """
    Return `existing` plus one new auto-enrolled CertTarget for every device
    in `entries` that exposes a TLS port (443/8443), is not already in
    `existing`, and is not in `excluded` (hosts the user previously removed).
    """
    existing_hosts: Set[str] = {t.host for t in existing}
    excluded_hosts: Set[str] = set(excluded)
    auto: List[CertTarget] = []
    for entry in entries:
        if entry.ip in existing_hosts or entry.ip in excluded_hosts:
            continue
        ports = [p for p in _TLS_PORTS if p in entry.open_ports]
        if not ports:
            continue
        auto.append(CertTarget(host=entry.ip, ports=ports, label="auto"))
    return list(existing) + auto

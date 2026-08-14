"""
scan_settings.py — QSettings-backed helpers for environment-aware scan behaviour.

QSettings key ``scan/flush_caches``:
  present -> explicit user override (Settings > Network Scanning checkbox); always wins.
  absent  -> default computed from the detected NetworkEnvironment: flush on a home
             network (matches pre-2.1.38 behaviour), skip everywhere else — a VPN or
             corporate machine is not this app's OS state to mutate without being asked.

QSettings key ``scan/bound_scope`` (L5):
  present -> explicit user override; always wins.
  absent  -> default computed from NetworkEnvironment.kind: bounded (scope_cidr
             returned) on vpn/corporate/large_subnet, unbounded (None) on home — a
             home ARP table essentially never contains foreign-subnet entries, so
             this is empirically a no-op there.

QSettings key ``scan/net_auth/<fingerprint>`` (L6):
  Per-physical-network authorization state for active probing (Port Scan, Login
  Test), keyed by modules.network_environment.network_fingerprint() (gateway MAC +
  subnet) — NOT by environment kind, so two different physical "home" networks are
  asked about separately. Absent -> None (never asked).

QSettings key ``scan/excluded_hosts`` (L6):
  JSON array of host strings that must never be actively port-scanned or
  credential-tested — a standing exclusion list for fragile devices (printers,
  embedded gear) shared across SYN/UDP/credentialed scan tools.

``experimental/identity_arbitrate_registry`` (Identity A4) used to live here.
It was promoted and the flag REMOVED, not defaulted True (the native_chrome
precedent) -- a permanently-on flag is just a branch nobody tests. Registry and
heuristic claims are now always both submitted to the arbiter; see
``ui/scan_wiring.py::_m1_seed_classification_claims``.
"""
from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtCore import QSettings

_FLUSH_KEY = "scan/flush_caches"
_SCOPE_KEY = "scan/bound_scope"
_AUTH_PREFIX = "scan/net_auth/"
_EXCLUDED_KEY = "scan/excluded_hosts"
_STABLE_ARBITRATION_KEY = "experimental/identity_stable_arbitration"

_POLITE_RATE_PPS = 50    # L6: unauthorized network — hard-capped regardless of kind
_MANAGED_RATE_PPS = 150  # L6: authorized but vpn/corporate — still reduced from the
                          # user's requested rate; only an authorized home/large_subnet
                          # network gets the full requested rate


def identity_stable_arbitration_enabled() -> bool:
    """QSettings ``experimental/identity_stable_arbitration`` (RULE-EXP1).

    OFF by default, so the shipped classification path stays byte-identical
    while the new one proves itself. When ON, callers arbitrate with
    ``arbitrate_stable()`` (order-independent tie-breaking + a margin a
    challenger must clear before a stored label flips) and score the heuristic
    with ``best_rule=True`` (highest-scoring rule, not first-listed).

    Both address the same defect: identity was being decided by ORDER --
    of the claim list, and of _RULES -- rather than by strength of evidence.
    """
    return QSettings("NetSentinel", "NetSentinel").value(
        _STABLE_ARBITRATION_KEY, False, type=bool
    )


def effective_flush_caches() -> bool:
    qs = QSettings("NetSentinel", "NetSentinel")
    if qs.contains(_FLUSH_KEY):
        return qs.value(_FLUSH_KEY, type=bool)
    from modules.network_environment import detect_environment
    return detect_environment().kind == "home"


def effective_scan_scope_cidr(env) -> Optional[str]:
    """Return the CIDR rogue_device.scan() should bound its ARP-table pass to, or
    None for no bounding (today's unfiltered behaviour). *env* is any object
    exposing .kind and .scope_cidr (a NetworkEnvironment in production)."""
    qs = QSettings("NetSentinel", "NetSentinel")
    if qs.contains(_SCOPE_KEY):
        bound = qs.value(_SCOPE_KEY, type=bool)
    else:
        bound = env.kind != "home"
    if not bound:
        return None
    return env.scope_cidr or None


def is_network_authorized(fingerprint: str) -> Optional[bool]:
    """None means this physical network has never been asked about."""
    qs = QSettings("NetSentinel", "NetSentinel")
    key = f"{_AUTH_PREFIX}{fingerprint}"
    if not qs.contains(key):
        return None
    return qs.value(key, type=bool)


def set_network_authorized(fingerprint: str, authorized: bool) -> None:
    QSettings("NetSentinel", "NetSentinel").setValue(f"{_AUTH_PREFIX}{fingerprint}", authorized)


def effective_syn_rate_cap(requested_pps: int, authorized: Optional[bool], kind: str) -> int:
    """L6: unauthorized (None or False) -> polite tier, regardless of kind and
    regardless of how low the user's own request already was. Authorized on a
    managed (vpn/corporate) network -> a still-reduced managed tier. Authorized on
    home/large_subnet -> the user's requested rate, unchanged."""
    if not authorized:
        return min(requested_pps, _POLITE_RATE_PPS)
    if kind in ("vpn", "corporate"):
        return min(requested_pps, _MANAGED_RATE_PPS)
    return requested_pps


def get_excluded_hosts() -> list:
    qs = QSettings("NetSentinel", "NetSentinel")
    raw = qs.value(_EXCLUDED_KEY, "", type=str)
    if not raw:
        return []
    try:
        hosts = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [h.strip() for h in hosts if isinstance(h, str) and h.strip()]


def set_excluded_hosts(hosts: list) -> None:
    cleaned = [h.strip() for h in hosts if isinstance(h, str) and h.strip()]
    QSettings("NetSentinel", "NetSentinel").setValue(_EXCLUDED_KEY, json.dumps(cleaned))


def is_host_excluded(host: str) -> bool:
    target = (host or "").strip().lower()
    if not target:
        return False
    return target in {h.lower() for h in get_excluded_hosts()}

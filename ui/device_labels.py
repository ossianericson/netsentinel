"""
ui/device_labels.py — shared MAC → display-name resolution for live traffic views.

Why this exists
---------------
App Traffic, Live Bandwidth and Timeline each display rows keyed by a source MAC
address. All three used to get their names from a single label map built in
`ui/scan_enrichment.py::_apply_mesh_enrichment()`, which requires a completed scan
in the current session. That left two gaps, both of which shipped as "the chart
only shows MAC addresses":

  1. **No scan this session** — the map is never fed, so every row is a bare MAC
     even though `known_device` already holds a hostname/vendor for most of them.
  2. **Label baked in at capture time** — the capture thread stamps a label onto
     each snapshot and the pages render that string verbatim, so a map that
     arrives *after* monitoring started never relabels the rows already on screen.

This resolver closes both: it adds `known_device` and the OUI registry as
fallbacks behind the fed map, and it is called at *render* time, so a later feed
corrects rows that are already displayed.

Layer note (ARCH RULE 1): this is a `ui/` helper. It only *reads* MetricStore for
display purposes, which the UI layer is allowed to do — it never writes.

Resolution order
----------------
    1. fed label map    — mesh/Deco client names, the richest source
    2. known_device     — custom_name → hostname → vendor
    3. OUI registry     — offline vendor lookup for MACs no scan has ever seen
    4. the MAC itself
"""

from __future__ import annotations

import re
import time
from typing import Dict, Optional

_MAC_RE = re.compile(r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")

#: Store/registry values that carry no more information than the MAC itself.
#: `known_device.vendor` is literally the string "Unknown" for an unresolvable
#: OUI, and rendering that as a device name is strictly worse than the MAC.
_PLACEHOLDER_NAMES = {"", "-", "—", "n/a", "na", "none", "null",
                      "unknown", "unknown device", "unknown vendor"}

#: How long a `known_device` read stays valid before the next lookup re-reads it.
#: The table is small (tens of rows) but this is called from paint paths, so it
#: is cached rather than queried per row.
_STORE_TTL_S = 30.0


def normalise_mac(mac: Optional[str]) -> str:
    """Lowercase, colon-separated form used as the cache/lookup key."""
    if not mac:
        return ""
    return str(mac).strip().lower().replace("-", ":")


def _is_placeholder(name: Optional[str]) -> bool:
    return not name or str(name).strip().lower() in _PLACEHOLDER_NAMES


class DeviceLabelResolver:
    """Resolves a MAC to the best available display name, with caching.

    Safe to construct with `store=None` (headless tests, pages built before the
    store exists) — it then resolves from the fed label map and OUI registry only.
    """

    def __init__(self, store=None, ttl_s: float = _STORE_TTL_S) -> None:
        self._store = store
        self._ttl_s = ttl_s
        self._label_map: Dict[str, str] = {}
        self._known: Dict[str, str] = {}         # mac -> name derived from known_device
        self._known_by_ip: Dict[str, str] = {}   # ip -> name derived from known_device
        self._known_read_at = 0.0
        self._known_loaded = False
        self._resolved: Dict[str, str] = {}   # mac -> final answer (memoised)

    # ── Inputs ────────────────────────────────────────────────────────────────

    def set_store(self, store) -> None:
        self._store = store
        self.invalidate()

    def set_label_map(self, label_map: Optional[dict]) -> None:
        """Install the scan/mesh-derived MAC → name map (see scan_enrichment)."""
        self._label_map = {
            normalise_mac(k): v for k, v in (label_map or {}).items() if k
        }
        self.invalidate()

    def invalidate(self) -> None:
        """Drop every cached answer; the next lookup re-resolves from scratch."""
        self._resolved.clear()
        self._known.clear()
        self._known_by_ip.clear()
        self._known_loaded = False
        self._known_read_at = 0.0

    # ── Lookup ────────────────────────────────────────────────────────────────

    def label_for(self, mac: Optional[str]) -> str:
        """Best display name for *mac*, falling back to the MAC itself."""
        key = normalise_mac(mac)
        if not key:
            return ""
        cached = self._resolved.get(key)
        if cached is not None:
            return cached
        name = self._resolve(key)
        self._resolved[key] = name
        return name

    def label_for_entry(self, mac: Optional[str], snapshot_label: str = "") -> str:
        """Resolve *mac*, but keep *snapshot_label* when nothing better is known.

        Capture-time labels can come from a source this resolver cannot reach
        (Deco client names present during an earlier scan), so a resolved answer
        is only preferred when it is an actual name rather than the MAC.
        """
        key = normalise_mac(mac)
        resolved = self.label_for(key)
        if resolved and resolved != key:
            return resolved
        return snapshot_label or resolved or normalise_mac(mac)

    def label_for_host(self, host: Optional[str]) -> str:
        """Best display name for *host*, which may be a MAC or an IP address.

        Alert surfaces persist `host` as whichever the firing rule used --
        most rule types key by IP, IP_CHURN keys by MAC. A MAC-looking host
        goes through the normal MAC resolution path; an IP is looked up
        directly against known_device.ip. Falls back to *host* unchanged
        (never the MAC/IP-shaped placeholder a fed-map lookup could produce,
        since there is no fed map for a bare IP)."""
        if not host:
            return ""
        host = str(host).strip()
        if _MAC_RE.match(host.lower().replace("-", ":")):
            return self.label_for(host)
        self._ensure_known()
        name = self._known_by_ip.get(host)
        if not _is_placeholder(name):
            return str(name)
        return host

    # ── Internals ─────────────────────────────────────────────────────────────

    def _resolve(self, key: str) -> str:
        fed = self._label_map.get(key)
        # `_hn or _vendor or _mac` upstream means an entry can be the MAC itself.
        if not _is_placeholder(fed) and normalise_mac(fed) != key:
            return str(fed)

        self._ensure_known()
        known = self._known.get(key)
        if not _is_placeholder(known):
            return str(known)

        vendor = self._lookup_oui(key)
        if not _is_placeholder(vendor):
            return str(vendor)

        return key

    def _ensure_known(self) -> None:
        """Refresh the known_device name cache if it is missing or stale."""
        if self._store is None:
            return
        now = time.time()
        if self._known_loaded and (now - self._known_read_at) < self._ttl_s:
            return
        self._known_read_at = now
        self._known_loaded = True
        try:
            devices = self._store.get_known_devices() or {}
        except Exception:
            return  # non-fatal — DB locked/unavailable; fall through to OUI/MAC
        names: Dict[str, str] = {}
        names_by_ip: Dict[str, str] = {}
        for mac, kd in devices.items():
            key = normalise_mac(mac)
            if not key:
                continue
            resolved_name = None
            for attr in ("custom_name", "hostname", "vendor"):
                value = getattr(kd, attr, None) if not isinstance(kd, dict) else kd.get(attr)
                if not _is_placeholder(value):
                    resolved_name = str(value).strip()
                    break
            if resolved_name:
                names[key] = resolved_name
                ip = getattr(kd, "ip", None) if not isinstance(kd, dict) else kd.get("ip")
                if ip:
                    names_by_ip[str(ip).strip()] = resolved_name
        self._known = names
        self._known_by_ip = names_by_ip

    @staticmethod
    def _lookup_oui(key: str) -> Optional[str]:
        """Offline-only OUI vendor lookup.

        `allow_online=False` is mandatory: this runs on the GUI thread from a
        paint path, and the online branch blocks for up to `timeout` seconds per
        unknown MAC (RULE 4).
        """
        try:
            from modules.utils import lookup_vendor
            return lookup_vendor(key, allow_online=False)
        except Exception:
            return None  # non-fatal — registry missing or malformed MAC


def resolve_alert_message(resolver: "DeviceLabelResolver", host: Optional[str], message: str) -> str:
    """Replace a bare host token embedded in an alert message with its
    resolved device name (S4).

    Every alert bakes the raw host straight into `message` at fire time
    ("Port 8443 opened on 192.168.68.51..."), and a device name learned
    later never corrected it. Resolving here at render time, rather than at
    fire time, means a name learned after the alert fired still fixes it —
    the same lesson this module's own docstring records for App Traffic /
    Live Bandwidth / Timeline."""
    if not host or not message or host not in message:
        return message
    name = resolver.label_for_host(host)
    if name and name != host:
        return message.replace(host, name)
    return message

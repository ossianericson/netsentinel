"""
MAC Vendor Lookup — resolves an unknown MAC OUI to a vendor name.

Priority order:
  1. Local mac_registry — curated vendor/model table (no network)
  2. Local offenders.json — curated rogue/problem-device OUI signatures
  3. scapy's bundled manuf database — ~50,000 entries, offline (no network).
     scapy is already a hard dependency (requirements.txt); this queries its
     existing manuf DB, no new install.
  4. Online: https://api.macvendors.com/<MAC>  (free, no key, rate-limited)

Usage::

    from modules.mac_lookup import lookup_vendor

    vendor = lookup_vendor("aa:bb:cc:dd:ee:ff")
    # "Espressif Inc." or None if unresolvable
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Optional


_CACHE: dict[str, Optional[str]] = {}
_LAST_REQUEST: float = 0.0
_MIN_INTERVAL = 1.2   # macvendors.com free tier: ~1 req/sec


def lookup_vendor(
    mac: str,
    offenders_path: Optional[str] = None,
    timeout: int = 5,
    allow_online: bool = True,
) -> Optional[str]:
    """
    Return the vendor name for a MAC address.

    Checks the local registries first (no network); only hits the API if
    all local lookups fail and the caller has not suppressed online lookups.

    Parameters
    ----------
    mac : str
        Full MAC address in any common notation (colons, dashes, no separators).
    offenders_path : str | None
        Path to offenders.json.  If None, uses the default search path.
    timeout : int
        HTTP timeout in seconds for the online lookup.
    allow_online : bool
        If False, tier 4 (api.macvendors.com) is skipped and this function
        never makes a network call, even when the local tiers all miss.

    Returns None if all lookups fail.
    """
    mac_clean = _normalise(mac)
    if not mac_clean:
        return None

    cache_key = mac_clean[:6]
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # 1 — local mac_registry (OUI → model/vendor)
    try:
        from modules.mac_registry import lookup as _mr_lookup
        info = _mr_lookup(mac)
        if info.get("vendor"):
            _CACHE[cache_key] = info["vendor"]
            return info["vendor"]
    except Exception:
        pass  # non-fatal

    oui_colon = ":".join(mac_clean[i:i + 2] for i in range(0, 6, 2))

    # 2 — offenders.json: a LIST of rogue/problem-device signature records
    # ({"vendor": ..., "ouis": [...]}), not an OUI->vendor dict.
    try:
        from modules.utils_platform import get_offenders_path
        import json
        path = offenders_path or get_offenders_path()
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data:
            if oui_colon in (o.lower() for o in entry.get("ouis", [])):
                vendor = entry.get("vendor")
                if vendor:
                    _CACHE[cache_key] = vendor
                    return vendor
    except Exception:
        pass  # non-fatal

    # 3 — scapy's bundled manuf database (offline, no network)
    try:
        from scapy.all import conf as _scapy_conf
        vendor = _scapy_conf.manufdb._get_manuf(oui_colon)
        if vendor and vendor != oui_colon:
            _CACHE[cache_key] = vendor
            return vendor
    except Exception:
        pass  # non-fatal -- scapy unavailable or manuf DB failed to load

    # 4 — online API (rate-limited)
    if not allow_online:
        return None
    vendor = _api_lookup(mac_clean, timeout)
    _CACHE[cache_key] = vendor
    return vendor


def _api_lookup(mac_clean: str, timeout: int) -> Optional[str]:
    """Hit the macvendors.com public API. Returns None on any failure."""
    global _LAST_REQUEST
    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_REQUEST = time.monotonic()

    formatted = ":".join(mac_clean[i:i+2] for i in range(0, 12, 2))
    url = f"https://api.macvendors.com/{formatted}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "NetSentinel/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read(256).decode("utf-8", errors="replace").strip()
            return text or None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None   # unknown OUI — not an error
        return None
    except Exception:
        return None


def _normalise(mac: str) -> str:
    """Return lowercase hex string of length 12, or '' on invalid input."""
    cleaned = mac.lower().replace(":", "").replace("-", "").replace(".", "")
    if len(cleaned) == 12 and all(c in "0123456789abcdef" for c in cleaned):
        return cleaned
    return ""

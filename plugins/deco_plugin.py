"""
NetSentinel Hardware Integration Script — TP-Link Deco XE75
Hardware: TP-Link Deco XE75
Author:   NetSentinel test plugin

Test standalone first:
    python plugins/deco_plugin.py

Then import via Hardware Integration page in NetSentinel and press Test.

Credentials are read from the OS keychain — no passwords in this file.
Connect once via the Mesh Router page in NetSentinel and the password will
be saved automatically.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME    = "TP-Link Deco XE75"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.68.1"   # default; keyring lookup uses the saved host at runtime
DESCRIPTION      = "TP-Link Deco mesh systems — all Deco models with TP-Link account login"
CREDENTIAL_LABEL = "Password"
PYPI_PACKAGE     = "tplinkrouterc6u"


def _load_credentials() -> tuple[str, str]:
    """Return (host, password) from the OS keychain.

    IP resolution order (RULE-PL1):
      1. _NETSENTINEL_INSTANCE_IP  — injected by PluginPollingWorker per instance
      2. NETSENTINEL_PLUGIN_IP env var  — legacy shim for older code paths
      3. HARDWARE_IP constant  — static default

    Password lookup order:
      1. NetSentinel/plugin/<instance_id>  — per-instance keyring (P4-2)
      2. NetSentinel/mesh                  — saved by the Mesh Router page
      3. NetSentinel/hardware/<ip>         — saved by the Hub password field
    """
    # globals() returns this module's own __dict__, where the worker injects the
    # per-instance IP and ID via mod._NETSENTINEL_INSTANCE_IP (RULE-PL1).
    _ip = (globals().get("_NETSENTINEL_INSTANCE_IP")
           or os.environ.get("NETSENTINEL_PLUGIN_IP")
           or HARDWARE_IP)
    _iid = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
    try:
        import keyring
        pw = None
        if _iid:
            pw = keyring.get_password("NetSentinel/plugin", _iid)
        if not pw:
            pw = (keyring.get_password("NetSentinel/mesh", _ip)
                  or keyring.get_password("NetSentinel/hardware", _ip))
        if pw:
            return _ip, pw
    except Exception:
        pass  # keyring unavailable — fall through to RuntimeError below
    raise RuntimeError(
        f"No saved password found for Deco at {_ip}. "
        "Enter the password in the Hardware Integration page and click Save."
    )


# ── Per-poll caches — reset each time exec_module creates a fresh namespace ────
# These let get_status() and get_clients() share one login + one set of API
# calls within a single poll cycle, cutting round-trips from 2×auth+4×API to
# 1×auth+2×API (typically halves the wall-clock time from ~30 s to ~10–12 s).

_cached_client  = None   # DecoMeshClient — reuse session token
_cached_units   = None   # List[MeshUnit] — avoid second device_list call
_cached_clients = None   # List[MeshClient] — avoid second client_list walk


def _get_client():
    global _cached_client
    if _cached_client is None:
        host, password = _load_credentials()
        from modules.deco_client import DecoMeshClient
        client = DecoMeshClient(host, password)
        client.login()
        _cached_client = client
    return _cached_client


def _fetch_all():
    """Login once, fetch mesh units + clients once; cache both for this poll."""
    global _cached_units, _cached_clients
    if _cached_units is None:
        client = _get_client()
        _cached_units   = client.get_mesh_units()
        _cached_clients = client.get_all_clients(units=_cached_units)
    return _cached_units, _cached_clients


# ── Required interface ────────────────────────────────────────────────────────


def _fmt_err(exc: Exception) -> str:
    """Return a structured error string with a machine-readable prefix.

    Checked in order: DEPS (missing package) -> HTTP 401/403 status -> a
    Connection/Timeout exception type -> message keywords (network before
    auth, since a timeout inside an auth call must classify as NET) -> ERR.
    Type/status-code checks come before message keywords because a raw
    requests ConnectionError's message includes the request URL — if that
    URL's path contains a word like "login", keyword-only matching would
    misclassify a plain connection failure as AUTH.
    """
    msg = str(exc)
    if isinstance(exc, ImportError) or 'pip install' in msg:
        return 'DEPS: ' + msg
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status in (401, 403):
        return 'AUTH: ' + msg
    if any(w in type(exc).__name__ for w in ('Connection', 'Timeout')):
        return 'NET: ' + msg
    lm = msg.lower()
    # Check network errors BEFORE auth keywords — a timeout inside an auth call
    # (e.g. "Deco login failed … Read timed out") must be classified as NET, not AUTH.
    if any(w in lm for w in ('refused', 'timed out', 'unreachable', 'no route', 'network is')):
        return 'NET: ' + msg
    if any(w in lm for w in ('auth', 'password', 'login', '401', 'forbidden', 'wrong credential')):
        return 'AUTH: ' + msg
    return 'ERR: ' + msg

def get_info() -> dict:
    host, _ = _load_credentials()
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           host,
        "manufacturer": "TP-Link",
        "model":        "Deco XE75",
        "firmware":     None,
    }


def get_status() -> dict:
    from modules.deco_client import MeshAuthError, MeshApiError
    try:
        units, clients = _fetch_all()
        return {
            "wan_ip":            None,
            "uptime_sec":        None,
            "download_mbps":     None,
            "upload_mbps":       None,
            "signal_dbm":        None,
            "connected_clients": len(clients),
            "mesh_nodes":        len(units),
            "extra": {
                "nodes": [{"name": u.name, "mac": u.mac, "ip": u.ip, "role": u.role}
                          for u in units],
            },
        }
    except (MeshAuthError, MeshApiError) as exc:
        return {
            "wan_ip": None, "uptime_sec": None,
            "download_mbps": None, "upload_mbps": None,
            "signal_dbm": None, "connected_clients": None,
            "extra": {"error": _fmt_err(exc)},
        }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    from modules.deco_client import MeshAuthError, MeshApiError
    try:
        _, raw = _fetch_all()   # reuses the units + clients fetched by get_status()
        return [
            {
                "ip":            c.ip,
                "mac":           c.mac,
                "hostname":      c.name,
                "band":          c.band,
                "unit":          c.unit_name,
                "upload_kbps":   c.upload_kbps,
                "download_kbps": c.download_kbps,
            }
            for c in raw
        ]
    except (MeshAuthError, MeshApiError):
        return []


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ===")
    print(json.dumps(get_clients(), indent=2, default=str))

# ── NetSentinel plugin shim (do not remove) ───────────────────────────────────
import sys as _sys
if "--netsentinel" in _sys.argv:
    import json as _json
    from modules.deco_client import DecoMeshClient, MeshAuthError, MeshApiError
    try:
        _host, _pw = _load_credentials()
        _client = DecoMeshClient(_host, _pw)
        _client.login()
        _units  = _client.get_mesh_units()
        _client_list = [
            {
                "ip":            c.ip,
                "mac":           c.mac,
                "hostname":      c.name or "",
                "band":          c.band,
                "unit":          c.unit_name,
                "upload_kbps":   c.upload_kbps,
                "download_kbps": c.download_kbps,
            }
            for c in _client.get_all_clients(units=_units)
        ]

        _status = {
            "wan_ip": None, "uptime_sec": None, "download_mbps": None,
            "upload_mbps": None, "signal_dbm": None,
            "connected_clients": len(_client_list), "mesh_nodes": len(_units),
            "extra": {"nodes": [{"name": u.name, "mac": u.mac, "ip": u.ip, "role": u.role}
                                 for u in _units]},
        }
        _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": _host,
                 "manufacturer": "TP-Link", "model": "Deco XE75", "firmware": None}
    except (MeshAuthError, MeshApiError, RuntimeError) as _exc:
        _status = {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                   "upload_mbps": None, "signal_dbm": None,
                   "connected_clients": None, "extra": {"error": _fmt_err(_exc)}}
        _client_list = []
        _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
                 "manufacturer": "TP-Link", "model": "Deco XE75", "firmware": None}
    _sys.stdout.write(_json.dumps({
        "info":    _info,
        "status":  _status,
        "clients": _client_list,
    }, default=str) + "\n")
    _sys.exit(0)

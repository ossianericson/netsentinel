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

    Checks in order:
      1. NetSentinel/mesh     — saved by the Mesh Router page
      2. NetSentinel/hardware — saved by the Hardware Integration page password field
    """
    _ip = os.environ.get("NETSENTINEL_PLUGIN_IP") or HARDWARE_IP
    try:
        import keyring
        pw = (keyring.get_password("NetSentinel/mesh", _ip)
              or keyring.get_password("NetSentinel/hardware", _ip))
        if pw:
            return _ip, pw
    except Exception:
        pass
    raise RuntimeError(
        f"No saved password found for Deco at {HARDWARE_IP}. "
        "Enter the password in the Hardware Integration page and click Save."
    )


# ── Shared client — login once, reuse for both get_status and get_clients ─────

def _get_client():
    host, password = _load_credentials()
    from modules.deco_client import DecoMeshClient
    client = DecoMeshClient(host, password)
    client.login()
    return client


# ── Required interface ────────────────────────────────────────────────────────


def _fmt_err(exc: Exception) -> str:
    """Return a structured error string with a machine-readable prefix."""
    msg = str(exc)
    if isinstance(exc, ImportError) or 'pip install' in msg:
        return 'DEPS: ' + msg
    lm = msg.lower()
    if any(w in lm for w in ('auth', 'password', 'login', '401', 'forbidden', 'wrong credential')):
        return 'AUTH: ' + msg
    if any(w in lm for w in ('refused', 'timed out', 'unreachable', 'no route', 'network')):
        return 'NET: ' + msg
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
        client = _get_client()
        units   = client.get_mesh_units()
        clients = client.get_all_clients(units=units)
        return {
            "wan_ip":            None,
            "uptime_sec":        None,
            "download_mbps":     None,
            "upload_mbps":       None,
            "signal_dbm":        None,
            "connected_clients": len(clients),
            "mesh_nodes":        len(units),
            "extra": {
                "nodes": [{"name": u.name, "mac": u.mac, "ip": u.ip, "role": u.role} for u in units],
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
        client = _get_client()
        units  = client.get_mesh_units()
        raw    = client.get_all_clients(units=units)
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

"""
NetSentinel Hardware Integration Script — TP-Link Deco XE75
Hardware: TP-Link Deco XE75
Author:   NetSentinel test plugin

Test standalone first:
    python plugins/deco_plugin.py

Then import via Hardware Integration page in NetSentinel and press Test.

BEFORE MERGING TO MAIN: remove hard-coded PASSWORD — replace with keyring
lookup or environment variable.  This script is for branch testing only.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME = "TP-Link Deco XE75"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.68.1"       # TODO: remove before merge — edit for your LAN
USERNAME      = "admin"
PASSWORD      = "a8-/Ba8+ZZJ_b9z"           # TODO: remove before merge — set your Deco password


# ── Required interface ────────────────────────────────────────────────────────

def get_info() -> dict:
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "TP-Link",
        "model":        "Deco XE75",
        "firmware":     None,   # not exposed by the API without an extra call
    }


def get_status() -> dict:
    from modules.deco_client import DecoMeshClient, MeshAuthError, MeshApiError
    try:
        client = DecoMeshClient(HARDWARE_IP, PASSWORD)
        client.login()
        units = client.get_mesh_units()
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
                "nodes": [{"name": u.name, "mac": u.mac, "role": u.role} for u in units],
            },
        }
    except (MeshAuthError, MeshApiError) as exc:
        return {
            "wan_ip": None, "uptime_sec": None,
            "download_mbps": None, "upload_mbps": None,
            "signal_dbm": None, "connected_clients": None,
            "extra": {"error": str(exc)},
        }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    from modules.deco_client import DecoMeshClient, MeshAuthError, MeshApiError
    try:
        client = DecoMeshClient(HARDWARE_IP, PASSWORD)
        client.login()
        units = client.get_mesh_units()
        raw = client.get_all_clients(units=units)
        return [
            {
                "ip":       c.ip,
                "mac":      c.mac,
                "hostname": c.name,
                "band":     c.band,
                "unit":     c.unit_name,
            }
            for c in raw
        ]
    except (MeshAuthError, MeshApiError):
        return []


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
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
    _sys.stdout.write(_json.dumps({
        "info":    get_info(),
        "status":  get_status(),
        "clients": get_clients(),
    }, default=str) + "\n")
    _sys.exit(0)

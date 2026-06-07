"""
NetSentinel Hardware Plugin — TEMPLATE (router / mesh / AP)

Copy this file, rename it, and replace every  # TODO  line with your
hardware's real API calls.  The structure below is identical to the
verified deco_plugin.py — do not change function signatures, return
shapes, or the shim at the bottom.

Standalone test (run before importing into the app):
    python plugins/my_router_plugin.py

Then import via Hardware Hub and enter your password.

For a MODEM plugin, use zte_plugin.py as the starting point instead.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Required constants ────────────────────────────────────────────────────────
# These are read by the Hardware Hub to display the plugin in the catalog.

HARDWARE_NAME    = "My Router"          # TODO: display name shown in the app
HARDWARE_TYPE    = "router"             # "router", "mesh", or "ap" — not "modem"
HARDWARE_IP      = "192.168.1.1"        # TODO: default gateway IP of your hardware
DESCRIPTION      = "One-line description shown in the plugin catalog"  # TODO
CREDENTIAL_LABEL = "Password"           # label on the password field in the app


# ── Credential helper ─────────────────────────────────────────────────────────
# Passwords are never stored in this file — the app saves them to the OS keychain.
# Call _load_credentials() at the start of get_status() and get_clients().

def _load_credentials() -> tuple[str, str]:
    """Return (host, password) from the OS keychain."""
    try:
        import keyring
        pw = keyring.get_password("NetSentinel/hardware", HARDWARE_IP)
        if pw:
            return HARDWARE_IP, pw
    except Exception:
        pass  # non-fatal
    raise RuntimeError(
        f"No saved password for {HARDWARE_IP}. "
        "Enter the password in the Hardware Hub card and click Save."
    )


# ── Per-poll connection cache ─────────────────────────────────────────────────
# Module-level caches are reset automatically on each poll because
# PluginPollingWorker calls exec_module() fresh every cycle.  This means
# get_status() and get_clients() share ONE login rather than doing two.
_cached_client = None


def _get_client():
    """Return a connected client, logging in only once per poll cycle."""
    global _cached_client
    if _cached_client is None:
        _host, _password = _load_credentials()
        # TODO: replace with your library's client / session object
        # Example:
        #   from mylib import MyRouterClient
        #   _cached_client = MyRouterClient(host, password)
        #   _cached_client.login()
        raise NotImplementedError("Replace _get_client() with your hardware's login logic")
    return _cached_client


# ── Required interface ────────────────────────────────────────────────────────

def get_info() -> dict:
    """Static hardware metadata — no network call needed."""
    host, _ = _load_credentials()
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           host,
        "manufacturer": "TODO",   # TODO: e.g. "ASUS", "Netgear"
        "model":        "TODO",   # TODO: e.g. "RT-AX88U"
        "firmware":     None,     # set to firmware string if you can fetch it cheaply
    }


def get_status() -> dict:
    """
    Return current hardware status.

    connected_clients  — total number of connected clients (used by Overview tile)
    mesh_nodes         — number of nodes (1 for a single router, N for a mesh)
    extra.nodes        — list of node dicts; each needs name, mac, ip, role.
                         The app uses this to build the topology mid-layer.
                         For a single router: one entry with role="primary".
    """
    try:
        client = _get_client()
        # TODO: fetch status from your hardware
        # units   = client.get_nodes()      # list of APs / mesh satellites
        # clients = client.get_clients()    # list of connected devices
        units   = []   # TODO
        clients = []   # TODO
        return {
            "wan_ip":            None,          # TODO: WAN/public IP if available
            "uptime_sec":        None,          # TODO: router uptime in seconds
            "download_mbps":     None,
            "upload_mbps":       None,
            "signal_dbm":        None,
            "connected_clients": len(clients),
            "mesh_nodes":        len(units),
            "extra": {
                # nodes list drives the topology mid-layer and "Group by node" button.
                # For a single router: [{"name": HARDWARE_NAME, "role": "primary",
                #                        "ip": HARDWARE_IP, "mac": ""}]
                "nodes": [
                    {"name": u.name, "mac": u.mac, "ip": u.ip, "role": u.role}
                    for u in units
                ],
            },
        }
    except Exception as exc:
        return {
            "wan_ip": None, "uptime_sec": None,
            "download_mbps": None, "upload_mbps": None,
            "signal_dbm": None, "connected_clients": None,
            "extra": {"error": str(exc)},
        }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    """
    Return connected devices.  Each dict must have at least ip, mac, hostname.

    unit  — name of the mesh node / AP this device is connected to.
             This populates the "Node" column in the Devices table and enables
             the "Group by node" button.  For a single router set unit=HARDWARE_NAME.
    band  — Wi-Fi band string, e.g. "2.4G", "5G", "6G", "Wired".
    """
    try:
        client = _get_client()
        # TODO: fetch client list from your hardware
        raw = []   # TODO: client.get_clients()
        return [
            {
                "ip":       c.ip,       # TODO: adapt field names to your library
                "mac":      c.mac,
                "hostname": c.name,
                "band":     c.band,
                "unit":     c.unit_name,  # TODO: node/AP name; use HARDWARE_NAME if single router
                "upload_kbps":   getattr(c, "upload_kbps",   None),
                "download_kbps": getattr(c, "download_kbps", None),
            }
            for c in raw
        ]
    except Exception:
        return []


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ===")
    print(json.dumps(get_clients(), indent=2, default=str))

# ── NetSentinel plugin shim (do not modify) ───────────────────────────────────
import sys as _sys
if "--netsentinel" in _sys.argv:
    import json as _json
    try:
        _host, _pw = _load_credentials()
    except Exception as _exc:
        _sys.stdout.write(_json.dumps({
            "info":    {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP},
            "status":  {"extra": {"error": str(_exc)}},
            "clients": [],
        }, default=str) + "\n")
        _sys.exit(0)
    try:
        _status  = get_status()
        _clients = get_clients()
        _info    = get_info()
    except Exception as _exc:
        _status  = {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
                    "extra": {"error": str(_exc)}}
        _clients = []
        _info    = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
                    "manufacturer": "TODO", "model": "TODO", "firmware": None}
    _sys.stdout.write(_json.dumps({
        "info":    _info,
        "status":  _status,
        "clients": _clients,
    }, default=str) + "\n")
    _sys.exit(0)

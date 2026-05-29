"""
NetSentinel Hardware Plugin — MikroTik RouterOS
Library: routeros-api  (pip install routeros-api)
Tested:  routeros-api >= 0.0.1alpha24

Standalone test:
    python plugins/mikrotik_plugin.py

Import via Hardware Hub. Enter your MikroTik admin password in the card.
API port 8728 must be enabled on the router (IP → Services → api).

Supports: hAP ax³, hAP ac², CCR2004, RB4011, Audience LTE6, and any device
          running RouterOS with the API service enabled.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "MikroTik Router"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.88.1"
PYPI_PACKAGE     = "routeros-api"
USERNAME         = "admin"
API_PORT         = 8728
DESCRIPTION      = "MikroTik RouterOS — hAP, CCR, RB series; API service must be enabled (port 8728)"
CREDENTIAL_LABEL = "Password"


def _check_deps():
    try:
        import routeros_api  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install routeros-api", file=sys.stderr)
        sys.exit(1)


def _load_password() -> str:
    try:
        import keyring
        pw = keyring.get_password("NetSentinel/hardware", _ip)
        if pw:
            return pw
    except Exception:
        pass
    raise RuntimeError(
        f"No password saved for {HARDWARE_IP}. "
        "Enter it in the Hardware Hub password field and click Save."
    )


def _make_api():
    import routeros_api
    pw   = _load_password()
    pool = routeros_api.RouterOsApiPool(
        HARDWARE_IP,
        username=USERNAME,
        password=pw,
        port=API_PORT,
        plaintext_login=True,   # required for RouterOS >= 6.43
    )
    return pool.get_api()


# ── Plugin interface ──────────────────────────────────────────────────────────


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
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "MikroTik",
        "model":        "RouterOS",
    }


def get_status() -> dict:
    _check_deps()
    api = _make_api()
    # Get WAN IP from first IP address that isn't the LAN subnet
    addresses = api.get_resource("/ip/address").get()
    wan_ip = None
    for a in addresses:
        if not a.get("address", "").startswith("192.168.88"):
            wan_ip = a.get("address", "").split("/")[0]
            break
    leases = api.get_resource("/ip/dhcp-server/lease").get()
    return {
        "wan_ip":            wan_ip,
        "connected_clients": len([l for l in leases if l.get("status") == "bound"]),
        "extra":             {},
    }


def get_clients() -> list:
    _check_deps()
    api    = _make_api()
    leases = api.get_resource("/ip/dhcp-server/lease").get()
    arp    = {a["mac-address"]: a for a in api.get_resource("/ip/arp").get()
              if "mac-address" in a}
    result = []
    for lease in leases:
        if lease.get("status") != "bound":
            continue
        mac  = lease.get("mac-address", "")
        ip   = lease.get("address", "") or arp.get(mac, {}).get("address", "")
        result.append({
            "ip":       ip,
            "mac":      mac,
            "hostname": lease.get("host-name", "") or lease.get("comment", ""),
            "band":     "",
        })
    return result


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Info ===");    print(json.dumps(get_info(), indent=2))
    print("\n=== Status ==="); print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ==="); print(json.dumps(get_clients()[:5], indent=2))

# ── NetSentinel shim ──────────────────────────────────────────────────────────
if "--netsentinel" in sys.argv:
    import json as _json
    _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
             "manufacturer": "MikroTik", "model": "RouterOS"}
    try:
        _status  = get_status()
        _clients = get_clients()
    except Exception as _exc:
        _status  = {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
                    "extra": {"error": _fmt_err(_exc)}}
        _clients = []
    sys.stdout.write(_json.dumps({"info": _info, "status": _status, "clients": _clients},
                                 default=str) + "\n")
    sys.exit(0)

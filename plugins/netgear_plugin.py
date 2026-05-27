"""
NetSentinel Hardware Plugin — Netgear Router / Orbi
Library: pynetgear  (pip install pynetgear)
Tested:  pynetgear >= 0.10

Standalone test:
    python plugins/netgear_plugin.py

Import via Hardware Hub. Enter your Netgear admin password in the card.
USERNAME is not used — pynetgear authenticates with password only.

Supports: Orbi RBK863S/752, Nighthawk AX12/RAX200, R7000, R8000, R9000, and most
          Netgear routers with the SOAP management API enabled.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "Netgear Router"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.1.1"
PYPI_PACKAGE     = "pynetgear"
DESCRIPTION      = "Netgear routers and Orbi mesh — Nighthawk, Orbi RBK series; requires pip install pynetgear"
CREDENTIAL_LABEL = "Password"


def _check_deps():
    try:
        import pynetgear  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install pynetgear", file=sys.stderr)
        sys.exit(1)


def _load_password() -> str:
    try:
        import keyring
        pw = keyring.get_password("NetSentinel/hardware", HARDWARE_IP)
        if pw:
            return pw
    except Exception:
        pass
    raise RuntimeError(
        f"No password saved for {HARDWARE_IP}. "
        "Enter it in the Hardware Hub password field and click Save."
    )


# ── Plugin interface ──────────────────────────────────────────────────────────

def get_info() -> dict:
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "Netgear",
        "model":        "Router / Orbi",
    }


def _make_client():
    from pynetgear import Netgear
    return Netgear(password=_load_password(), host=HARDWARE_IP)


def get_status() -> dict:
    _check_deps()
    ng = _make_client()
    info = ng.get_info() or {}
    return {
        "wan_ip":            info.get("ExternalIPAddress"),
        "uptime_sec":        None,
        "connected_clients": None,
        "extra": {
            "firmware": info.get("Firmwareversion", ""),
            "model":    info.get("ModelName", ""),
        },
    }


def get_clients() -> list:
    _check_deps()
    ng = _make_client()
    _BAND = {"1": "Wired", "2": "2.4G", "3": "5G", "4": "5G-2"}
    devices = ng.get_attached_devices_v2() or []
    return [
        {
            "ip":       getattr(d, "ip",   "") or "",
            "mac":      getattr(d, "mac",  "") or "",
            "hostname": getattr(d, "name", "") or "",
            "band":     _BAND.get(str(getattr(d, "connection_type", "")), ""),
        }
        for d in devices
    ]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Info ===");    print(json.dumps(get_info(), indent=2))
    print("\n=== Status ==="); print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ==="); print(json.dumps(get_clients()[:5], indent=2))

# ── NetSentinel shim ──────────────────────────────────────────────────────────
if "--netsentinel" in sys.argv:
    import json as _json
    _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
             "manufacturer": "Netgear", "model": "Router / Orbi"}
    try:
        _status  = get_status()
        _clients = get_clients()
    except Exception as _exc:
        _status  = {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                    "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
                    "extra": {"error": str(_exc)}}
        _clients = []
    sys.stdout.write(_json.dumps({"info": _info, "status": _status, "clients": _clients},
                                 default=str) + "\n")
    sys.exit(0)

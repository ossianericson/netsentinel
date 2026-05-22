"""
NetSentinel Hardware Plugin — Ubiquiti UniFi
Library: pyunifi  (pip install pyunifi)
Tested:  pyunifi >= 2.21  /  UniFi OS (UDM, UDM Pro, UDM SE, Cloud Key Gen2+)

Standalone test:
    python plugins/unifi_plugin.py

Import via Hardware Hub. Enter your UniFi Network admin password in the card.
USERNAME below defaults to "admin" — change if your account is different.

For older non-UniFi-OS controllers change CONTROLLER_VERSION to "v5".
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME       = "Ubiquiti UniFi"
HARDWARE_TYPE       = "router"
HARDWARE_IP         = "192.168.1.1"
USERNAME            = "admin"
CONTROLLER_VERSION  = "UDMP-unifiOS"   # or "v5" for older standalone controllers


def _check_deps():
    try:
        import pyunifi  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install pyunifi", file=sys.stderr)
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
        "manufacturer": "Ubiquiti",
        "model":        "UniFi",
    }


def _make_controller():
    from pyunifi.controller import Controller
    pw = _load_password()
    return Controller(
        HARDWARE_IP, USERNAME, pw,
        version=CONTROLLER_VERSION,
        ssl_verify=False,
    )


def get_status() -> dict:
    _check_deps()
    c = _make_controller()
    sites = c.get_sites()
    n_clients = len(c.get_clients())
    return {
        "wan_ip":            None,
        "connected_clients": n_clients,
        "extra": {
            "sites": [s.get("desc", s.get("name", "")) for s in sites],
        },
    }


def get_clients() -> list:
    _check_deps()
    c = _make_controller()
    _BAND = {"ng": "2.4G", "na": "5G", "6e": "6G"}
    return [
        {
            "ip":       cl.get("ip", ""),
            "mac":      cl.get("mac", ""),
            "hostname": cl.get("hostname", "") or cl.get("name", ""),
            "band":     _BAND.get(cl.get("radio", ""), cl.get("radio", "")),
            "unit":     cl.get("ap_mac", ""),
        }
        for cl in c.get_clients()
    ]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Info ===");    print(json.dumps(get_info(), indent=2))
    print("\n=== Status ==="); print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ==="); print(json.dumps(get_clients()[:5], indent=2))

# ── NetSentinel shim ──────────────────────────────────────────────────────────
if "--netsentinel" in sys.argv:
    import json as _j, sys as _s
    try:
        _clients = get_clients()
    except Exception:
        _clients = []
    _s.stdout.write(_j.dumps({"info": get_info(), "status": get_status(), "clients": _clients},
                              default=str) + "\n")
    _s.exit(0)

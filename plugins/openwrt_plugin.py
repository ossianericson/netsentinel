"""
NetSentinel Hardware Plugin — OpenWrt / LEDE
Library: openwrt-luci-rpc  (pip install openwrt-luci-rpc)
Tested:  openwrt-luci-rpc >= 1.1.14

Standalone test:
    python plugins/openwrt_plugin.py

Import via Hardware Hub. Enter your OpenWrt root password in the card.
LuCI web interface must be reachable at http://HARDWARE_IP (port 80).

Supports: any router running OpenWrt 18.06+ or LEDE with LuCI installed.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "OpenWrt Router"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.1.1"
USERNAME         = "root"
PYPI_PACKAGE     = "openwrt-luci-rpc"
DESCRIPTION      = "OpenWrt / LEDE routers with LuCI web interface — requires pip install openwrt-luci-rpc"
CREDENTIAL_LABEL = "Password"


def _check_deps():
    try:
        import openwrt_luci_rpc  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install openwrt-luci-rpc", file=sys.stderr)
        sys.exit(1)


def _load_password() -> str:
    try:
        import keyring
        pw = keyring.get_password("NetSentinel/hardware", _ip)
        if pw:
            return pw
    except Exception:
        pass  # non-fatal
    raise RuntimeError(
        f"No password saved for {HARDWARE_IP}. "
        "Enter it in the Hardware Hub password field and click Save."
    )


_cached_rpc = None  # Per-poll cache — reset each exec_module call


def _make_rpc():
    global _cached_rpc
    if _cached_rpc is None:
        from openwrt_luci_rpc import OpenWrtRpc
        _cached_rpc = OpenWrtRpc(HARDWARE_IP, USERNAME, _load_password())
    return _cached_rpc


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
        "manufacturer": "OpenWrt",
        "model":        "OpenWrt / LEDE",
    }


def get_status() -> dict:
    _check_deps()
    rpc = _make_rpc()
    status = rpc.get_status() or {}
    return {
        "wan_ip":            None,
        "uptime_sec":        status.get("uptime"),
        "connected_clients": None,
        "extra":             {"load": status.get("load", [])},
    }


def get_clients() -> list:
    _check_deps()
    rpc = _make_rpc()

    # Build MAC → IP mapping from ARP table
    arp_map: dict[str, str] = {}
    for entry in (rpc.get_arp_table() or []):
        mac = entry.get("macaddr", "").upper()
        ip  = entry.get("ipaddr", "")
        if mac and ip:
            arp_map[mac] = ip

    # Build client list from wireless associations
    result = []
    seen: set[str] = set()
    for radio, ifaces in (rpc.get_wireless_devices() or {}).items():
        band = "5G" if "5" in str(radio) else "2.4G"
        for iface, data in (ifaces.items() if isinstance(ifaces, dict) else {}.items()):
            for assoc in (data.get("assoclist", {}).values() if isinstance(data, dict) else []):
                mac = assoc.get("mac", "").upper()
                if not mac or mac in seen:
                    continue
                seen.add(mac)
                result.append({
                    "ip":       arp_map.get(mac, ""),
                    "mac":      mac,
                    "hostname": "",
                    "band":     band,
                })

    # Add ARP entries that have no wireless association (wired clients)
    for mac, ip in arp_map.items():
        if mac not in seen:
            result.append({"ip": ip, "mac": mac, "hostname": "", "band": "Wired"})

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
             "manufacturer": "OpenWrt", "model": "OpenWrt / LEDE"}
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

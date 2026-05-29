"""
NetSentinel Hardware Plugin — ASUS Router / ZenWiFi
Library: asusrouter  (pip install asusrouter)
Tested:  asusrouter >= 0.20  (async library, wrapped with asyncio.run)

Standalone test:
    python plugins/asus_plugin.py

Import via Hardware Hub. Enter your ASUS admin password in the card.
USERNAME defaults to "admin" — change if you've set a custom account.

Supports: RT-AX88U, RT-AX86U, RT-AX58U, ZenWiFi AX (XT8), ZenWiFi Pro ET12, and all
          other routers running ASUSWRT or ASUSWRT-Merlin firmware.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "ASUS Router"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.50.1"   # default ASUS LAN address
PYPI_PACKAGE     = "asusrouter"
USERNAME         = "admin"
DESCRIPTION      = "ASUS routers and ZenWiFi — ASUSWRT & Merlin firmware; requires pip install asusrouter"
CREDENTIAL_LABEL = "Password"


def _check_deps():
    try:
        import asusrouter  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install asusrouter", file=sys.stderr)
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


# ── Async data fetcher ────────────────────────────────────────────────────────

async def _fetch_all():
    from asusrouter import AsusRouter
    pw = _load_password()
    router = AsusRouter(host=HARDWARE_IP, username=USERNAME, password=pw, use_ssl=False)
    await router.async_connect()
    try:
        devices = await router.async_get_connected_devices()
        info    = await router.async_get_network()
        return devices, info
    finally:
        await router.async_disconnect()


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
        "manufacturer": "ASUS",
        "model":        "Router / ZenWiFi",
    }


def get_status() -> dict:
    _check_deps()
    devices, _ = asyncio.run(_fetch_all())
    return {
        "wan_ip":            None,
        "connected_clients": len(devices),
        "extra":             {},
    }


def get_clients() -> list:
    _check_deps()
    devices, _ = asyncio.run(_fetch_all())
    _BAND = {
        "2g":    "2.4G", "2ghz": "2.4G",
        "5g":    "5G",   "5ghz": "5G",
        "5g2":   "5G-2",
        "6g":    "6G",   "6ghz": "6G",
        "wired": "Wired",
    }
    result = []
    for mac, dev in (devices.items() if isinstance(devices, dict) else enumerate(devices)):
        if isinstance(dev, dict):
            ct = str(dev.get("connection_type", "")).lower()
            result.append({
                "ip":       dev.get("ip", ""),
                "mac":      str(mac) if isinstance(devices, dict) else dev.get("mac", ""),
                "hostname": dev.get("name", "") or dev.get("hostname", ""),
                "band":     _BAND.get(ct, ct),
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
             "manufacturer": "ASUS", "model": "Router / ZenWiFi"}
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

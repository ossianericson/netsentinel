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
import os
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
    except ImportError as exc:
        # Raise (never sys.exit) so get_status()/get_clients() catch this like any
        # other failure and classify it DEPS: via _fmt_err. PluginPollingWorker
        # treats a plugin's sys.exit() as a silent no-op poll (see its SystemExit
        # handler) — exiting here would report NO error at all to the user.
        raise ImportError("Missing dependency — run: pip install asusrouter") from exc


def _host() -> str:
    """Resolve the live device host (RULE-PL1): per-instance IP, env shim, then default."""
    return (globals().get("_NETSENTINEL_INSTANCE_IP")
            or os.environ.get("NETSENTINEL_PLUGIN_IP")
            or HARDWARE_IP)


def _load_password() -> str:
    host = _host()
    iid  = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
    try:
        import keyring
        pw = None
        if iid:
            pw = keyring.get_password("NetSentinel/plugin", iid)
        if not pw:
            pw = keyring.get_password("NetSentinel/hardware", host)
        if pw:
            return pw
    except Exception:
        pass  # keyring unavailable — fall through to RuntimeError below
    raise RuntimeError(
        f"No password saved for {host}. "
        "Enter it in the Hardware Hub password field and click Save."
    )


# ── Per-poll cache — reset each time exec_module creates a fresh namespace ────
_cached_fetch = None  # (devices, info) tuple — reused by get_status + get_clients


async def _fetch_all_async():
    from asusrouter import AsusRouter
    pw = _load_password()
    router = AsusRouter(host=_host(), username=USERNAME, password=pw, use_ssl=False)
    await router.async_connect()
    try:
        devices = await router.async_get_connected_devices()
        info    = await router.async_get_network()
        return devices, info
    finally:
        await router.async_disconnect()


def _fetch_all():
    """Run async fetch once per poll; cache result so get_clients() reuses it."""
    global _cached_fetch
    if _cached_fetch is None:
        _cached_fetch = asyncio.run(_fetch_all_async())
    return _cached_fetch


# ── Plugin interface ──────────────────────────────────────────────────────────


def _fmt_err(exc: Exception) -> str:
    """Return a structured error string with a machine-readable prefix.

    Checked in order: DEPS (missing package) -> HTTP 401/403 status -> a
    Connection/Timeout exception type -> message keywords (network before
    auth) -> ERR. Type/status-code checks come first because a raw
    connection-library exception's message can include the request URL —
    if that URL's path contains a word like "login", keyword-only matching
    would misclassify a plain connection failure as AUTH.
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
    if any(w in lm for w in ('refused', 'timed out', 'unreachable', 'no route', 'network')):
        return 'NET: ' + msg
    if any(w in lm for w in ('auth', 'password', 'login', '401', 'forbidden', 'wrong credential')):
        return 'AUTH: ' + msg
    return 'ERR: ' + msg

def get_info() -> dict:
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           _host(),
        "manufacturer": "ASUS",
        "model":        "Router / ZenWiFi",
    }


def get_status() -> dict:
    try:
        _check_deps()
        devices, _ = _fetch_all()
        return {
            "wan_ip":            None,
            "connected_clients": len(devices),
            "extra":             {},
        }
    except Exception as exc:
        return {
            "wan_ip": None, "uptime_sec": None, "download_mbps": None,
            "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
            "extra": {"error": _fmt_err(exc)},
        }


def get_clients() -> list:
    try:
        _check_deps()
        devices, _ = _fetch_all()
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
    except Exception:
        return []  # get_clients() failures are non-fatal — return empty, not an error


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

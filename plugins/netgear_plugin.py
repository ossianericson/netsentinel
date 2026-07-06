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
import os
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
        # Same `from ... import` spelling used later for the real client --
        # a plain `import pynetgear` here would collide with that (CodeQL
        # py/import-and-import-from, RULE-LINT5).
        from pynetgear import Netgear  # noqa: F401
    except ImportError as exc:
        # Raise (never sys.exit) so get_status()/get_clients() catch this like any
        # other failure and classify it DEPS: via _fmt_err. PluginPollingWorker
        # treats a plugin's sys.exit() as a silent no-op poll (see its SystemExit
        # handler) — exiting here would report NO error at all to the user.
        raise ImportError("Missing dependency — run: pip install pynetgear") from exc


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
        "manufacturer": "Netgear",
        "model":        "Router / Orbi",
    }


_cached_ng = None  # Per-poll cache — reset each exec_module call


def _make_client():
    global _cached_ng
    if _cached_ng is None:
        from pynetgear import Netgear
        _cached_ng = Netgear(password=_load_password(), host=_host())
    return _cached_ng


def get_status() -> dict:
    try:
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
    except Exception as exc:
        return {
            "wan_ip": None, "uptime_sec": None, "download_mbps": None,
            "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
            "extra": {"error": _fmt_err(exc)},
        }


def get_clients() -> list:
    try:
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
             "manufacturer": "Netgear", "model": "Router / Orbi"}
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

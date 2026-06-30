"""
NetSentinel Hardware Plugin — AVM FRITZ!Box
Library: fritzconnection  (pip install fritzconnection)
Tested:  fritzconnection >= 1.12

Standalone test:
    python plugins/fritzbox_plugin.py

Import via Hardware Hub, enter your FRITZ!Box password in the card's password field.
No username needed — FRITZ!Box only requires the admin password.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME      = "AVM FRITZ!Box"
HARDWARE_TYPE      = "router"
HARDWARE_IP        = "192.168.178.1"   # default FRITZ!Box LAN address
PYPI_PACKAGE       = "fritzconnection"
DESCRIPTION        = "AVM FRITZ!Box routers — all models; requires pip install fritzconnection"
CREDENTIAL_LABEL   = "Password"


def _check_deps():
    try:
        import fritzconnection  # noqa: F401
    except ImportError:
        print("Missing dependency — run:  pip install fritzconnection", file=sys.stderr)
        sys.exit(1)


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
        "ip":           _host(),
        "manufacturer": "AVM",
        "model":        "FRITZ!Box",
    }


# ── Per-poll caches — reset each exec_module call ─────────────────────────────
_cached_fritz_status = None
_cached_fritz_hosts  = None


def _get_fritz_status():
    global _cached_fritz_status
    if _cached_fritz_status is None:
        _check_deps()
        from fritzconnection.lib.fritzstatus import FritzStatus
        _cached_fritz_status = FritzStatus(address=_host(), password=_load_password())
    return _cached_fritz_status


def _get_fritz_hosts():
    global _cached_fritz_hosts
    if _cached_fritz_hosts is None:
        _check_deps()
        from fritzconnection.lib.fritzhosts import FritzHosts
        _cached_fritz_hosts = FritzHosts(address=_host(), password=_load_password())
    return _cached_fritz_hosts


def get_status() -> dict:
    _check_deps()
    fs = _get_fritz_status()
    return {
        "wan_ip":            fs.external_ip,
        "uptime_sec":        fs.uptime,
        "connected_clients": None,
        "extra":             {"is_connected": fs.is_connected},
    }


def get_clients() -> list:
    _check_deps()
    fh = _get_fritz_hosts()
    return [
        {
            "ip":       h.get("ip",   ""),
            "mac":      h.get("mac",  ""),
            "hostname": h.get("name", ""),
            "band":     h.get("interface_type", ""),
        }
        for h in fh.get_active_hosts()
    ]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Info ===");    print(json.dumps(get_info(), indent=2))
    print("\n=== Status ==="); print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients ==="); print(json.dumps(get_clients(), indent=2))

# ── NetSentinel shim ──────────────────────────────────────────────────────────
if "--netsentinel" in sys.argv:
    import json as _json
    _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
             "manufacturer": "AVM", "model": "FRITZ!Box"}
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

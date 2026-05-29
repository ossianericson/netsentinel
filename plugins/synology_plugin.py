"""
NetSentinel Hardware Plugin — Synology Router (SRM)
Library: none — uses Synology SRM REST API directly (urllib only)
Tested:  Synology SRM 1.3+

Standalone test:
    python plugins/synology_plugin.py

Import via Hardware Hub. Enter your Synology admin password in the card.
SRM web interface must be reachable at http://HARDWARE_IP:8000.

Supports: RT6600ax, RT2600ac, MR2200ac, WRX560 running SRM.
Note: This is for Synology ROUTERS (SRM firmware), not NAS devices (DSM).
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "Synology Router"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.1.1"
SRM_PORT         = 8000
USERNAME         = "admin"
DESCRIPTION      = "Synology SRM routers — RT6600ax, RT2600ac, MR2200ac, WRX560 (SRM firmware, not DSM NAS)"
CREDENTIAL_LABEL = "Password"


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


def _api_call(session_id: str, api: str, method: str, version: int = 1, **kwargs) -> dict:
    base = f"http://{HARDWARE_IP}:{SRM_PORT}/webapi/entry.cgi"
    params = {"api": api, "method": method, "version": version, "_sid": session_id}
    params.update(kwargs)
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _login() -> str:
    """Return session ID (SID)."""
    pw   = _load_password()
    base = f"http://{HARDWARE_IP}:{SRM_PORT}/webapi/auth.cgi"
    params = urllib.parse.urlencode({
        "api":     "SYNO.API.Auth",
        "version": 6,
        "method":  "login",
        "account": USERNAME,
        "passwd":  pw,
        "format":  "sid",
    })
    req = urllib.request.Request(base + "?" + params)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    if not data.get("success"):
        raise RuntimeError(f"Synology login failed: {data.get('error', {}).get('code', '?')}")
    return data["data"]["sid"]


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
        "manufacturer": "Synology",
        "model":        "SRM Router",
    }


def get_status() -> dict:
    sid  = _login()
    data = _api_call(sid, "SYNO.Core.System", "info")
    info = data.get("data", {})
    return {
        "wan_ip":            None,
        "uptime_sec":        info.get("uptime"),
        "connected_clients": None,
        "extra": {
            "firmware": info.get("ram_size", ""),
            "model":    info.get("model", ""),
        },
    }


def get_clients() -> list:
    sid     = _login()
    data    = _api_call(sid, "SYNO.Core.Network.NSMDevice", "list", version=1)
    devices = data.get("data", {}).get("devices", [])
    _BAND = {"0": "2.4G", "1": "5G", "2": "6G", "3": "Wired"}
    return [
        {
            "ip":       d.get("ip6_addr", "") or d.get("ip_addr", ""),
            "mac":      d.get("mac", ""),
            "hostname": d.get("hostname", "") or d.get("dev_type", ""),
            "band":     _BAND.get(str(d.get("band", "")), ""),
            "unit":     d.get("mesh_node_id", ""),
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
             "manufacturer": "Synology", "model": "SRM Router"}
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

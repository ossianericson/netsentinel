"""
NetSentinel Hardware Plugin — Home Assistant device tracker
Library: none — uses HA REST API directly (urllib only)

This single plugin exposes ALL devices tracked by Home Assistant,
covering hundreds of hardware types: Philips Hue, Sonos, Nest, Ring,
smart TVs, IoT sensors, and anything else HA has an integration for.

Setup:
  1. In Home Assistant: Profile → Long-Lived Access Tokens → Create Token
  2. Paste the token into the HA_TOKEN variable below (or save to keyring)
  3. Set HA_URL to your HA instance address

Standalone test:
    python plugins/ha_plugin.py

Import via Hardware Hub — no password in the card needed (token is in the script).
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Configuration ─────────────────────────────────────────────────────────────
HARDWARE_NAME    = "Home Assistant"
HARDWARE_TYPE    = "router"       # treated as enrichment source like a router
HARDWARE_IP      = "192.168.1.x"  # HA host — update to your HA IP or hostname
HA_URL           = f"http://{HARDWARE_IP}:8123"
HA_TOKEN         = ""             # paste your Long-Lived Access Token here
DESCRIPTION      = "Home Assistant — all HA-tracked devices (Hue, Sonos, IoT…) via Long-Lived Access Token"
CREDENTIAL_LABEL = "Token"


def _load_token() -> str:
    """Return HA token — from variable above or OS keyring fallback."""
    if HA_TOKEN:
        return HA_TOKEN
    try:
        import keyring
        tok = keyring.get_password("NetSentinel/hardware", _ip)
        if tok:
            return tok
    except Exception:
        pass
    raise RuntimeError(
        "No Home Assistant token configured. "
        "Edit ha_plugin.py and set HA_TOKEN, or save it via the Hardware Hub password field."
    )


def _ha_get(endpoint: str) -> object:
    req = urllib.request.Request(
        f"{HA_URL}/api/{endpoint}",
        headers={
            "Authorization": f"Bearer {_load_token()}",
            "Content-Type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


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
        "manufacturer": "Home Assistant",
        "model":        "Local HA instance",
    }


def get_status() -> dict:
    ha_config = _ha_get("config")
    states    = _ha_get("states")
    trackers  = [s for s in states if s["entity_id"].startswith("device_tracker.")]
    home_count = sum(1 for t in trackers if t.get("state") == "home")
    return {
        "wan_ip":            None,
        "connected_clients": home_count,
        "extra": {
            "ha_version":    ha_config.get("version", ""),
            "location_name": ha_config.get("location_name", ""),
            "total_tracked": len(trackers),
        },
    }


def get_clients() -> list:
    states   = _ha_get("states")
    trackers = [s for s in states if s["entity_id"].startswith("device_tracker.")]
    result   = []
    for t in trackers:
        if t.get("state") != "home":
            continue
        attrs = t.get("attributes", {})
        result.append({
            "ip":       attrs.get("ip", ""),
            "mac":      attrs.get("mac", ""),
            "hostname": attrs.get("friendly_name", "") or t["entity_id"].replace("device_tracker.", ""),
            "band":     attrs.get("ssid", ""),
            "unit":     attrs.get("source_type", ""),
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
             "manufacturer": "Home Assistant", "model": "Local HA instance"}
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

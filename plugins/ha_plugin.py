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


def _host() -> str:
    """Resolve the live HA host (RULE-PL1): per-instance IP, env shim, then default."""
    return (globals().get("_NETSENTINEL_INSTANCE_IP")
            or os.environ.get("NETSENTINEL_PLUGIN_IP")
            or HARDWARE_IP)


def _load_token() -> str:
    """Return HA token — from variable above or OS keyring fallback."""
    if HA_TOKEN:
        return HA_TOKEN
    host = _host()
    iid  = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
    try:
        import keyring
        tok = None
        if iid:
            tok = keyring.get_password("NetSentinel/plugin", iid)
        if not tok:
            tok = keyring.get_password("NetSentinel/hardware", host)
        if tok:
            return tok
    except Exception:
        pass  # keyring unavailable — fall through to RuntimeError below
    raise RuntimeError(
        "No Home Assistant token configured. "
        "Edit ha_plugin.py and set HA_TOKEN, or save it via the Hardware Hub password field."
    )


def _ha_get(endpoint: str) -> object:
    req = urllib.request.Request(
        f"http://{_host()}:8123/api/{endpoint}",
        headers={
            "Authorization": f"Bearer {_load_token()}",
            "Content-Type":  "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


# ── Per-poll cache — /api/states is large; fetch once, share across calls ─────
_cached_states = None


def _get_states() -> list:
    global _cached_states
    if _cached_states is None:
        _cached_states = _ha_get("states")
    return _cached_states


# ── Plugin interface ──────────────────────────────────────────────────────────


def _fmt_err(exc: Exception) -> str:
    """Return a structured error string with a machine-readable prefix.

    Checked in order: DEPS (missing package) -> HTTP 401/403 status -> a
    Connection/Timeout exception type -> message keywords (network before
    auth) -> ERR. Type/status-code checks come first because a raw
    connection-library exception's message can include the request URL —
    if that URL's path contains a word like "login", keyword-only matching
    would misclassify a plain connection failure as AUTH. It would also fail
    outright on a non-English-locale OS, where the OS's connection-refused
    message isn't in English — urllib.error.URLError wraps the real socket
    exception in .reason, so that inner type is checked too.
    """
    msg = str(exc)
    if isinstance(exc, ImportError) or 'pip install' in msg:
        return 'DEPS: ' + msg
    status = getattr(getattr(exc, 'response', None), 'status_code', None)
    if status in (401, 403):
        return 'AUTH: ' + msg
    if getattr(exc, 'code', None) in (401, 403):  # urllib.error.HTTPError
        return 'AUTH: ' + msg
    if any(w in type(exc).__name__ for w in ('Connection', 'Timeout')):
        return 'NET: ' + msg
    reason = getattr(exc, 'reason', None)  # urllib.error.URLError wraps the real cause
    if reason is not None and any(w in type(reason).__name__ for w in ('Connection', 'Timeout')):
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
        "manufacturer": "Home Assistant",
        "model":        "Local HA instance",
    }


def get_status() -> dict:
    try:
        ha_config = _ha_get("config")
        states    = _get_states()
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
    except Exception as exc:
        return {
            "wan_ip": None, "uptime_sec": None, "download_mbps": None,
            "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
            "extra": {"error": _fmt_err(exc)},
        }


def get_clients() -> list:
    try:
        states   = _get_states()
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

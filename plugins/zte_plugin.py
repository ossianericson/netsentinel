"""
NetSentinel Hardware Integration Script — ZTE MC889 5G Modem
Hardware: ZTE MC889
Author:   NetSentinel test plugin

Test standalone first:
    python plugins/zte_plugin.py

Then import via Hardware Integration page in NetSentinel and press Test.

Credentials are read from the OS keychain — no passwords in this file.
Connect once via the Modem page in NetSentinel and the password will be
saved automatically.
"""

import json
import os
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so 'modules.*' imports work whether the
# script is run from the repo root, the plugins/ dir, or via PluginWorker.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME    = "ZTE MC889"
HARDWARE_TYPE    = "modem"
HARDWARE_IP      = "192.168.254.1"   # default; keyring lookup uses the saved host at runtime
DESCRIPTION      = "ZTE MC889 5G modem — cellular signal strength, WAN IP, band and cell identity"
CREDENTIAL_LABEL = "Password"


def _load_credentials() -> tuple[str, str]:
    """Return (host, password) from the OS keychain.

    IP resolution order (RULE-PL1):
      1. _NETSENTINEL_INSTANCE_IP  — injected by PluginPollingWorker per instance
      2. NETSENTINEL_PLUGIN_IP env var  — legacy shim for older code paths
      3. HARDWARE_IP constant  — static default

    Password lookup order:
      1. NetSentinel/plugin/<instance_id>  — per-instance keyring (P4-2)
      2. NetSentinel/modem                 — saved by the Modem page
      3. NetSentinel/hardware/<ip>         — saved by the Hub password field
    """
    # globals() returns this module's own __dict__, where the worker injects the
    # per-instance IP and ID via mod._NETSENTINEL_INSTANCE_IP (RULE-PL1).
    _ip = (globals().get("_NETSENTINEL_INSTANCE_IP")
           or os.environ.get("NETSENTINEL_PLUGIN_IP")
           or HARDWARE_IP)
    _iid = globals().get("_NETSENTINEL_INSTANCE_ID") or ""
    try:
        import keyring
        pw = None
        if _iid:
            pw = keyring.get_password("NetSentinel/plugin", _iid)
        if not pw:
            pw = (keyring.get_password("NetSentinel/modem", _ip)
                  or keyring.get_password("NetSentinel/hardware", _ip))
        if pw:
            return _ip, pw
    except Exception:
        pass  # keyring unavailable — fall through to RuntimeError below
    raise RuntimeError(
        f"No saved password found for ZTE modem at {_ip}. "
        "Enter the password in the Hardware Integration page and click Save."
    )


# ── Required interface ────────────────────────────────────────────────────────


def _fmt_err(exc: Exception) -> str:
    """Return a structured error string with a machine-readable prefix.

    Checked in order: DEPS (missing package) -> HTTP 401/403 status -> a
    Connection/Timeout exception type -> message keywords -> ERR. Type/
    status-code checks come before message keywords because a raw requests
    ConnectionError's message includes the request URL — if that URL's path
    contains a word like "login", keyword-only matching would misclassify a
    plain connection failure as AUTH.
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
    if any(w in lm for w in ('auth', 'password', 'login', '401', 'forbidden', 'wrong credential')):
        return 'AUTH: ' + msg
    if any(w in lm for w in ('refused', 'timed out', 'unreachable', 'no route', 'network')):
        return 'NET: ' + msg
    return 'ERR: ' + msg

def get_info() -> dict:
    host, _ = _load_credentials()
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           host,
        "manufacturer": "ZTE",
        "model":        "MC889",
        "firmware":     None,   # fetched live in get_status()
    }


#: Authenticated client reused across polls — see get_status().
#:
#: Held inside a dict that is only ever mutated, never rebound. A plain module
#: global rebound inside get_status() is reported by CodeQL
#: py/unused-global-variable: within that one function the read happens before
#: both writes, so the query sees two dead stores and cannot see the read that
#: matters — the one made by the *next* poll.
_CACHE: dict = {"client": None}


def get_status() -> dict:
    from modules.zte_client import ZteMC889Client, ZteAuthError, ZteApiError
    try:
        host, pw = _load_credentials()
        # PluginPollingWorker polls a "modem" plugin every 30 s. Building a new
        # client per poll meant a new requests.Session per poll, and creating a
        # Session's HTTPS adapter builds an SSLContext whose load_default_certs()
        # enumerates the ENTIRE Windows certificate store — measured at 24% of
        # all Python samples on an idle Dashboard, plus two extra HTTPS
        # round-trips every 30 s. get_signal_data() already re-authenticates
        # itself when the session goes stale, so one cached client is enough.
        client = _CACHE["client"]
        if client is None or getattr(client, "host", None) != host:
            client = ZteMC889Client(host)
            client.login(pw)
            _CACHE["client"] = client
        data = client.get_signal_data()
        return {
            "wan_ip":            data.wan_ip,
            "wan_status":        data.wan_status,
            "uptime_sec":        None,
            "download_mbps":     None,
            "upload_mbps":       None,
            "signal_dbm":        data.nr5g_rsrp_dbm or data.lte_rsrp_dbm,
            "connected_clients": None,
            "extra": {
                "firmware":      data.firmware_version,
                "network_type":  data.network_type,
                "signal_bars":   data.signal_bars,
                "nr5g_band":     data.nr5g_band,
                "nr5g_rsrp_dbm": data.nr5g_rsrp_dbm,
                "nr5g_sinr_db":  data.nr5g_sinr_db,
                "nr5g_rsrq_db":  data.nr5g_rsrq_db,
                "nr5g_pci":      data.nr5g_pci,
                "nr5g_arfcn":    data.nr5g_arfcn,
                "lte_band":      data.lte_band,
                "lte_rsrp_dbm":  data.lte_rsrp_dbm,
                "lte_snr_db":    data.lte_snr_db,
                "lte_rsrq_db":   data.lte_rsrq_db,
                "lte_pci":       data.lte_pci,
                "lte_earfcn":    data.lte_earfcn,
                "cell_id":       data.cell_id,
                "enb_id":        data.enb_id,
                "mcc":           data.mcc,
                "mnc":           data.mnc,
                "endc_info":     data.endc_info,
            },
        }
    except (ZteAuthError, ZteApiError) as exc:
        # Drop the cached client: a revoked cookie or a rebooted modem makes it
        # permanently unusable, so the next poll must build and authenticate a
        # fresh one rather than re-failing against a dead session forever.
        _CACHE["client"] = None
        return {
            "wan_ip": None, "uptime_sec": None,
            "download_mbps": None, "upload_mbps": None,
            "signal_dbm": None, "connected_clients": None,
            "extra": {"error": _fmt_err(exc)},
        }


# ── Optional interface ────────────────────────────────────────────────────────

def get_clients() -> list:
    # ZTE MC889 is a modem — it does not track LAN clients.
    return []


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__" and "--netsentinel" not in sys.argv:
    print("=== Hardware Info ===")
    print(json.dumps(get_info(), indent=2, default=str))
    print("\n=== Live Status ===")
    print(json.dumps(get_status(), indent=2, default=str))
    print("\n=== Clients (ZTE modem — always empty) ===")
    print(json.dumps(get_clients(), indent=2, default=str))

# ── NetSentinel plugin shim (do not remove) ───────────────────────────────────
import sys as _sys
if "--netsentinel" in _sys.argv:
    import json as _json
    from modules.zte_client import ZteMC889Client, ZteAuthError, ZteApiError
    try:
        _host, _pw = _load_credentials()
        _client = ZteMC889Client(_host)
        _client.login(_pw)
        _data = _client.get_signal_data()
        _status = {
            "wan_ip":            _data.wan_ip,
            "wan_status":        _data.wan_status,
            "uptime_sec":        None,
            "download_mbps":     None,
            "upload_mbps":       None,
            "signal_dbm":        _data.nr5g_rsrp_dbm or _data.lte_rsrp_dbm,
            "connected_clients": None,
            "extra": {
                "firmware":      _data.firmware_version,
                "network_type":  _data.network_type,
                "signal_bars":   _data.signal_bars,
                "nr5g_band":     _data.nr5g_band,
                "nr5g_rsrp_dbm": _data.nr5g_rsrp_dbm,
                "nr5g_sinr_db":  _data.nr5g_sinr_db,
                "nr5g_rsrq_db":  _data.nr5g_rsrq_db,
                "nr5g_pci":      _data.nr5g_pci,
                "nr5g_arfcn":    _data.nr5g_arfcn,
                "lte_band":      _data.lte_band,
                "lte_rsrp_dbm":  _data.lte_rsrp_dbm,
                "lte_snr_db":    _data.lte_snr_db,
                "lte_rsrq_db":   _data.lte_rsrq_db,
                "lte_pci":       _data.lte_pci,
                "lte_earfcn":    _data.lte_earfcn,
                "cell_id":       _data.cell_id,
                "enb_id":        _data.enb_id,
                "mcc":           _data.mcc,
                "mnc":           _data.mnc,
                "endc_info":     _data.endc_info,
            },
        }
        _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": _host,
                 "manufacturer": "ZTE", "model": "MC889", "firmware": _data.firmware_version}
    except (ZteAuthError, ZteApiError, RuntimeError) as _exc:
        _status = {"wan_ip": None, "uptime_sec": None, "download_mbps": None,
                   "upload_mbps": None, "signal_dbm": None, "connected_clients": None,
                   "extra": {"error": _fmt_err(_exc)}}
        _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
                 "manufacturer": "ZTE", "model": "MC889", "firmware": None}
    _sys.stdout.write(_json.dumps({
        "info":    _info,
        "status":  _status,
        "clients": [],
    }, default=str) + "\n")
    _sys.exit(0)

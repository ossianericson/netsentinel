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

    Checks in order:
      1. NetSentinel/modem    — saved by the Modem page
      2. NetSentinel/hardware — saved by the Hardware Integration page password field
    """
    try:
        import keyring
        pw = (keyring.get_password("NetSentinel/modem", HARDWARE_IP)
              or keyring.get_password("NetSentinel/hardware", HARDWARE_IP))
        if pw:
            return HARDWARE_IP, pw
    except Exception:
        pass
    raise RuntimeError(
        f"No saved password found for ZTE modem at {HARDWARE_IP}. "
        "Enter the password in the Hardware Integration page and click Save."
    )


# ── Required interface ────────────────────────────────────────────────────────

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


def get_status() -> dict:
    from modules.zte_client import ZteMC889Client, ZteAuthError, ZteApiError
    try:
        host, pw = _load_credentials()
        client = ZteMC889Client(host)
        client.login(pw)
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
        return {
            "wan_ip": None, "uptime_sec": None,
            "download_mbps": None, "upload_mbps": None,
            "signal_dbm": None, "connected_clients": None,
            "extra": {"error": str(exc)},
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
                   "extra": {"error": str(_exc)}}
        _info = {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP,
                 "manufacturer": "ZTE", "model": "MC889", "firmware": None}
    _sys.stdout.write(_json.dumps({
        "info":    _info,
        "status":  _status,
        "clients": [],
    }, default=str) + "\n")
    _sys.exit(0)

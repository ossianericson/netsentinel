"""
NetSentinel Hardware Integration Script — ZTE MC889 5G Modem
Hardware: ZTE MC889
Author:   NetSentinel test plugin

Test standalone first:
    python plugins/zte_plugin.py

Then import via Hardware Integration page in NetSentinel and press Test.

BEFORE MERGING TO MAIN: remove hard-coded PASSWORD — replace with keyring
lookup or environment variable.  This script is for branch testing only.
"""

import json

# ── Metadata (required) ───────────────────────────────────────────────────────
HARDWARE_NAME = "ZTE MC889"
HARDWARE_TYPE = "modem"
HARDWARE_IP   = "192.168.254.1"      # TODO: remove before merge — edit for your LAN
PASSWORD      = "changeme"           # TODO: remove before merge — set your modem password


# ── Required interface ────────────────────────────────────────────────────────

def get_info() -> dict:
    return {
        "name":         HARDWARE_NAME,
        "type":         HARDWARE_TYPE,
        "ip":           HARDWARE_IP,
        "manufacturer": "ZTE",
        "model":        "MC889",
        "firmware":     None,   # fetched live in get_status()
    }


def get_status() -> dict:
    from modules.zte_client import ZteMC889Client, ZteAuthError, ZteApiError
    try:
        client = ZteMC889Client(HARDWARE_IP)
        client.login(PASSWORD)
        data = client.get_signal_data()
        return {
            "wan_ip":            data.wan_ip,
            "uptime_sec":        None,           # MC889 does not expose uptime
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
                "lte_band":      data.lte_band,
                "lte_rsrp_dbm":  data.lte_rsrp_dbm,
                "lte_snr_db":    data.lte_snr_db,
                "cell_id":       data.cell_id,
                "enb_id":        data.enb_id,
                "mcc":           data.mcc,
                "mnc":           data.mnc,
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
if __name__ == "__main__":
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
    _sys.stdout.write(_json.dumps({
        "info":    get_info(),
        "status":  get_status(),
        "clients": get_clients(),
    }, default=str) + "\n")
    _sys.exit(0)

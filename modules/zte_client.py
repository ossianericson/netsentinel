"""
ZTE MC889 5G modem local web-API client.

Authentication
--------------
The MC889 uses a two-step SHA-256 challenge-response: the router supplies a
random LD nonce; the client hashes password → sha256_upper, then hashes
(hash1 + LD) → sha256_upper and POSTs the result.  This exact flow is
required by the hardware and must not be altered.

Password security
-----------------
Passwords are NEVER stored in files.  The caller is responsible for obtaining
the password from the OS keychain or by prompting the user.  This module
retains the password in process memory to support automatic session renewal
when the router's web-UI session cookie expires — this is intentional and
required for unattended reconnects.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests
import requests.exceptions
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class ZteAuthError(Exception):
    """Raised when login to the ZTE modem fails."""


class ZteApiError(Exception):
    """Raised when an authenticated API call returns no usable data."""


# ── Data contract ─────────────────────────────────────────────────────────────

@dataclass
class ZteSignalData:
    """
    Translated modem metrics — canonical internal field names.

    All fields except `ts` are Optional: the modem may omit any key
    depending on its current network mode (e.g. 5G NR fields are None
    when attached on LTE only).
    """
    ts: int                           # Unix seconds when sampled

    # WAN identity
    wan_ip:           Optional[str]   # public WAN IP
    wan_status:       Optional[str]   # ppp_status ("ppp_connected", …)
    firmware_version: Optional[str]
    network_type:     Optional[str]   # "LTE" | "NR5G" | "ENDC" | …
    signal_bars:      Optional[int]   # 0–5

    # PLMN
    mcc: Optional[str]
    mnc: Optional[str]

    # Cell identity
    cell_id: Optional[str]   # raw value from device (may be hex, e.g. "535aa34")
    enb_id:  Optional[str]   # derived: int(cell_id) >> 8

    # 5G NR
    nr5g_rsrp_dbm: Optional[float]   # e.g. -76.0  (from Z5g_rsrp)
    nr5g_sinr_db:  Optional[float]   # e.g. -1.5   (from Z5g_SINR; can be negative)
    nr5g_rsrq_db:  Optional[float]   # e.g. -9.0   (from Z5g_rsrq)
    nr5g_band:     Optional[str]     # e.g. "n78"
    nr5g_pci:      Optional[str]     # e.g. "277"
    nr5g_arfcn:    Optional[str]     # e.g. "642048"

    # LTE primary
    lte_rsrp_dbm: Optional[float]   # e.g. -76.0  (from lte_rsrp)
    lte_snr_db:   Optional[float]   # e.g.  3.4   (from lte_snr)
    lte_rsrq_db:  Optional[float]   # e.g. -11.0  (from lte_rsrq)
    lte_band:     Optional[str]     # e.g. "LTE BAND 3" (raw from device)
    lte_pci:      Optional[str]     # e.g. "178"
    lte_earfcn:   Optional[str]     # e.g. "1750"

    # EN-DC dual-connectivity
    endc_info: Optional[str]        # "1" when EN-DC active, else "0" or None


# ── Goform parameter list (verbatim from working test script) ─────────────────

_CMD_PARAMS = ",".join([
    "Z5g_rsrp", "Z5g_SINR", "Z5g_rsrq",
    "lte_rsrp", "lte_snr", "lte_rsrq",
    "network_type", "wan_active_band", "nr5g_action_band",
    "cell_id", "wan_ipaddr", "ppp_status", "signalbar",
    "wa_inner_version", "lte_pci", "nr5g_pci",
    "wan_active_channel", "nr5g_action_channel",
    "rmcc", "rmnc", "endc_info",
])


# ── Detect ────────────────────────────────────────────────────────────────────

def detect_zte(host: str, timeout: float = 3.0) -> bool:
    """Return True if `host` responds to the ZTE LD challenge endpoint."""
    try:
        ts = int(time.time() * 1000)
        r = requests.get(
            f"https://{host}/goform/goform_get_cmd_process"
            f"?isTest=false&cmd=LD&_={ts}",
            verify=False,
            timeout=timeout,
        )
        return bool(r.json().get("LD"))
    except Exception:
        return False


# ── Client ────────────────────────────────────────────────────────────────────

class ZteMC889Client:
    """
    ZTE MC889 local web-API client.

    The router's session cookie expires periodically (or when the web UI is
    opened in a browser).  Call login() once; if get_signal_data() detects a
    stale session it re-authenticates automatically using the stored password.

    Password is retained in process memory for session renewal — credential
    storage and user prompting is the caller's responsibility (use OS keychain).

    Example
    -------
        c = ZteMC889Client("192.168.254.1")
        c.login(password)
        data = c.get_signal_data()   # ZteSignalData
    """

    def __init__(self, host: str = "192.168.254.1", timeout: float = 10.0) -> None:
        self.host      = host
        self._base_url = f"https://{host}/goform"
        self._timeout  = timeout
        self._session: Optional[requests.Session] = None
        self._password = ""

    # ── Auth ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _sha256_upper(text: str) -> str:
        """SHA-256 hex digest, upper-cased.  Required by MC889 firmware — do not alter."""
        return hashlib.sha256(text.encode()).hexdigest().upper()

    def login(self, password: str, username: str = "admin") -> None:
        """
        Authenticate against the modem.  Raises ZteAuthError on failure.

        Two-step challenge-response required by MC889 hardware:
          1. GET LD nonce from the modem
          2. POST SHA-256(SHA-256(password) + LD) as the credentials

        This exact flow must not be modified.
        """
        self._password = password  # kept for auto-reconnect only

        session = requests.Session()
        session.headers.update({
            "Referer":    f"https://{self.host}/index.html",
            "User-Agent": "Mozilla/5.0",
        })
        session.verify = False

        # Step 1: fetch LD nonce (cache-busted with millisecond timestamp)
        try:
            ts = int(time.time() * 1000)
            ld_resp = session.get(
                f"{self._base_url}/goform_get_cmd_process"
                f"?isTest=false&cmd=LD&_={ts}",
                timeout=self._timeout,
            )
            ld_value = ld_resp.json().get("LD")
        except Exception as exc:
            raise ZteAuthError(
                f"ZTE modem unreachable at {self.host}: {exc}"
            ) from exc

        if not ld_value:
            raise ZteAuthError(
                f"ZTE modem at {self.host} returned no LD nonce — "
                "check that the host IP is correct."
            )

        # Step 2: SHA-256 challenge-response hash chain
        hash1      = self._sha256_upper(password)
        final_hash = self._sha256_upper(hash1 + ld_value)

        login_url = f"{self._base_url}/goform_set_cmd_process"
        for goform_id in ("LOGIN_MULTI_USER", "LOGIN"):
            payload: dict = {
                "isTest":   "false",
                "goformId": goform_id,
                "password": final_hash,
            }
            if goform_id == "LOGIN_MULTI_USER":
                payload["user"] = username
            try:
                resp = session.post(login_url, data=payload, timeout=self._timeout)
                if resp.json().get("result") in ("0", "success"):
                    self._session = session
                    log.debug("ZTE authenticated against %s", self.host)
                    return
            except Exception:
                continue

        raise ZteAuthError(
            f"ZTE login failed for {self.host}. "
            "Verify the local admin password (not the ZTE cloud account)."
        )

    # ── Raw fetch ─────────────────────────────────────────────────────────────

    def _fetch_raw(self) -> Optional[dict]:
        """Single goform GET for all signal params.  Returns JSON dict or None on any failure."""
        if self._session is None:
            return None
        url = (
            f"{self._base_url}/goform_get_cmd_process"
            f"?isTest=false&isReadPc=1&multi_data=1&cmd={_CMD_PARAMS}"
        )
        try:
            resp = self._session.get(url, timeout=self._timeout)
            data = resp.json()
            return data if isinstance(data, dict) and data else None
        except Exception:
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_signal_data(self) -> ZteSignalData:
        """
        Return translated signal metrics as a ZteSignalData dataclass.

        If the session has expired (None or empty JSON), re-authenticates once
        using the stored password then retries.  Raises ZteApiError if data is
        still unavailable after the reconnect attempt.
        """
        raw = self._fetch_raw()

        if raw is None:
            if not self._password:
                raise ZteApiError(
                    "ZTE session expired and no password is stored for reconnect."
                )
            log.debug("ZTE session stale — re-authenticating against %s", self.host)
            self.login(self._password)
            raw = self._fetch_raw()

        if raw is None:
            raise ZteApiError(
                f"ZTE modem at {self.host} returned no data after reconnect."
            )

        return self._parse(raw)

    # ── Parser / adapter ──────────────────────────────────────────────────────

    @staticmethod
    def _parse(raw: dict) -> ZteSignalData:
        """Map raw ZTE key names to internal canonical field names."""

        def _float(key: str) -> Optional[float]:
            val = raw.get(key, "")
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        def _int(key: str) -> Optional[int]:
            val = raw.get(key, "")
            try:
                return int(float(val))
            except (TypeError, ValueError):
                return None

        def _str(key: str) -> Optional[str]:
            val = raw.get(key, "")
            s = str(val).strip() if val else ""
            return s if s else None

        # Derive eNB/gNB ID from cell_id (cell_id may be hex, e.g. "535aa34")
        enb_id: Optional[str] = None
        cell_id_raw = raw.get("cell_id", "")
        if cell_id_raw:
            try:
                cid = (
                    int(str(cell_id_raw), 16)
                    if any(c.isalpha() for c in str(cell_id_raw))
                    else int(str(cell_id_raw))
                )
                enb_id = str(cid >> 8)
            except (TypeError, ValueError):
                pass

        return ZteSignalData(
            ts=int(time.time()),

            # WAN
            wan_ip=_str("wan_ipaddr"),
            wan_status=_str("ppp_status"),
            firmware_version=_str("wa_inner_version"),
            network_type=_str("network_type"),
            signal_bars=_int("signalbar"),

            # PLMN
            mcc=_str("rmcc"),
            mnc=_str("rmnc"),

            # Cell
            cell_id=_str("cell_id"),
            enb_id=enb_id,

            # 5G NR
            nr5g_rsrp_dbm=_float("Z5g_rsrp"),
            nr5g_sinr_db=_float("Z5g_SINR"),
            nr5g_rsrq_db=_float("Z5g_rsrq"),
            nr5g_band=_str("nr5g_action_band"),
            nr5g_pci=_str("nr5g_pci"),
            nr5g_arfcn=_str("nr5g_action_channel"),

            # LTE
            lte_rsrp_dbm=_float("lte_rsrp"),
            lte_snr_db=_float("lte_snr"),
            lte_rsrq_db=_float("lte_rsrq"),
            lte_band=_str("wan_active_band"),
            lte_pci=_str("lte_pci"),
            lte_earfcn=_str("wan_active_channel"),

            # EN-DC
            endc_info=_str("endc_info"),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def signal_quality_label(rsrp_dbm: Optional[float]) -> str:
        """Return a plain-text signal quality label based on RSRP (dBm)."""
        if rsrp_dbm is None:
            return "N/A"
        try:
            r = float(rsrp_dbm)
        except (TypeError, ValueError):
            return "N/A"
        if r >= -80:
            return "Excellent"
        if r >= -90:
            return "Good"
        if r >= -100:
            return "Fair"
        return "Poor"

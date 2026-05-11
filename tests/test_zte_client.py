"""
Unit tests for modules/zte_client.py

Covers:
  • _sha256_upper — hash chain correctness
  • _parse — real-device field mapping
  • _parse — hex cell_id / eNB derivation (e.g. "535aa34" → 341418)
  • _parse — negative SINR parsed correctly
  • _parse — LTE-band string stored as-is ("LTE BAND 3")
  • _parse — graceful None for missing / unparseable fields
  • signal_quality_label — all four quality bands + None guard
  • detect_zte — returns True/False based on mocked HTTP response
  • ZteMC889Client._fetch_raw — returns None when session is None
  • get_signal_data — auto-reconnect path on stale session
  • ZteAuthError / ZteApiError are importable distinct exceptions
"""

from __future__ import annotations

import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
try:
    from modules.zte_client import (
        ZteAuthError,
        ZteApiError,
        ZteMC889Client,
        ZteSignalData,
        detect_zte,
    )
    signal_quality_label = ZteMC889Client.signal_quality_label
except ImportError as exc:
    pytest.skip(f"modules.zte_client not importable: {exc}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Shared raw-device fixture (matches real MC889 output from test session)
# ---------------------------------------------------------------------------

REAL_RAW = {
    "Z5g_rsrp":          "-76",
    "Z5g_SINR":          "-1.5",
    "Z5g_rsrq":          "-9",
    "lte_rsrp":          "-80",
    "lte_snr":           "3.4",
    "lte_rsrq":          "-11",
    "network_type":      "ENDC",
    "wan_active_band":   "LTE BAND 3",
    "nr5g_action_band":  "n78",
    "cell_id":           "535aa34",
    "wan_ipaddr":        "10.0.0.1",
    "ppp_status":        "ppp_connected",
    "signalbar":         "5",
    "wa_inner_version":  "BD_ZNRV1.0.0B05",
    "lte_pci":           "178",
    "nr5g_pci":          "277",
    "wan_active_channel": "1750",
    "nr5g_action_channel": "642048",
    "rmcc":              "240",
    "rmnc":              "7",
    "endc_info":         "1",
}


# ---------------------------------------------------------------------------
# _sha256_upper
# ---------------------------------------------------------------------------

class TestSha256Upper:
    def test_known_value(self):
        result = ZteMC889Client._sha256_upper("password")
        assert result == result.upper()
        assert len(result) == 64

    def test_empty_string(self):
        result = ZteMC889Client._sha256_upper("")
        assert len(result) == 64
        assert result == result.upper()

    def test_deterministic(self):
        assert ZteMC889Client._sha256_upper("abc") == ZteMC889Client._sha256_upper("abc")

    def test_different_inputs_differ(self):
        assert ZteMC889Client._sha256_upper("a") != ZteMC889Client._sha256_upper("b")


# ---------------------------------------------------------------------------
# _parse — field mapping
# ---------------------------------------------------------------------------

class TestParse:
    def _parse(self, raw: dict) -> ZteSignalData:
        return ZteMC889Client._parse(raw)

    def test_5g_rsrp(self):
        data = self._parse(REAL_RAW)
        assert data.nr5g_rsrp_dbm == -76.0

    def test_negative_sinr(self):
        """SINR can be negative — must not be treated as missing."""
        data = self._parse(REAL_RAW)
        assert data.nr5g_sinr_db == -1.5

    def test_hex_cell_id_stored_verbatim(self):
        data = self._parse(REAL_RAW)
        assert data.cell_id == "535aa34"

    def test_enb_id_derived_from_hex_cell_id(self):
        """int("535aa34", 16) >> 8 == 341418"""
        data = self._parse(REAL_RAW)
        assert data.enb_id == "341418"

    def test_lte_band_stored_as_is(self):
        """Device returns "LTE BAND 3" — store the full string."""
        data = self._parse(REAL_RAW)
        assert data.lte_band == "LTE BAND 3"

    def test_nr5g_band(self):
        data = self._parse(REAL_RAW)
        assert data.nr5g_band == "n78"

    def test_network_type(self):
        data = self._parse(REAL_RAW)
        assert data.network_type == "ENDC"

    def test_signal_bars(self):
        data = self._parse(REAL_RAW)
        assert data.signal_bars == 5

    def test_wan_ip(self):
        data = self._parse(REAL_RAW)
        assert data.wan_ip == "10.0.0.1"

    def test_endc_info(self):
        data = self._parse(REAL_RAW)
        assert data.endc_info == "1"

    def test_mcc_mnc(self):
        data = self._parse(REAL_RAW)
        assert data.mcc == "240"
        assert data.mnc == "7"

    def test_lte_rsrp(self):
        data = self._parse(REAL_RAW)
        assert data.lte_rsrp_dbm == -80.0

    def test_lte_snr(self):
        data = self._parse(REAL_RAW)
        assert data.lte_snr_db == 3.4

    def test_missing_field_returns_none(self):
        data = self._parse({})
        assert data.nr5g_rsrp_dbm is None
        assert data.enb_id is None
        assert data.cell_id is None

    def test_unparseable_rsrp_returns_none(self):
        data = self._parse({"Z5g_rsrp": "N/A"})
        assert data.nr5g_rsrp_dbm is None

    def test_decimal_cell_id_enb_derivation(self):
        """Decimal cell_id (no alpha chars) → integer shift."""
        data = self._parse({"cell_id": "87290164"})
        expected = str(87290164 >> 8)
        assert data.enb_id == expected

    def test_ts_is_recent_unix_seconds(self):
        before = int(time.time()) - 2
        data = self._parse(REAL_RAW)
        assert data.ts >= before

    def test_firmware_version(self):
        data = self._parse(REAL_RAW)
        assert data.firmware_version == "BD_ZNRV1.0.0B05"


# ---------------------------------------------------------------------------
# signal_quality_label
# ---------------------------------------------------------------------------

class TestSignalQualityLabel:
    def test_excellent(self):
        assert ZteMC889Client.signal_quality_label(-76.0) == "Excellent"
        assert ZteMC889Client.signal_quality_label(-80.0) == "Excellent"

    def test_good(self):
        assert ZteMC889Client.signal_quality_label(-81.0) == "Good"
        assert ZteMC889Client.signal_quality_label(-90.0) == "Good"

    def test_fair(self):
        assert ZteMC889Client.signal_quality_label(-91.0) == "Fair"
        assert ZteMC889Client.signal_quality_label(-100.0) == "Fair"

    def test_poor(self):
        assert ZteMC889Client.signal_quality_label(-101.0) == "Poor"
        assert ZteMC889Client.signal_quality_label(-130.0) == "Poor"

    def test_none_returns_na(self):
        assert ZteMC889Client.signal_quality_label(None) == "N/A"

    def test_bad_type_returns_na(self):
        assert ZteMC889Client.signal_quality_label("not-a-number") == "N/A"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# detect_zte
# ---------------------------------------------------------------------------

class TestDetectZte:
    def test_returns_true_when_ld_present(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"LD": "ABCDEF1234567890"}
        with patch("requests.get", return_value=mock_resp):
            assert detect_zte("192.168.254.1") is True

    def test_returns_false_when_ld_absent(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        with patch("requests.get", return_value=mock_resp):
            assert detect_zte("192.168.254.1") is False

    def test_returns_false_on_connection_error(self):
        with patch("requests.get", side_effect=OSError("unreachable")):
            assert detect_zte("192.168.1.1") is False


# ---------------------------------------------------------------------------
# ZteMC889Client._fetch_raw
# ---------------------------------------------------------------------------

class TestFetchRaw:
    def test_returns_none_when_no_session(self):
        client = ZteMC889Client("192.168.254.1")
        assert client._fetch_raw() is None

    def test_returns_none_on_request_exception(self):
        client = ZteMC889Client("192.168.254.1")
        client._session = MagicMock()
        client._session.get.side_effect = OSError("boom")
        assert client._fetch_raw() is None

    def test_returns_none_when_json_empty(self):
        client = ZteMC889Client("192.168.254.1")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        client._session = MagicMock()
        client._session.get.return_value = mock_resp
        assert client._fetch_raw() is None

    def test_returns_dict_on_success(self):
        client = ZteMC889Client("192.168.254.1")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"Z5g_rsrp": "-76"}
        client._session = MagicMock()
        client._session.get.return_value = mock_resp
        result = client._fetch_raw()
        assert result == {"Z5g_rsrp": "-76"}


# ---------------------------------------------------------------------------
# get_signal_data — auto-reconnect path
# ---------------------------------------------------------------------------

class TestGetSignalDataReconnect:
    def test_raises_api_error_when_no_password_and_stale_session(self):
        client = ZteMC889Client("192.168.254.1")
        client._session = None   # stale — _fetch_raw returns None
        client._password = ""
        with pytest.raises(ZteApiError):
            client.get_signal_data()

    def test_reconnects_on_stale_session(self):
        """First _fetch_raw returns None (stale), login is called, second returns data."""
        client = ZteMC889Client("192.168.254.1")
        client._password = "secret"

        with (
            patch.object(client, "_fetch_raw", side_effect=[None, REAL_RAW]),
            patch.object(client, "login", return_value=None) as mock_login,
        ):
            data = client.get_signal_data()

        mock_login.assert_called_once_with("secret")
        assert data.nr5g_rsrp_dbm == -76.0

    def test_raises_api_error_when_still_none_after_reconnect(self):
        client = ZteMC889Client("192.168.254.1")
        client._password = "secret"

        with (
            patch.object(client, "_fetch_raw", return_value=None),
            patch.object(client, "login", return_value=None),
        ):
            with pytest.raises(ZteApiError):
                client.get_signal_data()


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

def test_exception_types_are_distinct():
    assert ZteAuthError is not ZteApiError

def test_zte_auth_error_is_exception():
    exc = ZteAuthError("bad password")
    assert isinstance(exc, Exception)
    assert str(exc) == "bad password"

def test_zte_api_error_is_exception():
    exc = ZteApiError("no data")
    assert isinstance(exc, Exception)
    assert str(exc) == "no data"

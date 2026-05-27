"""
Tests for ui/pages/modem_page.py

Covers:
  • ModemPage constructs without crash (offscreen Qt)
  • on_modem_signal() populates labels correctly
  • on_modem_signal() switches stack to data view (index 1)
  • negative SINR rendered correctly ("-1.5 dB")
  • EN-DC info rendered as "Yes" / "No" / "—"
  • RSRP label shows dBm suffix
  • signal_bars rendered as "X/5"
  • operator rendered as "MCC-MNC"
  • on_modem_error() resets button and shows error
  • on_modem_status() updates status label
  • connect button emits connect_requested with correct args
  • connect button requires host and password
  • disconnect button emits disconnect_requested
  • _quality_color thresholds (helper function)
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Qt bootstrap — must happen before importing page
# ---------------------------------------------------------------------------
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------
try:
    from ui.pages.modem_page import ModemPage, _quality_color
except ImportError as exc:
    pytest.skip(f"ui.pages.modem_page not importable: {exc}", allow_module_level=True)

from ui.styles import GREEN, AMBER, RED, TEXT_SECONDARY


# ---------------------------------------------------------------------------
# Shared fixture data (matches real MC889 output)
# ---------------------------------------------------------------------------

REAL_DATA = {
    "ts":               1715000000,
    "host":             "192.168.254.1",
    "wan_ip":           "10.0.0.1",
    "wan_status":       "ppp_connected",
    "firmware_version": "BD_ZNRV1.0.0B05",
    "network_type":     "ENDC",
    "signal_bars":      5,
    "mcc":              "240",
    "mnc":              "7",
    "cell_id":          "535aa34",
    "enb_id":           "341418",
    "nr5g_rsrp_dbm":    -76.0,
    "nr5g_sinr_db":     -1.5,
    "nr5g_rsrq_db":     -9.0,
    "nr5g_band":        "n78",
    "nr5g_pci":         "277",
    "nr5g_arfcn":       "642048",
    "lte_rsrp_dbm":     -80.0,
    "lte_snr_db":       3.4,
    "lte_rsrq_db":      -11.0,
    "lte_band":         "LTE BAND 3",
    "lte_pci":          "178",
    "lte_earfcn":       "1750",
    "endc_info":        "1",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page() -> ModemPage:
    """Construct a ModemPage with keyring and QSettings stubs."""
    mock_settings = MagicMock()
    mock_settings.value.return_value = ""
    with (
        patch("ui.pages.modem_page._keyring_available", return_value=False),
        patch("ui.pages.modem_page._keyring_load",      return_value=None),
        patch("ui.pages.modem_page.QSettings", return_value=mock_settings),
    ):
        return ModemPage(parent=None)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestModemPageConstruction:
    def test_constructs_without_crash(self):
        page = _make_page()
        assert page is not None

    def test_initial_stack_index_is_empty(self):
        page = _make_page()
        assert page._signal_stack.currentIndex() == 0

    def test_connect_button_exists(self):
        page = _make_page()
        assert page._connect_btn is not None

    def test_signals_exist(self):
        page = _make_page()
        assert hasattr(page, "connect_requested")
        assert hasattr(page, "disconnect_requested")


# ---------------------------------------------------------------------------
# on_modem_signal — data display
# ---------------------------------------------------------------------------

class TestOnModemSignal:
    def setup_method(self):
        self.page = _make_page()
        self.page.on_modem_signal(REAL_DATA)

    def test_stack_switches_to_data_view(self):
        assert self.page._signal_stack.currentIndex() == 1

    def test_wan_ip_displayed(self):
        assert self.page._v_wan_ip.text() == "10.0.0.1"

    def test_network_type_displayed(self):
        assert self.page._v_network_type.text() == "ENDC"

    def test_signal_bars_displayed(self):
        assert self.page._v_signal_bars.text() == "5/5"

    def test_operator_mcc_mnc(self):
        assert self.page._v_operator.text() == "240-7"

    def test_nr5g_rsrp_formatted(self):
        assert self.page._v_nr5g_rsrp.text() == "-76.0 dBm"

    def test_negative_sinr_formatted(self):
        """SINR of -1.5 must render as "-1.5 dB", not "—"."""
        assert self.page._v_nr5g_sinr.text() == "-1.5 dB"

    def test_nr5g_rsrq_formatted(self):
        assert self.page._v_nr5g_rsrq.text() == "-9.0 dB"

    def test_nr5g_band(self):
        assert self.page._v_nr5g_band.text() == "n78"

    def test_lte_rsrp_formatted(self):
        assert self.page._v_lte_rsrp.text() == "-80.0 dBm"

    def test_lte_snr_positive(self):
        assert self.page._v_lte_snr.text() == "3.4 dB"

    def test_lte_band_full_string(self):
        assert self.page._v_lte_band.text() == "LTE BAND 3"

    def test_cell_id(self):
        assert self.page._v_cell_id.text() == "535aa34"

    def test_enb_id(self):
        assert self.page._v_enb_id.text() == "341418"

    def test_endc_active_shown_as_yes(self):
        assert self.page._v_endc_info.text() == "Yes"

    def test_endc_inactive_shown_as_no(self):
        data = {**REAL_DATA, "endc_info": "0"}
        self.page.on_modem_signal(data)
        assert self.page._v_endc_info.text() == "No"

    def test_endc_none_shown_as_dash(self):
        data = {**REAL_DATA, "endc_info": None}
        self.page.on_modem_signal(data)
        assert self.page._v_endc_info.text() == "—"

    def test_firmware(self):
        assert self.page._v_firmware.text() == "BD_ZNRV1.0.0B05"

    def test_none_fields_show_dash(self):
        sparse = {k: None for k in REAL_DATA}
        sparse["ts"] = 0
        sparse["host"] = "192.168.254.1"
        self.page.on_modem_signal(sparse)
        assert self.page._v_wan_ip.text() == "—"
        assert self.page._v_nr5g_rsrp.text() == "—"
        assert self.page._v_signal_bars.text() == "—"


# ---------------------------------------------------------------------------
# on_modem_error / on_modem_status
# ---------------------------------------------------------------------------

class TestOnModemError:
    def test_on_modem_error_resets_button(self):
        page = _make_page()
        page._connected = True
        page._connect_btn.setText("■  Disconnect")
        page.on_modem_error("timeout")
        assert page._connect_btn.text() == "▶  Connect"
        assert page._connect_btn.isEnabled()
        assert not page._connected

    def test_on_modem_error_shows_message(self):
        page = _make_page()
        page.on_modem_error("authentication failed")
        assert "authentication failed" in page._status_lbl.text()

    def test_on_modem_status_updates_label(self):
        page = _make_page()
        page.on_modem_status("Connected — polling…")
        assert page._status_lbl.text() == "Connected — polling…"


# ---------------------------------------------------------------------------
# connect_requested signal
# ---------------------------------------------------------------------------

class TestConnectSignal:
    def test_connect_emits_host_and_password(self):
        page = _make_page()
        page._ip_edit.setText("192.168.1.1")
        page._pw_edit.setText("secret")

        received = []
        page.connect_requested.connect(lambda h, p: received.append((h, p)))

        mock_s = MagicMock()
        with patch("ui.pages.modem_page.QSettings", return_value=mock_s):
            page._on_connect_clicked()

        assert received == [("192.168.1.1", "secret")]

    def test_connect_uses_placeholder_when_host_empty(self):
        """Empty IP field falls back to placeholder text (192.168.254.1)."""
        page = _make_page()
        page._ip_edit.setText("")
        page._pw_edit.setText("secret")

        received = []
        page.connect_requested.connect(lambda h, p: received.append((h, p)))

        mock_s = MagicMock()
        with patch("ui.pages.modem_page.QSettings", return_value=mock_s):
            page._on_connect_clicked()

        assert len(received) == 1
        assert received[0][0] == page._ip_edit.placeholderText()
        assert received[0][1] == "secret"

    def test_connect_requires_password(self):
        page = _make_page()
        page._ip_edit.setText("192.168.1.1")
        page._pw_edit.setText("")

        received = []
        page.connect_requested.connect(lambda h, p: received.append((h, p)))
        page._on_connect_clicked()

        assert received == []

    def test_connect_button_becomes_disconnect(self):
        page = _make_page()
        page._ip_edit.setText("192.168.1.1")
        page._pw_edit.setText("pw")

        mock_s = MagicMock()
        with patch("ui.pages.modem_page.QSettings", return_value=mock_s):
            page._on_connect_clicked()

        assert "Disconnect" in page._connect_btn.text()

    def test_disconnect_emits_disconnect_requested(self):
        page = _make_page()
        page._ip_edit.setText("192.168.1.1")
        page._pw_edit.setText("pw")
        page._connected = True
        page._connect_btn.setText("■  Disconnect")

        fired = []
        page.disconnect_requested.connect(lambda: fired.append(True))
        page._on_connect_clicked()

        assert fired


# ---------------------------------------------------------------------------
# _quality_color helper
# ---------------------------------------------------------------------------

class TestQualityColor:
    def test_none_returns_muted(self):
        assert _quality_color(None) == TEXT_SECONDARY

    def test_excellent_is_green(self):
        assert _quality_color(-76.0) == GREEN
        assert _quality_color(-80.0) == GREEN

    def test_good_is_amber_ish(self):
        color = _quality_color(-85.0)
        assert color != GREEN and color != RED

    def test_poor_is_red(self):
        assert _quality_color(-105.0) == RED

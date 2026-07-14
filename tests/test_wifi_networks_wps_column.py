"""
Regression test for F-25/F-52: WPS-enabled networks are computed by
modules/wifi_scanner.py (WifiNetwork.wps_enabled) but the WiFi Networks
table (ui/tabs_scan.py's _m4_table, populated by
ScanEnrichmentMixin._on_m4_result) never read the field -- there was no
WPS column anywhere in the UI.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QLabel, QStackedWidget, QTableWidget, QWidget

from ui.scan_enrichment import ScanEnrichmentMixin


class _FakeHost(ScanEnrichmentMixin, QWidget):
    """Minimal host exposing just what _on_m4_result touches."""

    def __init__(self):
        super().__init__()
        self._m4_table = QTableWidget(0, 10)
        self._m4_status = QLabel()
        self._m4_stack = QStackedWidget()
        self._m4_stack.addWidget(QWidget())
        self._m4_stack.addWidget(QWidget())

    def _update_overall_verdict(self):
        pass

    def _nav_set_scan_state(self, *args, **kwargs):
        pass


def _wifi_result(wps_enabled: bool):
    net = SimpleNamespace(
        ssid="TestNet", bssid="aa:bb:cc:00:00:01", channel=6, band="2.4G",
        signal_dbm=-55, is_rogue_ssid=False, co_channel_conflict=False,
        wps_enabled=wps_enabled,
    )
    return SimpleNamespace(networks=[net], my_ssid="", rogue_count=0, hidden_count=0)


@pytest.fixture
def host(qt_app):
    h = _FakeHost()
    yield h
    try:
        h.deleteLater()
    except RuntimeError:
        pass  # already gone
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()


def test_table_has_wps_header():
    from ui.tabs_scan import _table  # noqa: F401 -- import confirms module loads

    # Header text is set on the widget in _build_m4_tab(); verify the label
    # this test's host table would need lines up with tabs_scan.py's source.
    import inspect
    src = inspect.getsource(__import__("ui.tabs_scan", fromlist=["dummy"]))
    assert '"WPS?"' in src


def test_wps_enabled_network_shows_warning_in_table(host):
    host._on_m4_result(_wifi_result(wps_enabled=True))
    assert host._m4_table.rowCount() == 1
    wps_item = host._m4_table.item(0, 8)
    assert wps_item is not None
    assert "Yes" in wps_item.text()


def test_wps_disabled_network_shows_no_in_table(host):
    host._on_m4_result(_wifi_result(wps_enabled=False))
    assert host._m4_table.rowCount() == 1
    wps_item = host._m4_table.item(0, 8)
    assert wps_item is not None
    assert wps_item.text() == "No"

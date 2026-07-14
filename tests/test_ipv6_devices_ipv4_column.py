"""
Regression test for F-18 (claims-audit): the IPv6 Devices page's help text claims an
IPv4 column shown "side-by-side" with the IPv6 address, but the table only had
["IPv6 Address", "MAC Address", "State", "Source"] -- no IPv4 column existed anywhere.

Fix: _on_ipv6_result() (ui/scan_wiring.py) now cross-references each IPv6 neighbour's
MAC against the already-scanned self._m1_result devices to populate a new
"IPv4 Address" column, without requiring a second scan.
"""
from __future__ import annotations

import types

import pytest

try:
    from PyQt6.QtWidgets import QTableWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


class _FakeLabel:
    def setText(self, _text):
        pass


def _call_on_ipv6_result(m1_result, ipv6_devices):
    from ui.scan_wiring import ScanResultMixin

    obj = types.SimpleNamespace(
        _m1_result=m1_result,
        _ipv6_table=QTableWidget(0, 5),
        _ipv6_status=_FakeLabel(),
    )
    ScanResultMixin._on_ipv6_result(obj, ipv6_devices)
    return obj


def test_ipv6_table_has_ipv4_column_header():
    from ui.tabs_analysis import _AnalysisTabsMixin

    host = types.SimpleNamespace(_start_ipv6_scan=lambda: None)
    tab_widget = _AnalysisTabsMixin._build_ipv6_tab(host)  # noqa: F841 -- keeps QWidget (and its child table) alive
    headers = [host._ipv6_table.horizontalHeaderItem(c).text()
               for c in range(host._ipv6_table.columnCount())]
    assert "IPv4 Address" in headers


def test_ipv6_result_populates_ipv4_from_matching_mac():
    """This assertion fails before the fix — there was no IPv4 column to populate."""
    m1_result = {"devices": [
        {"mac": "AA:BB:CC:11:22:33", "ip": "192.168.1.42"},
    ]}
    ipv6_devices = [
        {"ip6": "fe80::1", "mac": "aa:bb:cc:11:22:33", "state": "REACHABLE", "source": "cache"},
    ]
    obj = _call_on_ipv6_result(m1_result, ipv6_devices)

    assert obj._ipv6_table.rowCount() == 1
    ipv4_col = 2
    assert obj._ipv6_table.item(0, ipv4_col).text() == "192.168.1.42"


def test_ipv6_result_shows_placeholder_when_mac_unmatched():
    obj = _call_on_ipv6_result(
        {"devices": []},
        [{"ip6": "fe80::2", "mac": "de:ad:be:ef:00:01", "state": "STALE", "source": "cache"}],
    )
    assert obj._ipv6_table.item(0, 2).text() == "—"

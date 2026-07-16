"""
Regression test for F-69 (claims-audit/BACKLOG): SNMP Device Info help text claimed
the poller queries "CPU load", but SNMPResult had no cpu_load field and the table had
no column for it.

Fix: modules/snmp_poller.py's poll() now populates SNMPResult.cpu_load (primary
HOST-RESOURCES-MIB OID, falling back to a Cisco vendor OID), and the SNMP Device Info
table (ui/tabs_monitors.py) + _on_snmp_result (ui/scan_wiring.py) surface it.
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


def test_snmp_table_has_cpu_load_column_header():
    from ui.tabs_monitors import _MonitorTabsMixin

    host = types.SimpleNamespace(
        _start_snmp_poll=lambda: None,
        _save_snmp_community=lambda: None,
        _on_snmp_table_selection=lambda: None,
        _start_snmp_if_poll=lambda: None,
    )
    _unused_tab_widget = _MonitorTabsMixin._build_snmp_tab(host)  # keeps QWidget (and its child table) alive
    headers = [host._snmp_table.horizontalHeaderItem(c).text()
               for c in range(host._snmp_table.columnCount())]
    assert "CPU Load" in headers


def test_on_snmp_result_populates_cpu_load_column():
    from modules.snmp_poller import SNMPResult
    from ui.scan_wiring import ScanResultMixin

    obj = types.SimpleNamespace(_snmp_table=QTableWidget(0, 7))
    result = SNMPResult(
        host="192.168.1.1", reachable=True, sys_name="router1",
        sys_descr="Linux router", sys_uptime="1h 2m 3s", if_count="4",
        cpu_load="17%", sys_contact="admin",
    )
    ScanResultMixin._on_snmp_result(obj, result)

    assert obj._snmp_table.rowCount() == 1
    cpu_col = 5
    assert obj._snmp_table.item(0, cpu_col).text() == "17%"


def test_on_snmp_result_unreachable_adds_no_row():
    from modules.snmp_poller import SNMPResult
    from ui.scan_wiring import ScanResultMixin

    obj = types.SimpleNamespace(_snmp_table=QTableWidget(0, 7))
    result = SNMPResult(host="192.168.1.2", reachable=False)
    ScanResultMixin._on_snmp_result(obj, result)

    assert obj._snmp_table.rowCount() == 0

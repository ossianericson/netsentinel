"""Behavioral test for ui/scan_wiring.py::_m1_stream_device_row (Part 2/L7).

Regression coverage for "a 715-device resolve produces nothing on screen for
minutes and then everything at once" — devices must be able to stream into
the Devices table live, appearing the instant an ARP entry is known and
updating in place (not duplicating a row) once the hostname resolves.
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QTableWidget
    from ui.scan_wiring import ScanResultMixin
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _Stub(ScanResultMixin):
    pass


def _make_stub() -> _Stub:
    stub = _Stub()
    stub._m1_table = QTableWidget(0, 9)
    return stub


def _cleanup(table: QTableWidget) -> None:
    from PyQt6.QtWidgets import QApplication
    try:
        table.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_stream_device_row_appends_new_row():
    stub = _make_stub()
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff", "vendor": "Acme"})
    assert stub._m1_table.rowCount() == 1
    assert stub._m1_table.item(0, 0).text() == "10.0.0.5"
    assert stub._m1_table.item(0, 2).text() == "aa:bb:cc:dd:ee:ff"
    _cleanup(stub._m1_table)


def test_stream_device_row_skeleton_shows_placeholder_hostname():
    stub = _make_stub()
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff"})
    assert stub._m1_table.item(0, 1).text() == "—"
    _cleanup(stub._m1_table)


def test_stream_device_row_updates_in_place_not_duplicated():
    """The critical behavior: a second call for the same IP must update the
    existing row (hostname fills in), not append a second row."""
    stub = _make_stub()
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff", "name": ""})
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:ff", "name": "printer-3f"})

    assert stub._m1_table.rowCount() == 1, "second call for the same IP must not add a row"
    assert stub._m1_table.item(0, 1).text() == "printer-3f"
    _cleanup(stub._m1_table)


def test_stream_device_row_multiple_ips_each_get_own_row():
    stub = _make_stub()
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:01"})
    stub._m1_stream_device_row({"ip": "10.0.0.6", "mac": "aa:bb:cc:dd:ee:02"})
    stub._m1_stream_device_row({"ip": "10.0.0.5", "mac": "aa:bb:cc:dd:ee:01", "name": "host-a"})

    assert stub._m1_table.rowCount() == 2
    ips = {stub._m1_table.item(r, 0).text() for r in range(2)}
    assert ips == {"10.0.0.5", "10.0.0.6"}
    _cleanup(stub._m1_table)


def test_stream_device_row_ignores_entries_with_no_ip():
    stub = _make_stub()
    stub._m1_stream_device_row({"ip": "", "mac": "aa:bb:cc:dd:ee:ff"})
    assert stub._m1_table.rowCount() == 0
    _cleanup(stub._m1_table)


def test_stream_device_row_high_risk_shows_risk_level():
    stub = _make_stub()
    stub._m1_stream_device_row({
        "ip": "10.0.0.9", "mac": "aa:bb:cc:dd:ee:ff",
        "risk_level": "HIGH", "verdict": "Rogue device detected",
    })
    assert stub._m1_table.item(0, 4).text() == "HIGH"
    assert stub._m1_table.item(0, 8).text() == "Rogue device detected"
    _cleanup(stub._m1_table)

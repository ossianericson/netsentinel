"""
Regression: Live Bandwidth rendered `entry.label or entry.mac` verbatim.

`entry.label` is filled in by BandwidthWorker from a label map built in
`_start_bandwidth_monitor()` out of the *current session's* scan result. With no
scan this session that map holds only this machine's own adapters, so every other
row showed a bare MAC — even for devices `known_device` already had a name for.
The row label is now resolved through DeviceLabelResolver at render time.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ui.tabs_monitors import _MonitorTabsMixin  # noqa: E402


class _FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def setRowCount(self, n) -> None:
        self.rows.clear()

    def rowCount(self) -> int:
        return len(self.rows)

    def insertRow(self, row) -> None:
        self.rows.append({})

    def setItem(self, row, col, item) -> None:
        self.rows[row][col] = item.text()


class _FakeStack:
    def setCurrentIndex(self, idx) -> None:
        pass


class _KD:
    def __init__(self, hostname=None, vendor=None, custom_name=None):
        self.hostname = hostname
        self.vendor = vendor
        self.custom_name = custom_name


class _FakeStore:
    def __init__(self, devices: dict):
        self._devices = devices

    def get_known_devices(self) -> dict:
        return dict(self._devices)


class _Host(_MonitorTabsMixin):
    """Minimal stand-in for the Dashboard the mixin normally lives on."""

    def __init__(self, store=None) -> None:
        self._store = store
        self._bw_table = _FakeTable()
        self._bw_stack = _FakeStack()
        self._bw_status = SimpleNamespace(setText=lambda _t: None)


def _snap(mac: str, label: str):
    return SimpleNamespace(
        window_s=5.0,
        entries=[SimpleNamespace(
            mac=mac, label=label,
            tx_bps=1000.0, rx_bps=2000.0, total_bps=3000.0, total_mbps=0.003,
        )],
    )


def test_row_uses_known_device_name_when_worker_had_no_label(monkeypatch):
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: None)
    host = _Host(store=_FakeStore({"00:22:61:d8:ee:58": _KD(hostname="Barnens-rum")}))

    host._on_bw_snapshot(_snap("00:22:61:d8:ee:58", ""))

    assert host._bw_table.rows[0][0] == "Barnens-rum"


def test_row_falls_back_to_oui_vendor_for_an_unscanned_mac(monkeypatch):
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: "TP-Link")
    host = _Host(store=_FakeStore({}))

    host._on_bw_snapshot(_snap("60:83:e7:88:a0:b1", "60:83:e7:88:a0:b1"))

    assert host._bw_table.rows[0][0] == "TP-Link"


def test_row_keeps_the_workers_label_when_nothing_resolves(monkeypatch):
    """A richer capture-time name (Deco client names) must not be discarded."""
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: None)
    host = _Host(store=_FakeStore({}))

    host._on_bw_snapshot(_snap("aa:bb:cc:dd:ee:ff", "This PC (DESKTOP-LN2HAJV)"))

    assert host._bw_table.rows[0][0] == "This PC (DESKTOP-LN2HAJV)"


def test_row_falls_back_to_the_mac_when_nothing_is_known(monkeypatch):
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: None)
    host = _Host(store=_FakeStore({}))

    host._on_bw_snapshot(_snap("de:ad:be:ef:ca:fe", ""))

    assert host._bw_table.rows[0][0] == "de:ad:be:ef:ca:fe"

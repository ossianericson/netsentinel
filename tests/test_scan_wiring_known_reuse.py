"""Regression tests for ui/scan_wiring.py known_device snapshot reuse (Phase B2 / F4).

_merge_scan_with_persistent() previously re-queried get_known_devices() on every
call. _on_m1_result() now reads the table once per scan cycle and threads that
snapshot down through _m1_refresh_segments_and_inventory ->
_merge_scan_with_persistent, _m1_populate_device_table, and _m1_track_devices ->
DeviceTracker.process_scan(). These tests cover _merge_scan_with_persistent
directly since it needs no QWidget/QApplication -- unlike its sibling steps, it
only touches self._store.
"""
from __future__ import annotations

import pytest

try:
    import PyQt6  # noqa: F401
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.metric_store_schema import KnownDevice
from ui.scan_wiring import ScanResultMixin


class _FakeStore:
    """Minimal store stub tracking how many times get_known_devices() is called."""

    def __init__(self, devices: dict):
        self._devices = devices
        self.get_known_devices_calls = 0

    def get_known_devices(self):
        self.get_known_devices_calls += 1
        return dict(self._devices)


class _Stub(ScanResultMixin):
    pass


def _pinned_printer() -> KnownDevice:
    return KnownDevice(
        mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.50", hostname="printer",
        vendor="HP", device_type="Printer", first_seen=1000, last_seen=1000,
        is_authorized=True, is_pinned=True,
    )


def test_merge_scan_with_persistent_reuses_supplied_known_snapshot():
    """A caller-supplied `known` snapshot must not trigger a second SELECT."""
    store = _FakeStore({"aa:bb:cc:dd:ee:ff": _pinned_printer()})
    snapshot = store.get_known_devices()  # the one read _on_m1_result would do
    assert store.get_known_devices_calls == 1

    stub = _Stub()
    stub._store = store

    result = stub._merge_scan_with_persistent([], known=snapshot)

    assert store.get_known_devices_calls == 1, (
        "_merge_scan_with_persistent(known=...) must reuse the supplied snapshot, "
        "not re-query get_known_devices()"
    )
    assert len(result) == 1
    assert result[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert result[0]["display_state"] == "pinned"


def test_merge_scan_with_persistent_falls_back_to_live_read_when_known_omitted():
    """Direct callers that don't supply `known` keep the pre-B2 self-fetch behaviour."""
    store = _FakeStore({"aa:bb:cc:dd:ee:ff": _pinned_printer()})

    stub = _Stub()
    stub._store = store

    result = stub._merge_scan_with_persistent([])

    assert store.get_known_devices_calls == 1
    assert len(result) == 1


def test_merge_scan_with_persistent_live_device_not_duplicated():
    """A device present in the live scan must not also appear as a pinned extra."""
    store = _FakeStore({"aa:bb:cc:dd:ee:ff": _pinned_printer()})
    snapshot = store.get_known_devices()

    stub = _Stub()
    stub._store = store

    live = [{"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.50"}]
    result = stub._merge_scan_with_persistent(live, known=snapshot)

    assert result == live  # no pinned "extra" appended for an already-live MAC

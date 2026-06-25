"""Tests for ui/widgets/scan_radar_widget.py — ScanRadarWidget."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture()
def radar_widget(qt_app):
    from ui.widgets.scan_radar_widget import ScanRadarWidget
    w = ScanRadarWidget()
    yield w
    try:
        if hasattr(w, "_tick_timer"):
            w._tick_timer.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # widget may already be closed by Qt
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.widgets.scan_radar_widget import ScanRadarWidget  # noqa: F401


def test_initial_state(radar_widget):
    assert not radar_widget._tick_timer.isActive()
    assert radar_widget._devices == []
    assert radar_widget._sweep_angle == 0.0


def test_start_activates_timer(radar_widget):
    radar_widget.start()
    assert radar_widget._tick_timer.isActive()
    radar_widget.stop()


def test_stop_deactivates_timer(radar_widget):
    radar_widget.start()
    radar_widget.stop()
    assert not radar_widget._tick_timer.isActive()


def test_start_resets_state(radar_widget):
    # start() must reset sweep angle and tick count; _devices stays empty (add_device is no-op)
    radar_widget.start()
    assert radar_widget._sweep_angle == 0.0
    assert radar_widget._tick_count == 0
    assert radar_widget._devices == []
    radar_widget.stop()


def test_add_device_is_noop(radar_widget):
    # add_device() is a pure no-op; _devices must remain empty after any call
    radar_widget.add_device("192.168.1.5", "Router", "router")
    assert radar_widget._devices == []


def test_add_multiple_devices_noop(radar_widget):
    # multiple calls to add_device() must not populate _devices
    radar_widget.add_device("192.168.1.1", "Gateway", "router")
    radar_widget.add_device("192.168.1.10", "Laptop", "laptop")
    radar_widget.add_device("192.168.1.20", "Phone", "mobile")
    assert radar_widget._devices == []


def test_add_device_accepts_optional_args(radar_widget):
    # add_device() must accept call with only ip (no optional args) without raising
    radar_widget.add_device("10.0.0.1")
    assert radar_widget._devices == []


def test_stop_clears_widget(radar_widget):
    # Regression test for the green-blob bug: stop() must clear _devices and stop the timer
    radar_widget.start()
    radar_widget.stop()
    assert not radar_widget._tick_timer.isActive()
    assert radar_widget._devices == []


def test_minimum_size(radar_widget):
    assert radar_widget.minimumWidth() >= 300
    assert radar_widget.minimumHeight() >= 300

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


def test_start_clears_devices(radar_widget):
    radar_widget.add_device("192.168.1.1", "Router", "router")
    assert len(radar_widget._devices) == 1
    radar_widget.start()
    assert radar_widget._devices == []
    radar_widget.stop()


def test_add_device(radar_widget):
    radar_widget.add_device("192.168.1.5", "Router", "router")
    assert len(radar_widget._devices) == 1
    dev = radar_widget._devices[0]
    assert dev["ip"] == "192.168.1.5"
    assert dev["name"] == "Router"
    assert dev["type"] == "router"


def test_add_multiple_devices(radar_widget):
    radar_widget.add_device("192.168.1.1", "Gateway", "router")
    radar_widget.add_device("192.168.1.10", "Laptop", "laptop")
    radar_widget.add_device("192.168.1.20", "Phone", "mobile")
    assert len(radar_widget._devices) == 3


def test_add_device_ip_fallback_for_empty_name(radar_widget):
    radar_widget.add_device("10.0.0.1")
    assert radar_widget._devices[0]["name"] == "10.0.0.1"


def test_device_position_is_deterministic(radar_widget):
    radar_widget.add_device("192.168.1.100", "A", "pc")
    radar_widget.add_device("192.168.1.100", "B", "pc")
    # Same IP → same azimuth and ring
    assert radar_widget._devices[0]["azimuth"] == radar_widget._devices[1]["azimuth"]
    assert radar_widget._devices[0]["ring"] == radar_widget._devices[1]["ring"]


def test_minimum_size(radar_widget):
    assert radar_widget.minimumWidth() >= 300
    assert radar_widget.minimumHeight() >= 300

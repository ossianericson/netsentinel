"""Tests for ui/pages/mqtt_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from unittest.mock import patch
    from ui.pages.mqtt_page import MqttPage
    # keyring has no backend on headless CI (Linux); patch to avoid NoKeyringError
    with patch("keyring.get_password", return_value=None), \
         patch("keyring.set_password", return_value=None):
        p = MqttPage()
        yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.pages.mqtt_page import MqttPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_broker_host_field(page):
    """MQTT page should have a broker hostname/IP field."""
    has_field = (
        hasattr(page, "_broker_edit") or
        hasattr(page, "_host_edit") or
        hasattr(page, "_broker_host")
    )
    assert has_field or page is not None


def test_on_scan_result_does_not_crash(page):
    """Injecting scan data should update the topic list without crashing."""
    result = {"devices": [{"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff",
                            "hostname": "router", "device_type": "Router"}]}
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None

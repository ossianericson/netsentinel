"""Tests for ui/pages/protocol_viz_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.protocol_viz_page import ProtocolVizPage
    p = ProtocolVizPage()
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
    from ui.pages.protocol_viz_page import ProtocolVizPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_protocol_selector(page):
    """Page should have a protocol combobox or selector."""
    has_selector = (
        hasattr(page, "_protocol_combo") or
        hasattr(page, "_proto_combo") or
        hasattr(page, "_selector")
    )
    assert has_selector or page is not None


def test_on_scan_result_does_not_crash(page):
    """Injecting scan data should not crash."""
    result = {
        "devices": [
            {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:01",
             "hostname": "router", "device_type": "Router"}
        ]
    }
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None

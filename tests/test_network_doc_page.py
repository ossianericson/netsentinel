"""Tests for ui/pages/network_doc_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.network_doc_page import NetworkDocPage
    p = NetworkDocPage()
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
    from ui.pages.network_doc_page import NetworkDocPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_scan_requested_signal(page):
    assert hasattr(page, "scan_requested")


def test_on_scan_result_does_not_crash(page):
    """Injecting scan data should not crash."""
    result = {
        "devices": [
            {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:01",
             "hostname": "router", "device_type": "Router", "risk": "CLEAN"}
        ]
    }
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None

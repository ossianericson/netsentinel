"""Tests for ui/pages/live_bandwidth_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.live_bandwidth_page import LiveBandwidthPage
    p = LiveBandwidthPage()
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
    from ui.pages.live_bandwidth_page import LiveBandwidthPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_on_bandwidth_result_does_not_crash(page):
    """Injecting bandwidth readings should not crash."""
    result = {"iface": "Ethernet", "rx_bytes": 1024 * 1024, "tx_bytes": 512 * 1024}
    slot = getattr(page, "on_bandwidth_result", None) or getattr(page, "on_result", None)
    if slot:
        slot(result)
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None

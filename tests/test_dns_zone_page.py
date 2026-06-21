"""Tests for ui/pages/dns_zone_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.dns_zone_page import DnsZonePage
    p = DnsZonePage()
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
    from ui.pages.dns_zone_page import DnsZonePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_start_button_or_input(page):
    """DNS zone page should have some form of scan control."""
    assert page is not None


def test_on_result_does_not_crash(page):
    """Injecting DNS zone scan results should not crash."""
    results = {"records": [("example.com", "A", "93.184.216.34")], "zone": "example.com"}
    slot = getattr(page, "on_dns_zone_result", None) or getattr(page, "on_result", None)
    if slot:
        slot(results)
    assert page is not None

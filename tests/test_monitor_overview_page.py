"""Tests for ui/pages/monitor_overview_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.monitor_overview_page import MonitorOverviewPage
    p = MonitorOverviewPage()
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
    from ui.pages.monitor_overview_page import MonitorOverviewPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None


def test_refresh_does_not_crash(page):
    """Refreshing the overview should not crash with empty store."""
    refresh = getattr(page, "refresh", None) or getattr(page, "_refresh", None)
    if refresh:
        refresh()
    assert page is not None

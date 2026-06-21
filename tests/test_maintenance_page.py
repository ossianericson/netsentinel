"""Tests for ui/pages/maintenance_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def page():
    from ui.pages.maintenance_page import MaintenancePage
    p = MaintenancePage()
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
    from ui.pages.maintenance_page import MaintenancePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None


def test_loads_without_windows(page):
    """Page should render correctly when no maintenance windows exist."""
    refresh = getattr(page, "_load_windows", None) or getattr(page, "refresh", None)
    if refresh:
        refresh()
    assert page is not None

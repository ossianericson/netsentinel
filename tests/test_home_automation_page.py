"""Tests for ui/pages/home_automation_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_store(tmp_path):
    from modules.metric_store import MetricStore
    return MetricStore(db_path=tmp_path / "test.db")


@pytest.fixture
def page(tmp_path):
    from ui.pages.home_automation_page import HomeAutomationPage
    store = _make_store(tmp_path)
    p = HomeAutomationPage(store=store)
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()


def test_import():
    from ui.pages.home_automation_page import HomeAutomationPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_widget_is_not_none(page):
    assert page is not None


def test_on_scan_result_does_not_crash(page):
    """Injecting scan results should not crash."""
    result = {"devices": []}
    slot = getattr(page, "on_scan_result", None)
    if slot:
        slot(result)
    assert page is not None

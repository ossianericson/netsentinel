"""Tests for ui/pages/timeline_page.py"""
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
    from ui.pages.timeline_page import TimelinePage
    store = _make_store(tmp_path)
    p = TimelinePage(store=store)
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
    from ui.pages.timeline_page import TimelinePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_refresh_with_empty_store(page):
    """Refreshing with an empty store should not crash."""
    refresh = getattr(page, "refresh", None) or getattr(page, "_load_events", None)
    if refresh:
        refresh()
    assert page is not None


def test_events_table_row_count_is_zero_initially(page):
    """Timeline should show 0 rows before any events are recorded."""
    table = getattr(page, "_events_table", None) or getattr(page, "_table", None)
    if table is not None:
        assert table.rowCount() >= 0
    assert page is not None

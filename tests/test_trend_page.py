"""Tests for ui/pages/trend_page.py"""
from __future__ import annotations

import time

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
    from ui.pages.trend_page import TrendPage
    store = _make_store(tmp_path)
    p = TrendPage(store=store)
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
    from ui.pages.trend_page import TrendPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_scan_requested_signal(page):
    assert hasattr(page, "scan_requested")


def test_refresh_with_rtt_data(tmp_path):
    """Trend page should render without error when RTT data is available."""
    from modules.metric_store import MetricStore
    from ui.pages.trend_page import TrendPage
    store = MetricStore(db_path=tmp_path / "trend.db")
    ts = int(time.time())
    for i in range(5):
        store.record_rtt("8.8.8.8", ts + i * 60, 20.0 + i, 0.0)
    p = TrendPage(store=store)
    refresh = getattr(p, "refresh", None) or getattr(p, "_load_data", None)
    if refresh:
        refresh()
    assert p is not None
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()

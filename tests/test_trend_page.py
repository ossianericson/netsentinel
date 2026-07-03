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


def test_rtt_headline_hidden_with_no_data(page):
    """Stability Sprint 2 (G11): _update_rtt_headline() now reads a single
    SQL aggregate (query_rtt_weekly_avg()) instead of scanning every host's
    raw RTT history on the main thread."""
    page._update_rtt_headline()
    assert page._headline_lbl.isHidden() is True


def test_rtt_headline_shows_this_week_average(tmp_path):
    from modules.metric_store import MetricStore
    from ui.pages.trend_page import TrendPage
    store = MetricStore(db_path=tmp_path / "trend2.db")
    now = int(time.time())
    store.record_rtt("8.8.8.8", 10.0, ts=now - 3600)
    store.record_rtt("8.8.8.8", 20.0, ts=now - 7200)
    p = TrendPage(store=store)
    p._update_rtt_headline()
    assert p._headline_lbl.isHidden() is False
    assert "15" in p._headline_lbl.text()
    p.deleteLater()
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()


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

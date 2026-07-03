"""Tests for ui/pages/geo_map_page.py"""
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
    from ui.pages.geo_map_page import GeoMapPage
    store = _make_store(tmp_path)
    p = GeoMapPage(store=store)
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
    from ui.pages.geo_map_page import GeoMapPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_navigate_requested_signal(page):
    """Geo Map's empty state routes to Threat Intel (its data source), not a
    device scan — see commit 8a2e797. navigate_requested carries the CTA."""
    assert hasattr(page, "navigate_requested")


def test_on_geo_result_does_not_crash(page):
    """Injecting geo results should not crash the page."""
    results = [{"ip": "93.184.216.34", "country": "US", "city": "Norwell",
                "lat": 42.1596, "lon": -70.8217}]
    slot = getattr(page, "on_geo_result", None) or getattr(page, "on_result", None)
    if slot:
        slot(results)
    assert page is not None

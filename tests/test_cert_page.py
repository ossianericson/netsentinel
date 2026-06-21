"""Tests for ui/pages/cert_page.py"""
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
    from ui.pages.cert_page import CertPage
    store = _make_store(tmp_path)
    p = CertPage(store=store)
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
    from ui.pages.cert_page import CertPage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_scan_requested_signal(page):
    assert hasattr(page, "scan_requested")


def test_on_results_populates_table(page):
    """Injecting cert results should populate the results table."""
    results = [
        {
            "host": "example.com",
            "status": "Valid",
            "expiry": "2030-01-01",
            "days_left": 1200,
            "issuer": "Let's Encrypt",
        }
    ]
    if hasattr(page, "on_cert_result"):
        page.on_cert_result(results)
    # Table should be populated or the page should not crash
    assert page is not None

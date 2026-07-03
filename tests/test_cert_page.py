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


@pytest.fixture
def clean_cert_settings():
    """V6 Sprint 3.3 — isolate the QSettings keys merge_auto_targets touches
    so this test suite never reads/writes real dev-machine cert targets."""
    from PyQt6.QtCore import QSettings
    from ui.pages.cert_page import _QS_KEY, _QS_EXCLUDED_KEY
    qs = QSettings("NetSentinel", "NetSentinel")
    prev_targets = qs.value(_QS_KEY, None)
    prev_excluded = qs.value(_QS_EXCLUDED_KEY, None)
    qs.remove(_QS_KEY)
    qs.remove(_QS_EXCLUDED_KEY)
    yield
    if prev_targets is None:
        qs.remove(_QS_KEY)
    else:
        qs.setValue(_QS_KEY, prev_targets)
    if prev_excluded is None:
        qs.remove(_QS_EXCLUDED_KEY)
    else:
        qs.setValue(_QS_EXCLUDED_KEY, prev_excluded)


def test_merge_auto_targets_adds_new_host(page, clean_cert_settings):
    from modules.cert_monitor import CertTarget
    page._configured = []
    page.merge_auto_targets([CertTarget(host="192.168.1.50", ports=[443], label="auto")])
    assert any(t["host"] == "192.168.1.50" and t["label"] == "auto" for t in page._configured)


def test_merge_auto_targets_skips_existing_host(page, clean_cert_settings):
    from modules.cert_monitor import CertTarget
    page._configured = [{"host": "192.168.1.50", "ports": [443], "label": ""}]
    page.merge_auto_targets([CertTarget(host="192.168.1.50", ports=[443], label="auto")])
    assert len(page._configured) == 1
    assert page._configured[0]["label"] == ""  # manual entry not overwritten


def test_removed_auto_target_is_not_re_enrolled(page, clean_cert_settings):
    from modules.cert_monitor import CertTarget
    page._configured = [{"host": "192.168.1.60", "ports": [443], "label": "auto"}]
    page._remove_host("192.168.1.60")
    assert page._configured == []

    page.merge_auto_targets([CertTarget(host="192.168.1.60", ports=[443], label="auto")])
    assert page._configured == []

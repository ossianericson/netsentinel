"""Tests for ui/pages/lab_mode_page.py"""
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
    from ui.pages.lab_mode_page import LabModePage
    store = _make_store(tmp_path)
    p = LabModePage(store=store)
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
    from ui.pages.lab_mode_page import LabModePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_inject_live_challenge(page):
    """Lab mode page must expose inject_live_challenge() for the Logger integration."""
    assert hasattr(page, "inject_live_challenge")
    assert callable(page.inject_live_challenge)


def test_inject_live_challenge_is_callable(page):
    """inject_live_challenge() must exist and be callable (Lab Mode ↔ Logger contract)."""
    assert callable(page.inject_live_challenge)

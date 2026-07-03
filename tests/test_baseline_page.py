"""Tests for ui/pages/baseline_page.py"""
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
    from ui.pages.baseline_page import BaselinePage
    store = _make_store(tmp_path)
    p = BaselinePage(store=store)
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
    from ui.pages.baseline_page import BaselinePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_has_scan_requested_signal(page):
    assert hasattr(page, "scan_requested")


def test_widget_is_visible_after_creation(page):
    assert page is not None


# ── V6 Sprint 4.3: blessed baseline (config-drift auto-diff target) ─────────

def test_blessed_snapshot_id_defaults_to_zero():
    from PyQt6.QtCore import QSettings
    from ui.pages.baseline_page import _blessed_snapshot_id, _BLESSED_KEY
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove(_BLESSED_KEY)
    try:
        assert _blessed_snapshot_id() == 0
    finally:
        qs.remove(_BLESSED_KEY)


def test_bless_selected_snapshot_persists_id_and_marks_row(page):
    from PyQt6.QtCore import QSettings
    from ui.pages.baseline_page import _blessed_snapshot_id, _BLESSED_KEY
    from modules.config_baseline import build_snapshot_from_scan, store_snapshot

    snap = build_snapshot_from_scan([{"ip": "192.168.1.10"}], label="Baseline snap")
    store_snapshot(page._store, snap)
    page._load_snapshots()
    page._snap_table.setCurrentCell(0, 0)

    qs = QSettings("NetSentinel", "NetSentinel")
    try:
        page._bless_selected_snapshot()
        assert _blessed_snapshot_id() == page._snapshots[0].id
        assert page._snap_table.item(0, 1).text().startswith("★")
    finally:
        qs.remove(_BLESSED_KEY)

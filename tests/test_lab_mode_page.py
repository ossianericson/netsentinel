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


def test_download_badge_button_exists(page):
    assert hasattr(page, "_badge_btn")
    assert page._badge_btn.text() == "Download Badge (PNG)"


def test_download_badge_writes_png(page, monkeypatch, tmp_path):
    """Clicking Download Badge renders a PNG for the last completed LabResult."""
    page._result_data = {
        "scenario_id": "arp_spoof_1",
        "scenario_title": "ARP Cache Poisoning Detective",
        "completed_at": "2026-07-03 14:22:00",
    }
    out_path = tmp_path / "badge.png"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )
    page._download_badge()
    assert out_path.exists()


def test_download_badge_noop_when_dialog_cancelled(page, monkeypatch, tmp_path):
    page._result_data = {
        "scenario_id": "arp_spoof_1",
        "scenario_title": "ARP Cache Poisoning Detective",
        "completed_at": "2026-07-03 14:22:00",
    }
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: ("", ""),
    )
    page._download_badge()  # must not raise


def test_download_badge_noop_when_no_result(page, monkeypatch, tmp_path):
    out_path = tmp_path / "badge.png"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )
    page._download_badge()  # no _result_data yet — must not raise or write
    assert not out_path.exists()

"""
Tests for ui/pages/inventory_page.py — Sprint 5 device intelligence additions.

Covers:
  • S5-2: Room/Owner group pill bar appears once a device has an annotation
  • S5-3: Health summary top-line reflects device risk/offline state
  • S5-1: open_device_drawer() prefills the suggested label when none is saved
  • S5-6: device drawer timeline section renders without error
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.device_tracker import save_annotations
from modules.metric_store import MetricStore
from ui.pages.inventory_page import InventoryPage

_created_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_pages():
    yield
    app = QApplication.instance()
    for page in _created_pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal
        for _ in range(3):
            app.processEvents()
    _created_pages.clear()


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_page(store=None) -> InventoryPage:
    page = InventoryPage(store=store)
    _created_pages.append(page)
    return page


def _dev(mac, ip, risk_level="CLEAN", display_state=""):
    return {
        "mac": mac, "ip": ip, "hostname": "", "vendor": "Apple",
        "device_type": "Laptop", "risk_level": risk_level,
        "confidence": 0.9, "is_gateway": False, "display_state": display_state,
        "last_seen_ts": 0,
    }


def test_constructs_without_store():
    page = _make_page(None)
    assert page is not None


def test_health_summary_all_healthy(store):
    page = _make_page(store)
    page.set_scan_devices([_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert not page._health_summary_lbl.isHidden()
    assert "healthy" in page._health_summary_lbl.text().lower()


def test_health_summary_flags_unusual_device(store):
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11", risk_level="HIGH"),
    ])
    assert "1 of your 2 devices" in page._health_summary_lbl.text()


def test_group_bar_hidden_with_no_annotations(store):
    page = _make_page(store)
    page.set_scan_devices([_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert page._group_bar_frame.isHidden()


def test_group_bar_shows_room_pills_once_annotated(store):
    save_annotations("aa:bb:cc:00:00:01", store, location="Living Room")
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    assert not page._group_bar_frame.isHidden()
    assert "Living Room" in page._group_pills
    assert "Unassigned" in page._group_pills


def test_toggle_group_hides_non_matching_rows(store):
    save_annotations("aa:bb:cc:00:00:01", store, location="Living Room")
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    page._toggle_group("Living Room")
    hidden_states = [page._snap_table.isRowHidden(r) for r in range(page._snap_table.rowCount())]
    assert hidden_states.count(True) == 1


def test_open_device_drawer_prefills_suggested_label(store):
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01", suggested_label="Sony Smart TV")
    assert page._device_drawer._ann_label.text() == "Sony Smart TV"


def test_open_device_drawer_keeps_existing_label(store):
    save_annotations("aa:bb:cc:00:00:01", store, user_label="My TV")
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01", suggested_label="Sony Smart TV")
    assert page._device_drawer._ann_label.text() == "My TV"


def test_drawer_timeline_renders_without_events(store):
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01")
    assert page._device_drawer._timeline_body.count() >= 1


def test_drawer_timeline_includes_join_event(store):
    store.record_device_event(ip="192.168.1.10", event_type="JOINED", mac="aa:bb:cc:00:00:01")
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01")
    texts = []
    for i in range(page._device_drawer._timeline_body.count()):
        w = page._device_drawer._timeline_body.itemAt(i).widget()
        if w:
            texts.append(w.text())
    assert any("JOINED" in t for t in texts)

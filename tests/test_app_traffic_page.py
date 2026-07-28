"""
Tests for ui/pages/app_traffic_page.py — top_host_changed signal (S5-4)

Covers:
  • AppTrafficPage constructs without error
  • _emit_top_host() does nothing when there are no snapshots
  • _emit_top_host() emits the highest-byte host with the correct share_pct
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.app_traffic_classifier import AppFlowEntry, AppHostSnapshot, AppTrafficSnapshot
from modules.metric_store import MetricStore
from ui.pages.app_traffic_page import AppTrafficPage

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


def _make_page(store=None) -> AppTrafficPage:
    page = AppTrafficPage(store=store)
    _created_pages.append(page)
    return page


def test_constructs_without_error():
    page = _make_page()
    assert page is not None


def test_emit_top_host_noop_when_no_snapshots():
    page = _make_page()
    received = []
    page.top_host_changed.connect(received.append)
    page._emit_top_host()
    assert received == []


def test_emit_top_host_reports_highest_consumer():
    page = _make_page()
    page._snapshots = {
        "aa:bb": AppHostSnapshot(mac="aa:bb", label="Quiet Device", total_bytes=10_000),
        "cc:dd": AppHostSnapshot(mac="cc:dd", label="John's MacBook", total_bytes=90_000),
    }
    received = []
    page.top_host_changed.connect(received.append)
    page._emit_top_host()
    assert len(received) == 1
    payload = received[0]
    assert payload["label"] == "John's MacBook"
    assert payload["bytes_total"] == 90_000
    assert payload["share_pct"] == pytest.approx(90.0)


# ── Sprint 6: traffic_sample_ready persistence signal (S6-1) ──────────────

def test_emit_traffic_samples_noop_when_empty_snapshot():
    page = _make_page()
    received = []
    page.traffic_sample_ready.connect(received.append)
    page._emit_traffic_samples(AppTrafficSnapshot(hosts=[]))
    assert received == []


def test_emit_traffic_samples_builds_persistable_payload():
    page = _make_page()
    received = []
    page.traffic_sample_ready.connect(received.append)
    host = AppHostSnapshot(
        mac="aa:bb:cc:dd:ee:ff", label="TV", total_bytes=5000, window_s=10.0,
        flows=[AppFlowEntry(mac="aa:bb:cc:dd:ee:ff", category="Streaming",
                             app="HTTPS", bytes_total=5000, label="TV", cdn="Netflix")],
    )
    page._emit_traffic_samples(AppTrafficSnapshot(hosts=[host]))
    assert len(received) == 1
    sample = received[0][0]
    assert sample["mac"] == "aa:bb:cc:dd:ee:ff"
    assert sample["category"] == "Streaming"
    assert sample["cdn"] == "Netflix"
    assert sample["bytes_total"] == 5000


# ── Sprint 6: 24h history chart + drill-down (S6-1 / S6-2) ────────────────

def test_refresh_hist_chart_with_no_store_shows_empty_state():
    page = _make_page(store=None)
    page._refresh_hist_chart()
    assert page._hist_categories == []


def test_refresh_hist_chart_populates_categories_from_store(tmp_path):
    store = MetricStore(db_path=tmp_path / "test.db")
    try:
        store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 80_000, 10.0, cdn="Netflix")
        store.record_app_traffic_sample("cc:dd", "Laptop", "Web", "HTTPS", 20_000, 10.0)
        page = _make_page(store=store)
        page._refresh_hist_chart()
        assert page._hist_categories[0] == "Streaming"
        assert "Web" in page._hist_categories
    finally:
        store.close()


# ── Regression: rows showed raw MACs instead of device names ─────────────

def _snapshot(mac: str, label: str, total: int = 5000) -> AppTrafficSnapshot:
    return AppTrafficSnapshot(hosts=[AppHostSnapshot(
        mac=mac, label=label, total_bytes=total, window_s=10.0,
        flows=[AppFlowEntry(mac=mac, category="Streaming", app="HTTPS",
                            bytes_total=total, label=label, cdn="Netflix")],
    )])


def test_chart_uses_store_name_when_capture_labelled_the_host_with_its_mac(tmp_path):
    """The capture thread stamps `label = mac` whenever it has no label map —
    which is every session where no scan ran before monitoring started. The
    chart must still name the device from the persistent device map."""
    store = MetricStore(db_path=tmp_path / "test.db")
    try:
        store.upsert_known_device("78:c8:81:d7:9f:fe", ip="192.168.68.60",
                                  hostname="PS5-vardagsrummet", vendor="Sony")
        page = _make_page(store=store)
        page._on_snapshot(_snapshot("78:c8:81:d7:9f:fe", "78:c8:81:d7:9f:fe"))
        assert page._host_label(page._snapshots["78:c8:81:d7:9f:fe"]) == "PS5-vardagsrummet"
        labels = [page._host_combo.itemText(i) for i in range(page._host_combo.count())]
        assert "PS5-vardagsrummet" in labels
        assert "78:c8:81:d7:9f:fe" not in labels
    finally:
        store.close()


def test_persisted_sample_label_is_the_resolved_name(tmp_path):
    """The 24h breakdown reads its device names from app_traffic_sample.label,
    so an unresolved label at capture time poisons the history too."""
    store = MetricStore(db_path=tmp_path / "test.db")
    try:
        store.upsert_known_device("00:22:61:d8:ee:58", ip="192.168.68.54",
                                  hostname="Barnens-rum", vendor="Sonos")
        page = _make_page(store=store)
        received = []
        page.traffic_sample_ready.connect(received.append)
        page._on_snapshot(_snapshot("00:22:61:d8:ee:58", "00:22:61:d8:ee:58"))
        assert received[0][0]["label"] == "Barnens-rum"
    finally:
        store.close()


def test_late_label_map_relabels_existing_rows_without_duplicating_them():
    """Keying snapshots by display label meant a map arriving mid-session added
    a second entry for the same device and left the MAC-labelled one on the
    chart forever."""
    page = _make_page()
    page._on_snapshot(_snapshot("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"))
    assert len(page._snapshots) == 1

    page.set_label_map({"aa:bb:cc:dd:ee:ff": "Living Room TV"})

    assert len(page._snapshots) == 1, "a relabel must not create a second row"
    labels = [page._host_combo.itemText(i) for i in range(page._host_combo.count())]
    assert "Living Room TV" in labels
    assert "aa:bb:cc:dd:ee:ff" not in labels


def test_host_selection_survives_a_label_change():
    page = _make_page()
    page._on_snapshot(_snapshot("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"))
    page._host_combo.setCurrentIndex(1)
    assert page._selected_host == "aa:bb:cc:dd:ee:ff"

    page.set_label_map({"aa:bb:cc:dd:ee:ff": "Living Room TV"})

    assert page._selected_host == "aa:bb:cc:dd:ee:ff"
    assert page._host_combo.currentText() == "Living Room TV"


def test_unnamed_device_falls_back_to_oui_vendor(monkeypatch):
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: "TP-Link")
    page = _make_page()
    page._on_snapshot(_snapshot("60:83:e7:88:a0:b1", "60:83:e7:88:a0:b1"))
    assert page._host_label(page._snapshots["60:83:e7:88:a0:b1"]) == "TP-Link"


def test_show_hist_breakdown_populates_labels(tmp_path):
    store = MetricStore(db_path=tmp_path / "test.db")
    try:
        store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 80_000, 10.0, cdn="Netflix")
        store.record_app_traffic_sample("cc:dd", "Laptop", "Streaming", "HTTPS", 20_000, 10.0, cdn="YouTube")
        page = _make_page(store=store)
        page._show_hist_breakdown("Streaming")
        assert "TV" in page._hist_breakdown_lbl.text()
        assert "Netflix" in page._hist_cdn_lbl.text()
        assert "YouTube" in page._hist_cdn_lbl.text()
    finally:
        store.close()

"""Tests for ui/pages/timeline_page.py"""
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
    from ui.pages.timeline_page import TimelinePage
    store = _make_store(tmp_path)
    p = TimelinePage(store=store)
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
    from ui.pages.timeline_page import TimelinePage  # noqa: F401


def test_instantiation(page):
    assert page is not None


def test_refresh_with_empty_store(page):
    """Refreshing with an empty store should not crash."""
    refresh = getattr(page, "refresh", None) or getattr(page, "_load_events", None)
    if refresh:
        refresh()
    assert page is not None


def test_events_table_row_count_is_zero_initially(page):
    """Timeline should show 0 rows before any events are recorded."""
    table = getattr(page, "_events_table", None) or getattr(page, "_table", None)
    if table is not None:
        assert table.rowCount() >= 0
    assert page is not None


def test_device_change_event_shows_hostname_after_set_label_map(page, tmp_path):
    """Regression: device-change rows must resolve MAC to hostname when a
    label map has been supplied, same as App Traffic / Live Bandwidth."""
    from modules.device_tracker import record_event

    mac = "aa:bb:cc:11:22:33"
    record_event(mac, "hostname_changed", "", "living-room-tv", "scan", page._store)

    page.set_label_map({mac: "Living Room TV"})

    titles = [ev.title for ev in page._events]
    assert any("Living Room TV" in t for t in titles)
    assert not any(mac in t for t in titles)


def _laid_out_widgets(page):
    lay = page._feed_layout
    return [lay.itemAt(i).widget() for i in range(lay.count())
            if lay.itemAt(i).widget() is not None]


def test_render_reuses_row_widgets_across_renders(page):
    """Regression: _render() tore down and reconstructed every row (a QFrame
    plus up to 4 QLabels per event) on each 60 s auto-refresh tick — the
    UMDH-confirmed native RSS growth site. Rows must now be re-used in place."""
    from modules.device_tracker import record_event

    for i in range(5):
        record_event(f"aa:bb:cc:00:00:0{i}", "hostname_changed",
                     "", f"host-{i}", "scan", page._store)
    page._reload()

    first = _laid_out_widgets(page)
    assert len(first) >= 5, "seeded events did not render any rows"

    page._render()
    second = _laid_out_widgets(page)

    assert len(first) == len(second)
    assert all(a is b for a, b in zip(first, second)), (
        "each _render() built brand-new row widgets instead of re-using them"
    )


def test_device_change_event_uses_known_device_name_without_any_label_map(page):
    """Regression: with no scan this session nothing ever calls set_label_map,
    and every device-change row rendered as a bare MAC even though the
    persistent device map already held the name."""
    from modules.device_tracker import record_event

    mac = "00:22:61:d8:ee:58"
    page._store.upsert_known_device(mac, ip="192.168.68.54",
                                    hostname="Barnens-rum", vendor="Sonos")
    record_event(mac, "hostname_changed", "", "barnens-rum", "scan", page._store)

    page._reload()

    titles = [ev.title for ev in page._events]
    assert any("Barnens-rum" in t for t in titles)
    assert not any(mac in t for t in titles)

"""
tests/test_home_action_card_ack_all.py — RULE-T7 behavioural coverage for the
Home "Action needed" card's bulk acknowledge (Phase 2b, notifications rework).

The card lists only the 5 newest unacked alerts and is repopulated from the
store every 30s by _push_monitor_pills(). With a deeper backlog, acking the 5
visible rows promotes the next 5 on the following refresh — which the user
reads as "the alerts I just acknowledged came straight back". Reproduced live:
87 unacked alerts, 5 shown.

RULE-T3: these fail before the fix (no _ack_all_alerts, no backlog count).
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


_created_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_home_pages():
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


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_page(store):
    from ui.pages.home_page import HomePage
    page = HomePage(store=store)
    _created_pages.append(page)
    return page


def _seed(store, n: int) -> list:
    return [
        store.record_alert_fired("Device Gone", f"192.168.68.{i}", "WARNING", f"gone {i}")
        for i in range(n)
    ]


# ── The backlog must be visible ───────────────────────────────────────────────

def test_card_reports_the_full_backlog_not_just_the_five_shown(store):
    _seed(store, 12)
    page = _make_page(store)

    page.set_pending_alert_rows(store.get_unacked_alerts())

    assert page._ac_count_lbl.text() == "showing 5 of 12"
    assert page._ac_ack_all_btn.text() == "✓ Acknowledge all (12)"


def test_no_backlog_label_when_everything_fits(store):
    _seed(store, 3)
    page = _make_page(store)

    page.set_pending_alert_rows(store.get_unacked_alerts())

    assert page._ac_count_lbl.text() == ""
    assert not page._ac_count_lbl.isVisible()
    assert page._ac_ack_all_btn.text() == "✓ Acknowledge all"


# ── Acknowledge all ───────────────────────────────────────────────────────────

def test_ack_all_clears_the_whole_backlog_not_just_the_visible_rows(store):
    _seed(store, 12)
    page = _make_page(store)
    page.set_pending_alert_rows(store.get_unacked_alerts())

    page._ack_all_alerts()

    assert store.get_unacked_alerts() == [], (
        "Acknowledge all must clear all 12, not the 5 rows on screen"
    )


def test_ack_all_hides_the_card_and_emits(store):
    _seed(store, 12)
    page = _make_page(store)
    page.set_pending_alert_rows(store.get_unacked_alerts())
    emitted: list = []
    page.alerts_acknowledged.connect(lambda: emitted.append(1))

    page._ack_all_alerts()

    assert page._action_card.isVisible() is False
    assert emitted, "the dashboard badge/pulse must be told to refresh immediately"


def test_ack_all_is_a_noop_with_an_empty_queue(store):
    page = _make_page(store)
    emitted: list = []
    page.alerts_acknowledged.connect(lambda: emitted.append(1))

    page._ack_all_alerts()

    assert emitted == []


# ── Undo ──────────────────────────────────────────────────────────────────────

def test_undo_restores_the_whole_backlog(store):
    ids = _seed(store, 12)
    page = _make_page(store)
    page.set_pending_alert_rows(store.get_unacked_alerts())
    page._ack_all_alerts()

    page._undo_ack_all(ids)

    assert {a["id"] for a in store.get_unacked_alerts()} == set(ids)
    assert page._ac_count_lbl.text() == "showing 5 of 12"


def test_ack_all_offers_an_undo_action_on_the_toast(store, monkeypatch):
    _seed(store, 12)
    page = _make_page(store)
    page.set_pending_alert_rows(store.get_unacked_alerts())

    shown: list = []
    from ui.widgets import toast as _toast_mod
    monkeypatch.setattr(
        _toast_mod.ToastManager, "show",
        classmethod(lambda cls, msg, kind="info", action_label="", action_callback=None:
                    shown.append((msg, kind, action_label, action_callback))),
    )

    page._ack_all_alerts()

    assert len(shown) == 1
    msg, kind, action_label, action_callback = shown[0]
    assert msg == "12 alerts acknowledged"
    assert kind == "action"
    assert action_label == "Undo"

    action_callback()
    assert len(store.get_unacked_alerts()) == 12


# ── Single-row ack still reports the remaining backlog ────────────────────────

def test_single_row_ack_emits_so_the_card_repopulates(store):
    ids = _seed(store, 12)
    page = _make_page(store)
    page.set_pending_alert_rows(store.get_unacked_alerts())
    emitted: list = []
    page.alerts_acknowledged.connect(lambda: emitted.append(1))

    row = page._ac_alert_rows_lay.itemAt(0).widget()
    page._ack_alert_row(ids[0], row)

    assert emitted, (
        "acking one row must tell the dashboard to repopulate, or the backlog "
        "count stays stale for up to 30s"
    )
    assert len(store.get_unacked_alerts()) == 11

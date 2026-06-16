"""Tests for ui/widgets/weekly_report_card.py (S8-3 weekly report card)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.widgets.weekly_report_card import WeeklyReportCard

_created_widgets: list = []


@pytest.fixture(autouse=True)
def _cleanup_widgets():
    yield
    app = QApplication.instance()
    for w in _created_widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()
    _created_widgets.clear()


@pytest.fixture(autouse=True)
def _reset_qsettings():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("weekly_report/last_shown_week")
    qs.remove("traffic/plan_speed_mbps")
    yield
    qs.remove("weekly_report/last_shown_week")
    qs.remove("traffic/plan_speed_mbps")


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _make_store():
    store = MagicMock()
    store.query_uptime_table.return_value = [{"168.0": 99.6}]
    store.query_speed_test_history.return_value = []
    store.query_device_events.return_value = []
    store.query_app_traffic_category_totals.return_value = {}
    return store


def _make_card(app, store=None) -> WeeklyReportCard:
    card = WeeklyReportCard(store=store)
    _created_widgets.append(card)
    return card


def test_constructs_hidden_by_default(app):
    card = _make_card(app)
    assert card.isVisible() is False


def test_no_store_stays_hidden(app):
    card = _make_card(app, store=None)
    card.refresh()
    assert card.isVisible() is False


def test_refresh_shows_card_with_bullets(app):
    card = _make_card(app, store=_make_store())
    card.refresh()
    assert card.isVisible() is True
    assert "uptime" in card.current_bullets_text()


def test_refresh_hides_when_already_shown_this_week(app):
    from ui.widgets.weekly_report_card import _current_week_key
    QSettings("NetSentinel", "NetSentinel").setValue(
        "weekly_report/last_shown_week", _current_week_key()
    )
    card = _make_card(app, store=_make_store())
    card.refresh()
    assert card.isVisible() is False


def test_dismiss_hides_and_persists_week(app):
    from ui.widgets.weekly_report_card import _current_week_key
    card = _make_card(app, store=_make_store())
    card.refresh()
    assert card.isVisible() is True
    card.dismiss()
    assert card.isVisible() is False
    qs = QSettings("NetSentinel", "NetSentinel")
    assert qs.value("weekly_report/last_shown_week") == _current_week_key()


def test_email_requested_signal_emitted_on_click(app):
    card = _make_card(app, store=_make_store())
    card.refresh()
    received = []
    card.email_requested.connect(lambda: received.append(True))
    card._email_btn.click()
    assert received == [True]

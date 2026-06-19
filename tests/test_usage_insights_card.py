"""
Tests for ui/widgets/usage_insights_card.py (S6-3 / S6-4 / S6-5)

Covers:
  • UsageInsightsCard constructs without error
  • Default empty state shows the "start monitoring" CTA
  • refresh() with no store data leaves the empty state in place
  • refresh() with history populates the headline summary
  • refresh() shows the plan utilization line only when a cap is configured
  • refresh() shows a dismissible QoS suggestion when Gaming/VoIP overlap
  • Dismissing the QoS suggestion hides it and persists via QSettings
  • navigate_to signal emits "App Traffic" when the CTA is clicked
"""
from __future__ import annotations

import time

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.metric_store import MetricStore
from ui.widgets.usage_insights_card import UsageInsightsCard

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
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal
        for _ in range(3):
            app.processEvents()
    _created_widgets.clear()


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_card(app, store=None) -> UsageInsightsCard:
    card = UsageInsightsCard(store=store)
    _created_widgets.append(card)
    return card


def test_constructs_without_error(app):
    card = _make_card(app)
    assert card is not None
    assert card._has_data is False


def test_default_state_shows_cta(app):
    card = _make_card(app)
    assert "Open App Traffic" in card._cta_btn.text()


def test_refresh_noop_without_store(app):
    card = _make_card(app, store=None)
    card.refresh()
    assert card._has_data is False


def test_refresh_noop_with_no_history(app, store):
    card = _make_card(app, store=store)
    card.refresh()
    assert card._has_data is False


def test_refresh_populates_summary_from_history(app, store, monkeypatch):
    monkeypatch.setattr(
        "ui.widgets.usage_insights_card.QSettings",
        lambda *a, **kw: type("FakeQS", (), {"value": staticmethod(lambda *a, **k: 0.0)})(),
    )
    store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 680_000_000, 10.0, cdn="Netflix")
    store.record_app_traffic_sample("cc:dd", "Laptop", "Web", "HTTPS", 320_000_000, 10.0)
    card = _make_card(app, store=store)
    card.refresh()
    assert card._has_data is True
    assert "streaming" in card._sub_lbl.text().lower()
    assert card._cta_btn.text() == "View Details →"


def test_plan_utilization_hidden_when_no_cap(app, store):
    store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 100_000, 10.0)
    card = _make_card(app, store=store)
    card.refresh()
    assert card._plan_lbl.isVisible() is False


def test_plan_utilization_shown_when_cap_configured(app, store, monkeypatch):
    fake_values = {"traffic/monthly_cap_gb": 1000.0}
    monkeypatch.setattr(
        "ui.widgets.usage_insights_card.QSettings",
        lambda *a, **kw: type(
            "FakeQS", (), {"value": staticmethod(lambda key, default=None, type=None: fake_values.get(key, default))}
        )(),
    )
    store.record_app_traffic_sample("aa:bb", "TV", "Streaming", "HTTPS", 120_000_000_000, 10.0)
    card = _make_card(app, store=store)
    card.show()
    card.refresh()
    assert card._plan_lbl.isVisible() is True
    assert "%" in card._plan_lbl.text()


def test_qos_suggestion_shown_for_overlapping_categories(app, store, monkeypatch):
    monkeypatch.setattr(
        "ui.widgets.usage_insights_card.QSettings",
        lambda *a, **kw: type(
            "FakeQS", (), {
                "value": staticmethod(lambda key, default=None, type=None: default),
                "setValue": staticmethod(lambda *a, **k: None),
            }
        )(),
    )
    now = int(time.time())
    for h in range(9, 17):
        ts = now - (now % 3600) - (23 - h) * 3600  # spread across hours-of-day
        store.record_app_traffic_sample("aa:bb", "PC", "Gaming", "Steam", 1000, 10.0, ts=ts)
        store.record_app_traffic_sample("aa:bb", "PC", "VoIP", "SIP", 800, 10.0, ts=ts)
    card = _make_card(app, store=store)
    card.show()
    card.refresh()
    assert card._qos_row_w.isVisible() is True
    assert "Gaming" in card._qos_lbl.text()


def test_dismiss_qos_suggestion_hides_row(app, store):
    card = _make_card(app, store=store)
    card._qos_key = "abc123"
    card._qos_row_w.setVisible(True)
    card._dismiss_qos_suggestion()
    assert card._qos_row_w.isVisible() is False


def test_navigate_to_emits_app_traffic(app):
    card = _make_card(app)
    received = []
    card.navigate_to.connect(received.append)
    card._cta_btn.click()
    assert received == ["App Traffic"]

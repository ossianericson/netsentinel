"""
Tests for ui/widgets/bandwidth_hog_card.py (S5-4)

Covers:
  • BandwidthHogCard constructs without error
  • Default empty state shows the "start monitoring" CTA
  • on_bandwidth_update() updates headline/sub text with the top host
  • navigate_to signal emits "App Traffic" when the CTA is clicked
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.widgets.bandwidth_hog_card import BandwidthHogCard

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


def _make_card(app) -> BandwidthHogCard:
    card = BandwidthHogCard()
    _created_widgets.append(card)
    return card


def test_constructs_without_error(app):
    card = _make_card(app)
    assert card is not None
    assert card._has_data is False


def test_default_state_shows_cta(app):
    card = _make_card(app)
    assert "Open App Traffic" in card._cta_btn.text()


def test_on_bandwidth_update_sets_headline(app):
    card = _make_card(app)
    card.on_bandwidth_update({
        "label": "John's MacBook", "bytes_total": 940_000,
        "share_pct": 87.0, "window_s": 10.0,
    })
    assert card._has_data is True
    assert "John's MacBook" in card._headline_lbl.text()
    assert "87%" in card._headline_lbl.text()
    assert card._cta_btn.text() == "View Details →"


def test_navigate_to_emits_app_traffic(app):
    card = _make_card(app)
    received = []
    card.navigate_to.connect(received.append)
    card._cta_btn.click()
    assert received == ["App Traffic"]

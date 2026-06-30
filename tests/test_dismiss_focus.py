"""
Regression test: ✕ dismiss buttons must call window().activateWindow()
so the Windows Desktop does not steal focus.

Reproduction: before fix, every ✕ click caused focus_stolen_count += 1
in the monkey tester (confirmed 10/10 in moderate run, 12/12 in wild run).
"""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def qt_app(request):
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    yield app


# ── HomePage dismiss handlers ─────────────────────────────────────────────────

def test_dismiss_hw_nudge_activates_window(qt_app, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.pages.home_page import HomePage

    parent = QWidget()
    page = HomePage(store=None, parent=parent)

    activated = []
    monkeypatch.setattr(page, "window", lambda: MagicMock(activateWindow=lambda: activated.append(1)))

    page._dismiss_hw_nudge()
    assert activated, "_dismiss_hw_nudge must call window().activateWindow()"
    try:
        page.deleteLater()
        parent.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be scheduled for deletion
    qt_app.processEvents()


def test_dismiss_first_scan_banner_activates_window(qt_app, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.pages.home_page import HomePage

    parent = QWidget()
    page = HomePage(store=None, parent=parent)

    activated = []
    monkeypatch.setattr(page, "window", lambda: MagicMock(activateWindow=lambda: activated.append(1)))

    page._dismiss_first_scan_banner()
    assert activated, "_dismiss_first_scan_banner must call window().activateWindow()"
    try:
        page.deleteLater()
        parent.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be scheduled for deletion
    qt_app.processEvents()


def test_dismiss_dashboard_strip_activates_window(qt_app, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.pages.home_page import HomePage

    parent = QWidget()
    page = HomePage(store=None, parent=parent)

    activated = []
    monkeypatch.setattr(page, "window", lambda: MagicMock(activateWindow=lambda: activated.append(1)))

    page._dismiss_dashboard_strip()
    assert activated, "_dismiss_dashboard_strip must call window().activateWindow()"
    try:
        page.deleteLater()
        parent.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be scheduled for deletion
    qt_app.processEvents()


# ── UsageInsightsCard ─────────────────────────────────────────────────────────

def test_dismiss_qos_activates_window(qt_app, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.widgets.usage_insights_card import UsageInsightsCard

    parent = QWidget()
    card = UsageInsightsCard(store=None, parent=parent)

    activated = []
    monkeypatch.setattr(card, "window", lambda: MagicMock(activateWindow=lambda: activated.append(1)))

    card._dismiss_qos_suggestion()
    assert activated, "_dismiss_qos_suggestion must call window().activateWindow()"
    try:
        card.deleteLater()
        parent.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be scheduled for deletion
    qt_app.processEvents()


# ── AlertDrawer ───────────────────────────────────────────────────────────────

def test_close_drawer_activates_window(qt_app, monkeypatch):
    from PyQt6.QtWidgets import QWidget
    from ui.widgets.alert_drawer import AlertDrawer

    parent = QWidget()
    drawer = AlertDrawer(parent=parent)

    activated = []
    monkeypatch.setattr(drawer, "window", lambda: MagicMock(activateWindow=lambda: activated.append(1)))

    drawer.close_drawer()
    # Pump the event loop until the QPropertyAnimation finished signal fires.
    # The animation has a real (120 ms) duration, so we must let wall-clock time
    # elapse — a tight processEvents() loop alone never advances it to the end.
    import time
    deadline = time.monotonic() + 2.0
    while not activated and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.01)

    assert activated, "close_drawer must call window().activateWindow() when animation finishes"
    try:
        drawer.deleteLater()
        parent.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be scheduled for deletion
    qt_app.processEvents()

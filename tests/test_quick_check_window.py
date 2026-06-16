"""Tests for ui/widgets/quick_check_window.py (S8-2 quick-check floating window)."""
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication(["-platform", "offscreen"])


def _make_store(alerts=None, uptime_rows=None):
    store = MagicMock()
    store.get_recent_alerts.return_value = alerts or []
    store.query_uptime_table.return_value = uptime_rows or []
    store.query_all_rtt_hosts.return_value = []
    return store


def _teardown(widget):
    try:
        widget.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import_and_construct(qt_app):
    from ui.widgets.quick_check_window import QuickCheckWindow
    win = QuickCheckWindow(store=None)
    assert win.size().width() == 300
    assert win.size().height() == 200
    _teardown(win)


def test_no_store_shows_unknown_state(qt_app):
    from ui.widgets.quick_check_window import QuickCheckWindow
    win = QuickCheckWindow(store=None)
    assert "○" in win._icon_lbl.text() or win._icon_lbl.text() == "○"
    _teardown(win)


def test_refresh_uses_top_alert_as_finding(qt_app):
    from ui.widgets.quick_check_window import QuickCheckWindow
    store = _make_store(alerts=[{"message": "Host 192.168.1.5 is down"}])
    win = QuickCheckWindow(store=store)
    assert win._finding_lbl.text() == "Host 192.168.1.5 is down"
    _teardown(win)


def test_refresh_falls_back_to_health_subtext_when_no_alerts(qt_app):
    from ui.widgets.quick_check_window import QuickCheckWindow
    store = _make_store(alerts=[])
    win = QuickCheckWindow(store=store)
    assert win._finding_lbl.text() != ""
    _teardown(win)


def test_close_button_closes_window(qt_app):
    from ui.widgets.quick_check_window import QuickCheckWindow
    win = QuickCheckWindow(store=None)
    win.show()
    assert win.isVisible()
    win.close()
    assert not win.isVisible()
    _teardown(win)

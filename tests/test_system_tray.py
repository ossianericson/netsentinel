"""Tests for ui/system_tray.py notification click-through (S8-1 support)."""
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QWidget
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


@pytest.fixture
def window():
    QApplication.instance() or QApplication(["-platform", "offscreen"])
    w = QWidget()
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_show_notification_stores_click_callback(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()  # bypass real QSystemTrayIcon (unavailable headless)
    mgr._shown = True  # simulate showEvent() having already run show_tray_icon()
    callback = MagicMock()
    mgr.show_notification("Title", "Message", on_click=callback)
    assert mgr._pending_click_callback is callback
    mgr._tray.showMessage.assert_called_once()


def test_message_clicked_invokes_and_clears_callback(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._shown = True
    mgr._act_show = MagicMock()
    mgr._act_hide = MagicMock()
    callback = MagicMock()
    mgr.show_notification("Title", "Message", on_click=callback)
    mgr._on_message_clicked()
    callback.assert_called_once()
    assert mgr._pending_click_callback is None


def test_message_clicked_without_callback_is_safe(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._shown = True
    mgr._act_show = MagicMock()
    mgr._act_hide = MagicMock()
    mgr.show_notification("Title", "Message")  # no on_click
    mgr._on_message_clicked()  # must not raise


def test_message_clicked_swallows_callback_exception(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._shown = True
    mgr._act_show = MagicMock()
    mgr._act_hide = MagicMock()
    mgr.show_notification(
        "Title", "Message",
        on_click=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    mgr._on_message_clicked()  # must not raise


def test_show_notification_before_shown_is_noop(window):
    """RULE-DBG regression: show_notification() before show_tray_icon() must
    not touch the native QSystemTrayIcon — that Shell_NotifyIcon call-out
    reproduced a fatal Windows COM reentrancy fault (0x8001010d) when it fired
    during app.py's startup sequence, before the window was shown."""
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    callback = MagicMock()
    mgr.show_notification("Title", "Message", on_click=callback)
    mgr._tray.showMessage.assert_not_called()
    assert mgr._pending_click_callback is None


def test_refresh_icon_before_shown_is_noop(window):
    """Same guard for the setIcon()/setToolTip() call-out path (badge/grade/
    health updates), reachable via increment_badge()/set_grade()/set_health()
    before the tray icon has been shown."""
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._base_icon = MagicMock()
    mgr.increment_badge()
    mgr.set_grade("A")
    mgr.set_health("green", "All clear")
    mgr._tray.setIcon.assert_not_called()
    mgr._tray.setToolTip.assert_not_called()
    # State is still tracked even though the icon wasn't touched yet.
    assert mgr._badge_count == 1
    assert mgr._grade == "A"


def test_show_tray_icon_flushes_pending_state(window):
    """show_tray_icon() must apply any badge/grade/health state that was set
    while the icon was hidden, so it doesn't wait for the next update tick."""
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._base_icon = MagicMock()
    mgr.set_grade("B")
    mgr._tray.setIcon.assert_not_called()
    mgr.show_tray_icon()
    assert mgr._shown is True
    mgr._tray.show.assert_called_once()
    mgr._tray.setIcon.assert_called_once()

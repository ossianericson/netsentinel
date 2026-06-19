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
    callback = MagicMock()
    mgr.show_notification("Title", "Message", on_click=callback)
    assert mgr._pending_click_callback is callback
    mgr._tray.showMessage.assert_called_once()


def test_message_clicked_invokes_and_clears_callback(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
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
    mgr._act_show = MagicMock()
    mgr._act_hide = MagicMock()
    mgr.show_notification("Title", "Message")  # no on_click
    mgr._on_message_clicked()  # must not raise


def test_message_clicked_swallows_callback_exception(window):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._tray = MagicMock()
    mgr._act_show = MagicMock()
    mgr._act_hide = MagicMock()
    mgr.show_notification(
        "Title", "Message",
        on_click=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    mgr._on_message_clicked()  # must not raise

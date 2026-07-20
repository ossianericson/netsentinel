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


# ── Autostart wiring (Phase 5) ──────────────────────────────────────────────

def test_apply_autostart_state_updates_action(window):
    from modules.autostart import AutostartState
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._act_startup = MagicMock()
    state = AutostartState(backend="run_key", enabled=True, can_change=True, reason="")
    mgr._apply_autostart_state(state)
    mgr._act_startup.setChecked.assert_called_once_with(True)
    mgr._act_startup.setEnabled.assert_called_once_with(True)
    mgr._act_startup.setToolTip.assert_called_once_with("")


def test_start_autostart_worker_skips_when_one_already_running(window, monkeypatch):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    fake_worker = MagicMock()
    fake_worker.isRunning.return_value = True
    mgr._autostart_worker = fake_worker

    from workers import autostart_worker as _aw_mod
    ctor = MagicMock()
    monkeypatch.setattr(_aw_mod, "AutostartWorker", ctor)

    mgr._start_autostart_worker(enable=True)
    ctor.assert_not_called()


def test_on_startup_toggled_disables_action_and_starts_worker(window, monkeypatch):
    from ui.system_tray import SystemTrayManager
    mgr = SystemTrayManager(window)
    mgr._act_startup = MagicMock()
    started = {}
    monkeypatch.setattr(mgr, "_start_autostart_worker", lambda enable=None: started.setdefault("enable", enable))

    mgr._on_startup_toggled(True)

    mgr._act_startup.setEnabled.assert_called_once_with(False)
    assert started["enable"] is True


def test_startup_toggle_full_sequence_reflects_actual_result(window, monkeypatch):
    """RULE-T5: the toggle -> worker -> result_ready chain, driven end to end
    with a real AutostartWorker QThread, not just the individual methods in
    isolation. The user clicks "enable" but Windows reports the actual result
    differs (mirrors the RULE-T3 lying-checkbox regression covered at the
    modules.autostart layer in tests/test_autostart.py)."""
    from modules import autostart
    from ui.system_tray import SystemTrayManager

    monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
    monkeypatch.setattr(autostart, "set_run_on_startup", lambda enabled: None)
    # Actual registry state disagrees with the click - e.g. another process
    # raced it. set_autostart() must report what's actually there.
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: False)

    app = QApplication.instance()
    mgr = SystemTrayManager(window)
    mgr._act_startup = MagicMock()

    mgr._on_startup_toggled(True)
    mgr._act_startup.setEnabled.assert_called_with(False)

    assert mgr._autostart_worker is not None
    assert mgr._autostart_worker.wait(5000), "AutostartWorker did not finish within 5s"
    for _ in range(5):
        app.processEvents()

    assert mgr._autostart_state is not None
    assert mgr._autostart_state.enabled is False  # actual, not the requested True
    mgr._act_startup.setChecked.assert_called_with(False)
    mgr._act_startup.setEnabled.assert_called_with(True)  # run_key is always changeable

"""
ui/system_tray.py — System Tray Guardian
=========================================
Manages the persistent system-tray presence for NetSentinel.

Features
--------
- Animated/badge tray icon (unacknowledged alert count overlay)
- Right-click context menu: Show / Hide / Alerts / Quit
- show_notification(title, message, severity) — routes desktop toasts
- Startup-at-login: backed by modules.autostart (Run-key or WinRT StartupTask
  depending on build) via workers.autostart_worker.AutostartWorker

Architecture notes
------------------
- Single instance created by app.py, passed into Dashboard via __init__
- No blocking I/O; all badge drawing is pure QPainter
- Autostart state is backend-selected (modules.autostart.autostart_backend())
  and always queried/set off the GUI thread (workers/autostart_worker.py) —
  the WinRT backend hard-guards against main-thread calls (RULE 4)
- Never imports from ui.dashboard — dependency direction is one-way
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ui import styles as _s


# ── Badge icon builder ────────────────────────────────────────────────────────

def _build_badge_icon(base_icon: QIcon, count: int) -> QIcon:
    """
    Overlay a red badge with the alert count onto base_icon.
    Returns a new QIcon.  count=0 → returns base_icon unchanged.
    """
    if count == 0:
        return base_icon

    px = base_icon.pixmap(32, 32)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Red circle
    badge_size = 13
    x = px.width()  - badge_size
    y = 0
    painter.setBrush(QColor(_s.RED))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(x, y, badge_size, badge_size)

    # Count number
    font = QFont("Segoe UI", 7, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    text = str(min(count, 99))
    painter.drawText(x, y, badge_size, badge_size, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()

    return QIcon(px)


def _health_dot_colour(state: str) -> "str | None":
    """Semantic dot colour per health state, read live (theme switch aware)."""
    return {
        "green":  _s.GREEN,
        "amber":  _s.AMBER,
        "red":    _s.RED,
    }.get(state)


def _overlay_health_dot(base_icon: QIcon, state: str) -> QIcon:
    """
    Overlay a small coloured dot in the bottom-left of the tray icon to
    represent the ambient health state.  Returns base_icon unchanged when
    state is 'unknown'.
    """
    colour_hex = _health_dot_colour(state)
    if not colour_hex:
        return base_icon

    px = base_icon.pixmap(32, 32)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    dot_size = 8
    x = 0
    y = px.height() - dot_size

    painter.setBrush(QColor(colour_hex))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(x, y, dot_size, dot_size)
    painter.end()

    return QIcon(px)


# ── SystemTrayManager ─────────────────────────────────────────────────────────

class SystemTrayManager:
    """
    Manages the QSystemTrayIcon lifecycle.

    Usage
    -----
        tray = SystemTrayManager(main_window)
        tray.setup()                            # call after QApplication exists
        tray.show_notification("Alert", "msg")
        tray.increment_badge()
        tray.reset_badge()
    """

    def __init__(self, window, icon_path: str | None = None):
        """
        Parameters
        ----------
        window    : QMainWindow — the Dashboard instance
        icon_path : path to .ico / .png; falls back to bundled icon or coloured square
        """
        self._window    = window
        self._icon_path = icon_path
        self._tray:  QSystemTrayIcon | None = None
        self._badge_count = 0
        self._base_icon: QIcon | None = None
        self._grade: str = "?"
        self._health_state: str = "unknown"
        self._health_headline: str = ""
        self._pending_click_callback: Optional[Callable[[], None]] = None
        self._qs = QSettings("NetSentinel", "NetSentinel")
        # True only after show_tray_icon() has run — see show_tray_icon() and
        # the guards in show_notification()/_refresh_icon() for why this exists.
        self._shown = False
        # Last-known autostart state (modules.autostart.AutostartState) and
        # the in-flight query/set worker, if any — see _start_autostart_worker().
        self._autostart_state = None
        self._autostart_worker = None

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> bool:
        """Create and show the tray icon.  Returns False if tray is unavailable."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        self._base_icon = self._load_icon()
        self._tray = QSystemTrayIcon(self._base_icon, self._window)
        self._tray.setToolTip(_s.safe_tooltip("NetSentinel — Network Guardian"))

        menu = self._build_menu()
        menu.aboutToShow.connect(self._on_menu_about_to_show)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.messageClicked.connect(self._on_message_clicked)
        # .show() is deliberately NOT called here — see show_tray_icon().
        # self._tray is fully constructed and wired above so is_available()
        # (self._tray is not None) still works immediately for callers gating
        # on it during startup, before the icon is actually shown.
        return True

    def show_tray_icon(self) -> None:
        """Show the already-constructed tray icon. Must only be called from
        AppHeaderMixin.showEvent() (ui/header.py) — never from setup() or
        anywhere else in Dashboard.__init__/main()'s startup sequence.
        QSystemTrayIcon.show() calls into Shell_NotifyIcon, a COM call-out.
        Calling it synchronously from setup() (invoked from Dashboard.__init__,
        while a dozen+ background QThread workers are already starting, and
        while main() is still pumping nested processEvents() calls via
        _splash_msg) reproduced a fatal, uncatchable Windows COM reentrancy
        fault (0x8001010d) during a 2026-07-08 chaos soak run
        (docs/spikes/startup-com-reentrancy.md). Deferring with
        QTimer.singleShot(0, ...) from setup() was tried and confirmed NOT to
        fix it — the 0ms timer fires on the very next event-loop turn, which
        is _splash_msg's own processEvents() call, the same pump it needed to
        avoid. showEvent() only fires after the real window.show() runs,
        which is after every _splash_msg pump in main() has already returned.

        showMessage()/setIcon()/setToolTip() are the same Shell_NotifyIcon
        call-out and are just as reachable during that startup window —
        show_notification() and _refresh_icon() are guarded by ``self._shown``
        below and stay silent until this method has run, then this method
        flushes any badge/grade/health state that was set while hidden.
        """
        if self._tray is not None:
            self._tray.show()
            self._shown = True
            self._refresh_icon()

    def _load_icon(self) -> QIcon:
        # 1. Caller-supplied path
        if self._icon_path:
            p = Path(self._icon_path)
            if p.exists():
                return QIcon(str(p))
        # 2. Standard asset locations
        _base = (Path(sys._MEIPASS)
                 if getattr(sys, "frozen", False)
                 else Path(__file__).parent.parent)
        for candidate in ("assets/icons/NetSentinel.ico",
                          "assets/icons/netsentinel.png",
                          "NetSentinel.ico", "icon.ico"):
            p = _base / candidate
            if p.exists():
                return QIcon(str(p))
        # 3. Fallback: plain blue square
        px = QPixmap(32, 32)
        px.fill(QColor(_s.ACCENT))
        return QIcon(px)

    def _build_menu(self) -> QMenu:
        menu = QMenu()
        _s.themed_ss(
            menu,
            "QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; font-size:11px; padding:4px; }}"
            "QMenu::item {{ padding:5px 20px; }}"
            "QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            "QMenu::separator {{ height:1px; background:{BORDER}; margin:3px 8px; }}",
        )

        self._act_health = QAction("○  Gathering health data…", menu)
        self._act_health.setEnabled(False)
        menu.addAction(self._act_health)

        menu.addSeparator()

        self._act_show = QAction("Show NetSentinel", menu)
        self._act_show.triggered.connect(self._show_window)
        menu.addAction(self._act_show)

        self._act_hide = QAction("Hide to Tray", menu)
        self._act_hide.triggered.connect(self._hide_window)
        menu.addAction(self._act_hide)

        menu.addSeparator()

        act_diagnose = QAction("◈  What's Wrong?", menu)
        act_diagnose.triggered.connect(self._open_diagnosis)
        menu.addAction(act_diagnose)

        act_scan = QAction("⟳  Run Full Scan", menu)
        act_scan.triggered.connect(self._run_full_scan)
        menu.addAction(act_scan)

        act_quickcheck = QAction("◷  Quick Check", menu)
        act_quickcheck.triggered.connect(self._open_quick_check)
        menu.addAction(act_quickcheck)

        menu.addSeparator()

        self._act_startup = QAction("Launch at Startup", menu)
        self._act_startup.setCheckable(True)
        # Real state is backend-selected (Run-key or WinRT StartupTask) and
        # can require an off-GUI-thread call (RULE 4) — populated
        # asynchronously on first _on_menu_about_to_show(), not here.
        self._act_startup.setChecked(False)
        self._act_startup.triggered.connect(self._on_startup_toggled)
        menu.addAction(self._act_startup)

        menu.addSeparator()

        act_alerts = QAction("Open Alerts…", menu)
        act_alerts.triggered.connect(self._open_alerts)
        menu.addAction(act_alerts)

        menu.addSeparator()

        act_quit = QAction("Quit NetSentinel", menu)
        act_quit.triggered.connect(self._quit)
        menu.addAction(act_quit)

        return menu

    def _on_menu_about_to_show(self) -> None:
        """Refresh dynamic state each time the menu opens."""
        is_visible = self._window.isVisible()
        self._act_show.setEnabled(not is_visible)
        self._act_hide.setEnabled(is_visible)
        if hasattr(self, "_act_startup"):
            # Apply the last-known state immediately (no blocking), then kick
            # off a background refresh — the user can change this in Windows
            # Settings while the app runs, so the menu should not go stale.
            if self._autostart_state is not None:
                self._apply_autostart_state(self._autostart_state)
            self._start_autostart_worker()
        # Refresh health line in menu
        if hasattr(self, "_act_health"):
            _icon = {"green": "✓", "amber": "⚠", "red": "✗"}.get(
                self._health_state, "○"
            )
            text = self._health_headline or "Gathering health data…"
            self._act_health.setText(f"{_icon}  {text[:60]}")

    # ── Public API ────────────────────────────────────────────────────────────

    def show_notification(self, title: str, message: str,
                          severity: str = "INFO",
                          on_click: Optional[Callable[[], None]] = None) -> None:
        """Show a native desktop notification balloon.

        ``on_click`` is invoked once if the user clicks the notification
        balloon itself (not the tray icon) before it dismisses.
        """
        if self._tray is None or not self._shown:
            return  # not shown yet — see show_tray_icon() docstring (COM reentrancy)
        icon_map = {
            "CRITICAL": QSystemTrayIcon.MessageIcon.Critical,
            "HIGH":     QSystemTrayIcon.MessageIcon.Critical,
            "WARNING":  QSystemTrayIcon.MessageIcon.Warning,
            "MEDIUM":   QSystemTrayIcon.MessageIcon.Warning,
        }
        icon = icon_map.get(severity.upper(), QSystemTrayIcon.MessageIcon.Information)
        self._pending_click_callback = on_click
        self._tray.showMessage(title, message, icon, 6000)

    def increment_badge(self) -> None:
        """Increment the unacknowledged alert counter and redraw tray icon."""
        self._badge_count += 1
        self._refresh_icon()

    def reset_badge(self) -> None:
        """Clear the alert badge (call when user opens the Alerts page)."""
        self._badge_count = 0
        self._refresh_icon()

    def set_badge(self, count: int) -> None:
        self._badge_count = max(0, count)
        self._refresh_icon()

    def set_grade(self, grade: str) -> None:
        """Update the network grade shown in the tray tooltip."""
        self._grade = grade[:1].upper() if grade else "?"
        self._refresh_icon()

    def set_health(self, state: str, headline: str) -> None:
        """Update ambient health state from HealthWorker result."""
        self._health_state   = state
        self._health_headline = headline
        self._refresh_icon()

    def is_available(self) -> bool:
        return self._tray is not None

    # ── Minimize-to-tray setting ──────────────────────────────────────────────

    def minimize_to_tray_enabled(self) -> bool:
        return self._qs.value("tray/minimize_to_tray", True, type=bool)

    def set_minimize_to_tray(self, enabled: bool) -> None:
        self._qs.setValue("tray/minimize_to_tray", enabled)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Single click or double-click on the tray icon — always restore the window.
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _on_message_clicked(self) -> None:
        self._show_window()
        callback = self._pending_click_callback
        self._pending_click_callback = None
        if callback is not None:
            try:
                callback()
            except Exception:
                pass  # non-fatal — notification click callback failed

    def _show_window(self) -> None:
        if hasattr(self._window, "show_main_window"):
            # Honours a pending maximize intent from a tray-only launch
            # (Phase 5.5) — see AppHeaderMixin.show_main_window().
            self._window.show_main_window()
        elif self._window.isMinimized():
            self._window.showNormal()
        else:
            self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        # Windows foreground lock can block the first activateWindow() when the
        # window has never been shown (e.g. --startup-logger mode). A deferred
        # second call after the event loop processes the show request succeeds.
        _t = QTimer(self._window)
        _t.setSingleShot(True)
        _t.timeout.connect(self._window.activateWindow)
        _t.start(150)
        self._act_show.setEnabled(False)
        self._act_hide.setEnabled(True)

    def _hide_window(self) -> None:
        self._window.hide()
        self._act_show.setEnabled(True)
        self._act_hide.setEnabled(False)

    def _open_diagnosis(self) -> None:
        self._show_window()
        if hasattr(self._window, "_open_diagnosis"):
            self._window._open_diagnosis()

    def _run_full_scan(self) -> None:
        self._show_window()
        if hasattr(self._window, "_start_full_scan"):
            self._window._start_full_scan()

    def _open_quick_check(self) -> None:
        # Deliberately does not restore the main window — Quick Check exists
        # precisely so the user can glance at health status without it (S8-2).
        if hasattr(self._window, "_show_quick_check_window"):
            self._window._show_quick_check_window()

    def _on_startup_toggled(self, checked: bool) -> None:
        # QAction already flipped its own visual checked state on trigger;
        # disable it until the worker reports what actually resulted — the
        # request is not guaranteed to be honoured (DisabledByUser/Policy).
        self._act_startup.setEnabled(False)
        self._start_autostart_worker(enable=checked)

    def _start_autostart_worker(self, enable: Optional[bool] = None) -> None:
        """Query (enable=None) or set (enable=True/False) autostart off the
        GUI thread. Never calls the setter synchronously (RULE 4 / RULE-UX2) —
        the WinRT backend hard-guards against main-thread calls outright."""
        if self._autostart_worker is not None and self._autostart_worker.isRunning():
            return  # a query/set is already in flight; let it finish
        from workers.autostart_worker import AutostartWorker
        worker = AutostartWorker(enable=enable, parent=self._window)
        worker.result_ready.connect(self._on_autostart_result)
        worker.error.connect(self._on_autostart_error)
        worker.finished.connect(worker.deleteLater)
        self._autostart_worker = worker
        worker.start()

    def _apply_autostart_state(self, state) -> None:
        if not hasattr(self, "_act_startup"):
            return
        self._act_startup.blockSignals(True)
        self._act_startup.setChecked(state.enabled)
        self._act_startup.setEnabled(state.can_change)
        self._act_startup.setToolTip(_s.safe_tooltip(state.reason) if state.reason else "")
        self._act_startup.blockSignals(False)

    def _on_autostart_result(self, state) -> None:
        self._autostart_state = state
        self._apply_autostart_state(state)
        # Sync the Settings page checkbox if it is currently open — with the
        # ACTUAL resulting state, never the value the user clicked.
        try:
            sp = getattr(self._window, "_settings_page", None)
            chk = getattr(sp, "_chk_startup", None)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(state.enabled)
                chk.setEnabled(state.can_change)
                chk.setToolTip(_s.safe_tooltip(state.reason) if state.reason else "")
                chk.blockSignals(False)
        except Exception:
            pass  # non-fatal

    def _on_autostart_error(self, message: str) -> None:
        if hasattr(self, "_act_startup"):
            self._act_startup.setEnabled(True)

    def _open_alerts(self) -> None:
        self._show_window()
        if hasattr(self._window, "_nav_go_to"):
            # "Alerts & Activity" was renamed to the Notifications page long ago;
            # the stale literal silently no-oped this tray action (RULE-NAV3).
            from ui.nav.labels import NavLabel as _L
            self._window._nav_go_to(_L.NOTIFICATIONS)

    def _quit(self) -> None:
        # Allow the normal close path to stop workers first
        self._window._tray_quit = True
        self._window.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _refresh_icon(self) -> None:
        if self._tray is None or self._base_icon is None or not self._shown:
            return  # not shown yet — see show_tray_icon() docstring (COM reentrancy)
        icon = _build_badge_icon(self._base_icon, self._badge_count)
        icon = _overlay_health_dot(icon, self._health_state)
        self._tray.setIcon(icon)
        parts = [f"Grade: {self._grade}"]
        if self._badge_count:
            parts.append(f"{self._badge_count} alert{'s' if self._badge_count != 1 else ''}")
        if self._health_state != "unknown" and self._health_headline:
            parts.append(self._health_headline[:50])
        self._tray.setToolTip(_s.safe_tooltip(f"NetSentinel — {' | '.join(parts)}"))

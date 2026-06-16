"""
ui/system_tray.py — System Tray Guardian
=========================================
Manages the persistent system-tray presence for NetSentinel.

Features
--------
- Animated/badge tray icon (unacknowledged alert count overlay)
- Right-click context menu: Show / Hide / Alerts / Quit
- show_notification(title, message, severity) — routes desktop toasts
- Startup-at-login helpers: set_run_on_startup() / get_run_on_startup()

Architecture notes
------------------
- Single instance created by app.py, passed into Dashboard via __init__
- No blocking I/O; all badge drawing is pure QPainter
- Windows startup uses winreg (guarded with ImportError for non-Windows)
- Never imports from ui.dashboard — dependency direction is one-way
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ui.styles import ACCENT, AMBER, GREEN, RED

# ── Startup registry helpers (Windows only) ───────────────────────────────────

_STARTUP_KEY  = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STARTUP_NAME = "NetSentinel"


def get_run_on_startup() -> bool:
    """Return True if the startup registry entry exists (Windows only)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0,
                             winreg.KEY_READ)
        winreg.QueryValueEx(key, _STARTUP_NAME)
        winreg.CloseKey(key)
        return True
    except (OSError, ImportError):
        return False


def set_run_on_startup(enabled: bool) -> None:
    """Add or remove the HKCU Run registry entry (Windows only, no-op elsewhere)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _STARTUP_KEY, 0,
                             winreg.KEY_SET_VALUE)
        if enabled:
            exe = _resolve_exe_path()
            winreg.SetValueEx(key, _STARTUP_NAME, 0, winreg.REG_SZ,
                              f'"{exe}" --startup-logger')
        else:
            try:
                winreg.DeleteValue(key, _STARTUP_NAME)
            except OSError:
                pass  # already absent
        winreg.CloseKey(key)
    except (OSError, ImportError):
        pass  # non-fatal


def _resolve_exe_path() -> str:
    """Return the path to NetSentinel.exe (packaged) or python + app.py (dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable  # PyInstaller single-exe
    root = Path(__file__).parent.parent
    app_py = root / "app.py"
    return f"{sys.executable} {app_py}"


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
    painter.setBrush(QColor(RED))
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


_HEALTH_DOT_COLOUR = {
    "green":  GREEN,
    "amber":  AMBER,
    "red":    RED,
}


def _overlay_health_dot(base_icon: QIcon, state: str) -> QIcon:
    """
    Overlay a small coloured dot in the bottom-left of the tray icon to
    represent the ambient health state.  Returns base_icon unchanged when
    state is 'unknown'.
    """
    colour_hex = _HEALTH_DOT_COLOUR.get(state)
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

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> bool:
        """Create and show the tray icon.  Returns False if tray is unavailable."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        self._base_icon = self._load_icon()
        self._tray = QSystemTrayIcon(self._base_icon, self._window)
        self._tray.setToolTip("NetSentinel — Network Guardian")

        menu = self._build_menu()
        menu.aboutToShow.connect(self._on_menu_about_to_show)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.messageClicked.connect(self._on_message_clicked)
        self._tray.show()
        return True

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
        px.fill(QColor(ACCENT))
        return QIcon(px)

    def _build_menu(self) -> QMenu:
        from ui.styles import BG_CARD, BORDER, TEXT_PRIMARY, BG_HOVER
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; font-size:11px; padding:4px; }}"
            f"QMenu::item {{ padding:5px 20px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
            f"QMenu::separator {{ height:1px; background:{BORDER}; margin:3px 8px; }}"
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
        self._act_startup.setChecked(get_run_on_startup())
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
            self._act_startup.setChecked(get_run_on_startup())
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
        if self._tray is None:
            return
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
        if self._window.isMinimized():
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
        set_run_on_startup(checked)
        # Sync the Settings page checkbox if it is currently open
        try:
            sp = getattr(self._window, "_settings_page", None)
            chk = getattr(sp, "_chk_startup", None)
            if chk is not None:
                chk.blockSignals(True)
                chk.setChecked(checked)
                chk.blockSignals(False)
        except Exception:
            pass  # non-fatal

    def _open_alerts(self) -> None:
        self._show_window()
        if hasattr(self._window, "_nav_go_to"):
            self._window._nav_go_to("Alerts & Activity")

    def _quit(self) -> None:
        # Allow the normal close path to stop workers first
        self._window._tray_quit = True
        self._window.close()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _refresh_icon(self) -> None:
        if self._tray is None or self._base_icon is None:
            return
        icon = _build_badge_icon(self._base_icon, self._badge_count)
        icon = _overlay_health_dot(icon, self._health_state)
        self._tray.setIcon(icon)
        parts = [f"Grade: {self._grade}"]
        if self._badge_count:
            parts.append(f"{self._badge_count} alert{'s' if self._badge_count != 1 else ''}")
        if self._health_state != "unknown" and self._health_headline:
            parts.append(self._health_headline[:50])
        self._tray.setToolTip(f"NetSentinel — {' | '.join(parts)}")

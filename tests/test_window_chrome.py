"""
Regression tests for the frameless-window chrome (AppHeaderMixin).

RULE-T3: these were written RED, against the shipped defect — the header's
maximize button called showFullScreen() (which hides the taskbar and ignores the
work area) instead of showMaximized() (which docks to it, like every standard
Windows app).  changeEvent() keyed its glyph/tooltip off WindowFullScreen to
match, so the button even advertised itself as "Full Screen".

RULE-TP4-DASH: a real Dashboard may never be constructed in-process.  These
tests mix AppHeaderMixin into a bare QMainWindow instead — the two methods under
test (_toggle_maximize / changeEvent) only touch window state and _maximize_btn,
both of which the host supplies.

Glyphs are written as \\uXXXX escapes, never as literal Segoe MDL2 private-use
characters (RULE-ENC1: PUA codepoints do not survive a cp1252 round-trip).
"""
import pytest

try:
    from PyQt6.QtCore import Qt, QEvent
    from PyQt6.QtWidgets import QMainWindow, QPushButton
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.header import AppHeaderMixin

CHROME_MAXIMIZE = ""   # Segoe MDL2 ChromeMaximize
CHROME_RESTORE = ""    # Segoe MDL2 ChromeRestore


class _ChromeHost(AppHeaderMixin, QMainWindow):
    """Minimal AppHeaderMixin host — no Dashboard, no _build_header()."""

    def __init__(self):
        super().__init__()
        self._maximize_btn = QPushButton()
        self._pre_maximize_geo = None
        self.calls = []

    def showEvent(self, event):
        # Bypass AppHeaderMixin.showEvent — it reaches into Dashboard-only
        # machinery (ToastManager, tray icon, welcome overlay, lazy-page
        # builder) that this bare host does not have.  Not under test here.
        QMainWindow.showEvent(self, event)

    # Spy on the window-state transitions _toggle_maximize drives.
    def showMaximized(self):
        self.calls.append("showMaximized")
        super().showMaximized()

    def showFullScreen(self):
        self.calls.append("showFullScreen")
        super().showFullScreen()

    def showNormal(self):
        self.calls.append("showNormal")
        super().showNormal()


@pytest.fixture
def host(qt_app):
    w = _ChromeHost()
    yield w
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already torn down
    for _ in range(3):
        qt_app.processEvents()


def test_toggle_maximize_maximizes_never_fullscreens(host):
    """The maximize button must dock to the work area, not go full-screen.

    Full-screen hides the taskbar; maximize respects it.  This is the defect the
    user reported as "no longer behaves like VS Code / standard Windows apps".
    """
    host._toggle_maximize()

    assert "showFullScreen" not in host.calls, (
        "maximize button called showFullScreen() — full-screen hides the taskbar "
        "and ignores the work area. It must call showMaximized()."
    )
    assert host.calls == ["showMaximized"]


def test_toggle_maximize_round_trips_back_to_normal(host):
    """Toggling twice returns the window to the normal (restored) state."""
    host._toggle_maximize()
    assert bool(host.windowState() & Qt.WindowState.WindowMaximized)

    host._toggle_maximize()
    assert not (host.windowState() & Qt.WindowState.WindowMaximized)
    assert host.calls == ["showMaximized", "showNormal"]


def test_restore_geometry_does_not_push_the_window_down_by_a_title_bar(qt_app, tmp_path):
    """Regression: the app came up with a 32px strip of desktop above it, every launch.

    QWidget::restoreGeometry() clamps the restored top to
    `availableGeometry.top() + PM_TitleBarHeight` (32px on Windows). That is a safety
    feature — it assumes a native title bar sits ABOVE the client and must not end up
    off-screen. Our window has no native title bar: the client IS the top edge. So a
    window saved flush with the top of the screen (y=0) is restored at y=32, the
    height is then clamped to keep it inside the work area, and the pushed-down
    values are what get saved on exit — so it sticks, on every launch, forever.

    Measured with the real saved blob: frame (1, 0, 1718, 1390) restored as
    (1, 32, 1718, 1359).

    Latent on the old frameless window (which could never be snapped flush to y=0);
    visible as soon as native chrome made Aero Snap work.
    """
    from PyQt6.QtCore import QSettings
    from ui.app_settings import apply_exact_geometry

    frameless = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window

    # 700x700 rather than a full desktop size (e.g. 1200x800) so the rect
    # stays within the offscreen Qt platform's small virtual screen — this
    # test verifies the y=0/x=1 title-bar-clamp undo, not a specific size,
    # and a too-large rect would now (correctly) get shrunk by
    # apply_exact_geometry()'s screen-bounds clamp (RULE-T3: off-screen rect).
    saved = QMainWindow()
    saved.setWindowFlags(frameless)
    saved.setGeometry(1, 0, 700, 700)        # flush with the top of the screen
    blob = saved.saveGeometry()

    s = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    s.setValue("window/geo_x", 1)
    s.setValue("window/geo_y", 0)
    s.setValue("window/geo_w", 700)
    s.setValue("window/geo_h", 700)

    w = QMainWindow()
    w.setWindowFlags(frameless)
    w.restoreGeometry(blob)
    clamped = w.geometry()

    apply_exact_geometry(w, s)

    assert w.geometry().y() == 0, (
        f"window restored at y={w.geometry().y()} instead of the saved y=0 "
        f"(Qt's restoreGeometry clamped it to y={clamped.y()}). A custom-chrome "
        f"window has no title bar above its client, so this leaves a strip of bare "
        f"desktop above the header."
    )
    assert w.geometry().x() == 1
    assert (w.geometry().width(), w.geometry().height()) == (700, 700), (
        f"size not restored exactly: {w.geometry()} (Qt clamped it to "
        f"{clamped.width()}x{clamped.height()})"
    )

    for widget in (saved, w):
        try:
            widget.deleteLater()
        except RuntimeError:
            pass  # non-fatal — already torn down
    for _ in range(3):
        qt_app.processEvents()


def test_show_main_window_restores_to_maximized_not_normal_when_minimized_while_maximized(host):
    """Regression: minimizing a maximized window (auto-hidden to tray when
    tray/minimize_window_to_tray is enabled -- confirmed a real user's setting)
    and later restoring via show_main_window() (the tray icon's "Show
    NetSentinel" action) must bring the window back maximized, not silently
    downgrade it to its pre-maximize size/position.

    Mechanism, confirmed live against a real Dashboard: minimizing a maximized
    window keeps BOTH the WindowMinimized and WindowMaximized bits set --
    isMinimized() and isMaximized() are both True at once. show_main_window()'s
    `elif self.isMinimized(): self.showNormal()` branch does not check whether
    the window was ALSO maximized, so it unconditionally drops the maximized
    state and restores to the last normal geometry instead. Live repro: a real
    Dashboard, maximized then minimized then restored via show_main_window(),
    came back at (1000, 246, 1440, 900) instead of the full maximized rect --
    and that smaller rect is exactly what save_settings() persists on the next
    real quit, reproducing "the window keeps coming back small, not by me."
    """
    host.showMaximized()
    assert bool(host.windowState() & Qt.WindowState.WindowMaximized)

    host.showMinimized()
    assert host.isMinimized()
    assert bool(host.windowState() & Qt.WindowState.WindowMaximized), (
        "test setup invariant: minimizing a maximized window must keep the "
        "maximized bit set (confirmed live under both the real platform and "
        "offscreen QPA) -- if this fails, re-check that assumption before "
        "touching the fix"
    )

    host.calls.clear()
    host.show_main_window()

    assert "showNormal" not in host.calls, (
        "show_main_window() called showNormal() on a window that was ALSO "
        "maximized before being minimized -- this silently un-maximizes it "
        "every time the user minimizes (auto-hides to tray) and restores"
    )
    assert host.calls == ["showMaximized"]
    assert bool(host.windowState() & Qt.WindowState.WindowMaximized)


def test_changeevent_swaps_glyph_and_tooltip_on_maximize(host):
    """changeEvent must key off WindowMaximized, with standard Windows wording."""
    host.setWindowState(Qt.WindowState.WindowMaximized)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))

    assert host._maximize_btn.text() == CHROME_RESTORE
    assert "Restore Down" in host._maximize_btn.toolTip()

    host.setWindowState(Qt.WindowState.WindowNoState)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))

    assert host._maximize_btn.text() == CHROME_MAXIMIZE
    assert "Maximize" in host._maximize_btn.toolTip()


def test_changeevent_reshows_window_when_native_restore_leaves_it_hidden(host, monkeypatch):
    """Regression: RULE-WIN14 / docs/spikes/minimize-restore-repaint-failure.md (2026-07-23).

    Live-reproduced and root-caused: a native ShowWindow(SW_RESTORE) that bypasses
    Qt's own showNormal() (the chaos harness's focus-reclaim; some OS window-
    management paths) leaves the top-level QWidget's isVisible() stuck False even
    though the Win32 window is back on screen and exposed. Qt gates both painting AND
    the accessibility tree on QWidget visibility, so the window returned as a blank
    unpainted rectangle with an empty UIA tree (166 real controls collapsed to 6
    native-frame ones) and would not repaint on invalidate/resize. changeEvent() must
    re-sync visibility with self.show() on the minimized -> not-minimized transition
    WHEN the widget is stuck hidden -- and must NOT fire on entering minimized, on an
    unrelated state change, or on a normal restore where the widget is already visible.
    """
    calls = []
    monkeypatch.setattr(host, "show", lambda: calls.append("show"))
    # host is constructed but never shown, so isVisible() is naturally False --
    # exactly the stuck-hidden state the native restore leaves behind.

    # 1. Entering minimized must NOT re-show (nothing has been restored yet).
    host.setWindowState(Qt.WindowState.WindowMinimized)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    assert calls == []

    # 2. Restore that left the widget hidden -> must re-sync visibility with show().
    host.setWindowState(Qt.WindowState.WindowNoState)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    assert calls == ["show"], (
        "changeEvent() did not re-show the window on a restore that left the QWidget "
        "hidden -- the exact desync that left the client area blank and the UIA tree "
        "empty in the live repro."
    )

    # 3. A restore where the widget is already visible must NOT re-show it (the guard
    #    keeps the fix targeted to the broken state, off every normal restore).
    monkeypatch.setattr(host, "isVisible", lambda: True)
    host.setWindowState(Qt.WindowState.WindowMinimized)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    host.setWindowState(Qt.WindowState.WindowNoState)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    assert calls == ["show"], "re-showed a window that was already visible"

    # 4. An unrelated WindowStateChange (maximize) must not re-show either.
    monkeypatch.setattr(host, "isVisible", lambda: False)
    host.setWindowState(Qt.WindowState.WindowMaximized)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))
    assert calls == ["show"]

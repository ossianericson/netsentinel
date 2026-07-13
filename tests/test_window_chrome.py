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


def test_changeevent_swaps_glyph_and_tooltip_on_maximize(host):
    """changeEvent must key off WindowMaximized, with standard Windows wording."""
    host.setWindowState(Qt.WindowState.WindowMaximized)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))

    assert host._maximize_btn.text() == CHROME_RESTORE
    assert host._maximize_btn.toolTip() == "Restore Down"

    host.setWindowState(Qt.WindowState.WindowNoState)
    host.changeEvent(QEvent(QEvent.Type.WindowStateChange))

    assert host._maximize_btn.text() == CHROME_MAXIMIZE
    assert host._maximize_btn.toolTip() == "Maximize"

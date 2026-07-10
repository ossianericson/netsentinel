"""Regression: repeatedly opening the Ctrl+K command palette must not leak
palette instances as C++ children of the host window.

Root cause (fixed): `_NavBuilderMixin._open_command_palette` created a new
`CommandPalette(items, parent=self)` every time it opened after the previous
palette had been closed, but the old palette — parented to the dashboard — was
never freed. Under sustained Ctrl+K/Esc churn (the monkey soak) this leaked one
palette (with its ~120 QListWidgetItems and cached device/alert data) per open,
driving RSS from ~600 MB to >1.2 GB and eventually a Not-Responding hang.
"""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ui.command_palette import CommandPalette  # noqa: E402
from ui.nav.builder import _NavBuilderMixin  # noqa: E402


class _Host(QWidget):
    """Minimal stand-in for the dashboard that owns just the method under test."""
    _store = None

    def _build_palette_items(self):
        return [{"icon": "◆", "label": "Overview", "kind": "page"}]

    def _nav_rail_go_to(self, *a):
        pass

    def _on_palette_action(self, *a):
        pass

    # Bind the real method under test onto this lightweight host.
    _open_command_palette = _NavBuilderMixin._open_command_palette


def _pump(times=5):
    app = QApplication.instance()
    if app:
        for _ in range(times):
            app.processEvents()


def test_reopening_palette_does_not_accumulate_instances(qt_app):
    host = _Host()
    try:
        # Simulate the soak pattern: open, close (hide), open, close, open.
        for _ in range(4):
            host._open_command_palette()
            pal = host._cmd_palette
            # Closing a non-modal QDialog hides it; the next open takes the
            # "create a fresh palette" path (the leak path before the fix).
            pal.reject()
            _pump()

        host._open_command_palette()  # 5th, left open
        _pump()

        live = [c for c in host.findChildren(CommandPalette)]
        # Before the fix this was 5 (one leaked per open). Allow a small slack
        # for a not-yet-collected deleteLater, but it must not scale with opens.
        assert len(live) <= 2, (
            f"palette instances leaked: {len(live)} live children after 5 opens"
        )
    finally:
        try:
            host.deleteLater()
        except RuntimeError:
            pass  # non-fatal — host may already be torn down
        _pump()

"""Tests for ui/widgets/device_popover.py — floating device quick-profile popup."""
from __future__ import annotations

import pytest

try:
    from PyQt6 import QtWidgets as _qtw
    from PyQt6.QtCore import QPoint, QRect
except ImportError:  # pragma: no cover - PyQt6 always present in CI
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _FakeScreen:
    """Minimal stand-in for QScreen exposing only availableGeometry()."""

    def __init__(self, rect: QRect) -> None:
        self._rect = rect

    def availableGeometry(self) -> QRect:
        return self._rect


class _FakeApp:
    """Stand-in for QApplication's screen lookup statics.

    `screenAt()` mirrors Qt: the screen whose geometry contains the point.
    """

    primary: _FakeScreen
    secondary: _FakeScreen

    @staticmethod
    def primaryScreen() -> _FakeScreen:
        return _FakeApp.primary

    @staticmethod
    def screenAt(pos: QPoint):
        for scr in (_FakeApp.primary, _FakeApp.secondary):
            if scr._rect.contains(pos):
                return scr
        return None


def _drain() -> None:
    app = _qtw.QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_reposition_uses_the_screen_under_the_cursor(monkeypatch):
    """A popover opened on a secondary monitor must stay on that monitor.

    `_reposition()` clamped the cursor position against
    `primaryScreen().availableGeometry()`. Because `global_pos` is a
    virtual-desktop coordinate, a point on a secondary monitor is outside the
    primary's rect, so the `min(...)` clamps dragged the popover back onto the
    primary screen — it opened nowhere near the row the user right-clicked.

    The three sibling positioners (ui/app_settings.py, ui/widgets/jargon_tooltip.py,
    ui/widgets/page_header.py) all use `screenAt(global_pos)`; this one did not.
    """
    from ui.widgets.device_popover import DevicePopover

    # Secondary monitor sits to the RIGHT of the primary.
    _FakeApp.primary = _FakeScreen(QRect(0, 0, 1920, 1080))
    _FakeApp.secondary = _FakeScreen(QRect(1920, 0, 1920, 1080))

    pop = DevicePopover()
    try:
        monkeypatch.setattr(_qtw, "QApplication", _FakeApp)

        # A cursor position clearly on the secondary monitor.
        pop._reposition(QPoint(2500, 400))

        assert pop.x() >= 1920, (
            f"popover landed at x={pop.x()} — snapped back onto the primary "
            "monitor instead of staying under the cursor on the secondary"
        )
    finally:
        monkeypatch.undo()
        try:
            pop.deleteLater()
        except RuntimeError:
            pass  # already gone
        _drain()


def test_reposition_still_clamps_within_the_target_screen(monkeypatch):
    """Clamping behaviour must be preserved — just against the correct screen."""
    from ui.widgets.device_popover import DevicePopover

    _FakeApp.primary = _FakeScreen(QRect(0, 0, 1920, 1080))
    _FakeApp.secondary = _FakeScreen(QRect(1920, 0, 1920, 1080))

    pop = DevicePopover()
    try:
        monkeypatch.setattr(_qtw, "QApplication", _FakeApp)

        # Far bottom-right corner of the secondary screen: must be pulled back
        # inside that screen's available geometry, not pushed onto a third.
        pop._reposition(QPoint(3830, 1070))

        assert pop.x() + pop.width() <= 3840
        assert pop.y() + pop.height() <= 1080
        assert pop.x() >= 1920
    finally:
        monkeypatch.undo()
        try:
            pop.deleteLater()
        except RuntimeError:
            pass  # already gone
        _drain()

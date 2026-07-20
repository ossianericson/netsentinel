"""Tests for ui/widgets/badge_medallion.py."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def medallion():
    from ui.widgets.badge_medallion import BadgeMedallion
    m = BadgeMedallion(size=64)
    yield m
    _teardown(m)


def test_import():
    from ui.widgets.badge_medallion import BadgeMedallion  # noqa: F401


def test_starts_locked(medallion):
    assert medallion.is_earned() is False


def test_set_earned_flips_reported_state(medallion):
    medallion.set_earned(True)
    assert medallion.is_earned() is True
    medallion.set_earned(False)
    assert medallion.is_earned() is False


def test_paints_locked_state_without_raising(medallion):
    medallion.set_earned(False)
    pixmap = medallion.grab()
    assert not pixmap.isNull()


def test_paints_earned_state_without_raising(medallion):
    medallion.set_earned(True)
    pixmap = medallion.grab()
    assert not pixmap.isNull()


def test_theme_switch_does_not_break_repaint(medallion):
    """RULE-LINT4 trap: paintEvent reads theme globals directly, so themed_ss()
    cannot re-render it — the medallion must self-subscribe to theme_changed."""
    from ui import styles as _s

    original = _s.get_active_theme_name()
    try:
        medallion.set_earned(True)
        _s.apply_theme("Arctic Clean")
        pm1 = medallion.grab()
        assert not pm1.isNull()

        _s.apply_theme("Midnight Pro")
        pm2 = medallion.grab()
        assert not pm2.isNull()
    finally:
        _s.apply_theme(original)

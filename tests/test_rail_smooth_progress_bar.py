"""Regression test for ui/nav/rail.py::_SmoothProgressBar (RULE-T3).

Live walkthrough of the Lab Mode Badge Scoreboard found a real crash:
navigating to LabScoreboardPanel a second time (>250ms after the first, e.g.
built once at page construction then refreshed again on "View Badges ->")
raised RuntimeError: wrapped C/C++ object of type QVariantAnimation has been
deleted. Root cause: set_smooth_value()'s animation self-deletes via
finished.connect(anim.deleteLater) but never cleared self._anim, so the next
call's `self._anim.stop()` ran on an already-deleted C++ object.
"""
from __future__ import annotations

import time

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
def bar():
    from ui.nav.rail import _SmoothProgressBar
    b = _SmoothProgressBar()
    b.setRange(0, 10)
    yield b
    _teardown(b)


def test_import():
    from ui.nav.rail import _SmoothProgressBar  # noqa: F401


def _pump_events(seconds: float) -> None:
    app = QApplication.instance()
    deadline = time.time() + seconds
    while time.time() < deadline:
        if app:
            app.processEvents()
        time.sleep(0.01)


def test_set_smooth_value_after_prior_animation_naturally_finishes(bar):
    """Reproduces the live crash: a second call, made after the first
    animation has had time to complete and self-delete, must not raise."""
    bar.set_smooth_value(3)
    _pump_events(0.4)   # animation duration is 250ms — let it finish naturally
    bar.set_smooth_value(7)   # must not raise RuntimeError
    _pump_events(0.4)
    assert bar.value() == 7


def test_set_smooth_value_called_rapidly_still_stops_cleanly(bar):
    """The early-stop path (second call before the first anim finishes) must
    also keep working — this is the branch that already explicitly stops
    and clears the previous animation."""
    bar.set_smooth_value(3)
    bar.set_smooth_value(9)   # interrupts the first animation early
    _pump_events(0.4)
    assert bar.value() == 9

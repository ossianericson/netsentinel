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


def _pump_until(predicate, timeout: float = 5.0) -> None:
    """Pump the Qt event loop until predicate() holds, or timeout elapses.

    A FIXED-duration pump makes every assertion below a race against the
    250ms animation. macOS CI failed on exactly that: the last frame it got
    to process sat at ~196ms of animation time (InOutSine -> v~8.9 -> int()
    -> 8), the 0.4s deadline expired before `finished` fired, and the test
    reported `assert 8 == 9` on correct production code. Polling keeps the
    assertions exact while surviving an arbitrarily loaded runner.

    Returns as soon as the predicate holds, then drains a few more passes so
    any deleteLater() queued by the same handler is actually processed.
    """
    app = QApplication.instance()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if app:
            app.processEvents()
        if predicate():
            break
        time.sleep(0.01)
    for _ in range(3):
        if app:
            app.processEvents()


def test_set_smooth_value_after_prior_animation_naturally_finishes(bar):
    """Reproduces the live crash: a second call, made after the first
    animation has had time to complete and self-delete, must not raise."""
    bar.set_smooth_value(3)
    # Wait for the animation to finish AND self-delete -- `_anim is None` is
    # the precondition the crash needed, so waiting on it (rather than on a
    # wall-clock guess) is what makes the next call a real regression probe.
    _pump_until(lambda: bar._anim is None)
    assert bar.value() == 3
    bar.set_smooth_value(7)   # must not raise RuntimeError
    _pump_until(lambda: bar.value() == 7)
    assert bar.value() == 7


def test_set_smooth_value_called_rapidly_still_stops_cleanly(bar):
    """The early-stop path (second call before the first anim finishes) must
    also keep working — this is the branch that already explicitly stops
    and clears the previous animation."""
    bar.set_smooth_value(3)
    bar.set_smooth_value(9)   # interrupts the first animation early
    _pump_until(lambda: bar.value() == 9)
    assert bar.value() == 9

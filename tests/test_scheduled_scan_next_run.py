"""Regression tests for scheduled-scan next-run computation (RULE-WIN22).

Two defects motivated this helper, both from the same duplicated arithmetic living
in two files that disagreed:

1. **GUI-thread hang.** ``ui/dashboard.py`` advanced the next-run time with
   ``while nxt.timestamp() <= now: nxt += timedelta(hours=hours)`` on the GUI thread,
   reading ``hours`` from QSettings with a bare ``int()``. A stored ``0`` or negative
   value spins that loop forever — Windows marks the app "Not Responding" — and a
   non-numeric value raises ``ValueError`` inside a ``QTimer`` slot.

2. **Schedule silently ignored.** ``ui/pages/settings_cards.py`` advanced with a
   single ``if`` rather than a ``while``, so a configured time already several
   intervals in the past was saved *still in the past*; the scan then fired on the
   next 60 s dashboard tick instead of at the requested time.

Collapsing both onto one helper is the fix: the divergence was the defect.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from modules.scheduler import next_scheduled_run


def _at(y, mo, d, h, mi) -> float:
    return _dt.datetime(y, mo, d, h, mi).timestamp()


def test_returns_todays_slot_when_it_is_still_ahead():
    now = _at(2026, 9, 2, 8, 0)
    got = next_scheduled_run(now=now, hour=14, minute=30, interval_hours=24)
    assert got == _at(2026, 9, 2, 14, 30)


def test_advances_past_a_slot_that_has_already_passed():
    now = _at(2026, 9, 2, 18, 0)
    got = next_scheduled_run(now=now, hour=14, minute=30, interval_hours=24)
    assert got == _at(2026, 9, 3, 14, 30)


def test_advances_repeatedly_when_many_intervals_have_elapsed():
    """The ``if``-instead-of-``while`` bug: one increment was not enough.

    A 1-hour schedule anchored at 02:00 and evaluated at 09:10 needs eight
    increments, not one. A single ``if`` leaves the result in the past.
    """
    now = _at(2026, 9, 2, 9, 10)
    got = next_scheduled_run(now=now, hour=2, minute=0, interval_hours=1)
    assert got > now, "next run must never be returned already in the past"
    assert got == _at(2026, 9, 2, 10, 0)


@pytest.mark.parametrize("bad", [0, -1, -24])
def test_non_positive_interval_cannot_hang(bad):
    """A zero/negative interval must be clamped, not looped on.

    This is the GUI-thread hang: the increment never advances the candidate past
    ``now``, so the loop cannot terminate.
    """
    now = _at(2026, 9, 2, 18, 0)
    got = next_scheduled_run(now=now, hour=14, minute=30, interval_hours=bad)
    assert got > now


@pytest.mark.parametrize("bad", ["abc", None, "", "12abc", 3.7])
def test_non_integer_interval_is_coerced_rather_than_raising(bad):
    """QSettings is untyped text on Windows; a slot must not raise on a bad value."""
    now = _at(2026, 9, 2, 18, 0)
    got = next_scheduled_run(now=now, hour=14, minute=30, interval_hours=bad)
    assert got > now


@pytest.mark.parametrize("hour,minute", [(-1, 0), (24, 0), (2, 60), (2, -5), ("x", "y")])
def test_out_of_range_clock_fields_are_coerced(hour, minute):
    now = _at(2026, 9, 2, 18, 0)
    got = next_scheduled_run(now=now, hour=hour, minute=minute, interval_hours=24)
    assert got > now


def test_result_is_always_strictly_in_the_future():
    """Property check across a day of anchors and every supported interval."""
    now = _at(2026, 9, 2, 13, 37)
    for h in range(24):
        for interval in (1, 6, 12, 24):
            got = next_scheduled_run(now=now, hour=h, minute=0, interval_hours=interval)
            assert got > now, f"hour={h} interval={interval} produced a past run"

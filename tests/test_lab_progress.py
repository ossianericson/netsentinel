"""Tests for modules/lab_progress.py — pure Lab Mode progress tracking (Phase L2)."""
from __future__ import annotations


def test_import():
    from modules import lab_progress
    assert lab_progress is not None


def test_mark_complete_first_attempt_records_entry():
    from modules.lab_progress import mark_complete
    state = {}
    result = {"verdict": "PASS", "completed_at": "2026-07-18 10:00:00"}
    state = mark_complete(state, "rogue_device", result)
    assert "rogue_device" in state
    entry = state["rogue_device"]
    assert entry["verdict"] == "PASS"
    assert entry["best_verdict"] == "PASS"
    assert entry["completed_at"] == "2026-07-18 10:00:00"
    assert entry["attempts"] == 1


def test_mark_complete_second_attempt_increments_attempts():
    from modules.lab_progress import mark_complete
    state = {}
    state = mark_complete(state, "rogue_device", {"verdict": "PARTIAL", "completed_at": "d1"})
    state = mark_complete(state, "rogue_device", {"verdict": "PARTIAL", "completed_at": "d2"})
    assert state["rogue_device"]["attempts"] == 2
    assert state["rogue_device"]["completed_at"] == "d2"


def test_mark_complete_upgrades_best_verdict_partial_then_pass():
    from modules.lab_progress import mark_complete
    state = {}
    state = mark_complete(state, "slow_dns", {"verdict": "PARTIAL", "completed_at": "d1"})
    assert state["slow_dns"]["best_verdict"] == "PARTIAL"
    state = mark_complete(state, "slow_dns", {"verdict": "PASS", "completed_at": "d2"})
    assert state["slow_dns"]["best_verdict"] == "PASS"
    assert state["slow_dns"]["verdict"] == "PASS"


def test_mark_complete_does_not_downgrade_best_verdict():
    from modules.lab_progress import mark_complete
    state = {}
    state = mark_complete(state, "slow_dns", {"verdict": "PASS", "completed_at": "d1"})
    state = mark_complete(state, "slow_dns", {"verdict": "PARTIAL", "completed_at": "d2"})
    assert state["slow_dns"]["best_verdict"] == "PASS"
    assert state["slow_dns"]["verdict"] == "PARTIAL"   # last-attempt verdict still tracked
    assert state["slow_dns"]["attempts"] == 2


def test_mark_complete_defaults_missing_verdict_to_incomplete():
    from modules.lab_progress import mark_complete
    state = mark_complete({}, "x", {"completed_at": "d1"})
    assert state["x"]["verdict"] == "INCOMPLETE"
    assert state["x"]["best_verdict"] == "INCOMPLETE"


def test_is_complete_false_for_unknown_scenario():
    from modules.lab_progress import is_complete
    assert is_complete({}, "rogue_device") is False


def test_is_complete_true_after_mark_complete():
    from modules.lab_progress import is_complete, mark_complete
    state = mark_complete({}, "rogue_device", {"verdict": "PASS", "completed_at": "d1"})
    assert is_complete(state, "rogue_device") is True


def test_summary_zero_of_total_when_empty():
    from modules.lab_progress import summary
    assert summary({}, 10) == (0, 10)


def test_summary_counts_distinct_completed_scenarios():
    from modules.lab_progress import mark_complete, summary
    state = {}
    state = mark_complete(state, "a", {"verdict": "PASS", "completed_at": "d1"})
    state = mark_complete(state, "b", {"verdict": "PARTIAL", "completed_at": "d1"})
    state = mark_complete(state, "a", {"verdict": "PASS", "completed_at": "d2"})  # re-attempt, not a new scenario
    assert summary(state, 10) == (2, 10)


def test_best_verdict_none_when_never_attempted():
    from modules.lab_progress import best_verdict
    assert best_verdict({}, "rogue_device") is None


def test_best_verdict_returns_recorded_value():
    from modules.lab_progress import best_verdict, mark_complete
    state = mark_complete({}, "rogue_device", {"verdict": "PASS", "completed_at": "d1"})
    assert best_verdict(state, "rogue_device") == "PASS"

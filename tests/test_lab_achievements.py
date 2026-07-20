"""Tests for modules/lab_achievements.py — Lab Mode badge/coverage math (RULE-TDD1)."""
from __future__ import annotations

from modules.lab_progress import mark_complete
from modules.lab_scenarios import SCENARIOS


def _earn(progress: dict, scenario_id: str, completed_at: str = "2026-07-19 10:00:00") -> dict:
    return mark_complete(progress, scenario_id, {"verdict": "PASS", "completed_at": completed_at})


def test_import():
    from modules import lab_achievements
    assert lab_achievements is not None


def test_badge_states_one_per_scenario_all_locked_when_empty():
    from modules.lab_achievements import badge_states
    states = badge_states({}, SCENARIOS)
    assert [s.scenario_id for s in states] == [s.id for s in SCENARIOS]
    assert all(not s.earned for s in states)
    assert all(s.earned_at == "" for s in states)
    assert all(s.attempts == 0 for s in states)


def test_badge_states_marks_earned_scenario_with_date_only():
    from modules.lab_achievements import badge_states
    progress = _earn({}, "rogue_device", "2026-07-19 10:00:00")
    states = {s.scenario_id: s for s in badge_states(progress, SCENARIOS)}
    earned = states["rogue_device"]
    assert earned.earned is True
    assert earned.earned_at == "2026-07-19"
    assert len(earned.earned_at) == 10
    assert earned.best_verdict == "PASS"
    assert earned.attempts == 1
    locked = states["slow_dns"]
    assert locked.earned is False
    assert locked.earned_at == ""


def test_earned_count_zero_of_ten_when_empty():
    from modules.lab_achievements import earned_count
    assert earned_count({}, SCENARIOS) == (0, len(SCENARIOS))


def test_curriculum_coverage_empty_progress_has_nonzero_denominators():
    from modules.lab_achievements import curriculum_coverage
    coverage = curriculum_coverage({}, SCENARIOS)
    assert coverage, "expected at least one certification with coverage"
    for cert, (earned, total) in coverage.items():
        assert earned == 0, cert
        assert total > 0, cert


def test_curriculum_coverage_after_earning_rogue_device_increases_networkplus():
    from modules.lab_achievements import curriculum_coverage
    progress = _earn({}, "rogue_device")
    coverage = curriculum_coverage(progress, SCENARIOS)
    assert "Network+" in coverage
    earned, total = coverage["Network+"]
    assert earned > 0
    assert earned <= total


def test_curriculum_coverage_dedups_objectives_shared_across_scenarios():
    from modules.lab_achievements import curriculum_coverage
    progress = _earn({}, "slow_dns")
    progress = _earn(progress, "trace_dns_resolvers")
    coverage = curriculum_coverage(progress, SCENARIOS)
    empty_coverage = curriculum_coverage({}, SCENARIOS)
    earned, total = coverage["Network+"]
    _, total_empty = empty_coverage["Network+"]
    # Shared objectives between the two DNS scenarios must count once, not twice —
    # the earned numerator can never exceed the de-duplicated denominator.
    assert total == total_empty
    assert earned <= total


def test_curriculum_coverage_ignores_unknown_scenario_id_in_progress():
    from modules.lab_achievements import curriculum_coverage
    progress = _earn({}, "rogue_device")
    progress["stale_removed_scenario"] = {
        "completed_at": "2026-01-01 00:00:00",
        "verdict": "PASS",
        "best_verdict": "PASS",
        "attempts": 1,
    }
    coverage = curriculum_coverage(progress, SCENARIOS)  # must not raise
    assert coverage["Network+"][0] > 0


def test_badge_states_ignores_unknown_scenario_id_in_progress():
    from modules.lab_achievements import badge_states
    progress = {"stale_removed_scenario": {"completed_at": "2026-01-01 00:00:00",
                                            "verdict": "PASS", "best_verdict": "PASS",
                                            "attempts": 1}}
    states = badge_states(progress, SCENARIOS)  # must not raise
    assert len(states) == len(SCENARIOS)
    assert all(not s.earned for s in states)


def test_badge_state_carries_protocol_for_cross_sell():
    from modules.lab_achievements import badge_states
    states = {s.scenario_id: s for s in badge_states({}, SCENARIOS)}
    assert states["rogue_device"].protocol == "ARP"

"""Tests for modules/lab_scenarios.py — pure data, no network required."""
from __future__ import annotations

import pytest


def test_import():
    import modules.lab_scenarios  # noqa: F401


def test_scenarios_list_non_empty():
    from modules.lab_scenarios import SCENARIOS
    assert isinstance(SCENARIOS, list)
    assert len(SCENARIOS) >= 1


def test_scenario_required_fields():
    from modules.lab_scenarios import SCENARIOS
    for s in SCENARIOS:
        assert hasattr(s, "id") and s.id
        assert hasattr(s, "title") and s.title
        assert hasattr(s, "steps") and isinstance(s.steps, list)
        assert len(s.steps) >= 1


def test_lab_step_fields():
    from modules.lab_scenarios import SCENARIOS
    for s in SCENARIOS:
        for step in s.steps:
            assert hasattr(step, "instruction")
            assert isinstance(step.instruction, str)


def test_get_scenario_found():
    from modules.lab_scenarios import SCENARIOS, get_scenario
    first_id = SCENARIOS[0].id
    result = get_scenario(first_id)
    assert result is not None
    assert result.id == first_id


def test_get_scenario_not_found():
    from modules.lab_scenarios import get_scenario
    assert get_scenario("__nonexistent__") is None


def test_lab_result_dataclass():
    from modules.lab_scenarios import LabResult
    lr = LabResult(
        scenario_id="rogue_device",
        scenario_title="Rogue Device",
        completed_at="2026-01-01T00:00:00",
        hints_used=0,
        steps_completed=3,
        steps_total=3,
        findings=["No rogue devices found"],
    )
    assert lr.scenario_id == "rogue_device"
    assert lr.steps_completed == 3
    assert lr.verdict == "INCOMPLETE"  # default


def test_lab_result_verdict_default():
    from modules.lab_scenarios import LabResult
    lr = LabResult(
        scenario_id="slow_dns",
        scenario_title="Slow DNS",
        completed_at="2026-01-01",
        hints_used=1,
        steps_completed=2,
        steps_total=4,
        findings=[],
    )
    assert isinstance(lr.verdict, str)


def test_all_known_scenarios_present():
    from modules.lab_scenarios import SCENARIOS
    ids = {s.id for s in SCENARIOS}
    expected = {"rogue_device", "slow_dns", "broadcast_storm", "map_subnet"}
    assert expected.issubset(ids), f"Missing scenarios: {expected - ids}"


def test_scenario_goal_field():
    from modules.lab_scenarios import SCENARIOS
    for s in SCENARIOS:
        assert hasattr(s, "goal")
        assert isinstance(s.goal, str)

"""
Tests for modules/evidence.py — the Signal Quality corroboration predicate.

Written test-first per RULE-TDD1. The gate exists because every Phase 3/4
signal asks the same question in a slightly different accent: "has this been
seen enough times, consecutively, to be worth speaking about — and is it the
*first* time we would speak about this episode?"  Phase 3 gives it one
production consumer (HOST_DOWN); Phase 4's modem/mesh/DNS wiring gives it four
more, which is the whole reason it is a module rather than four private streak
dicts.
"""
from __future__ import annotations

import pytest

from modules.evidence import DEFAULT_MIN_CONSECUTIVE, Evidence, EvidenceGate


BASE_TS = 1_780_000_000
CYCLE_S = 60


def _observe_run(gate: EvidenceGate, key: str, pattern: str):
    """Drive `gate` through a pattern string: '#' symptomatic, '.' healthy.

    Returns the list of admit() verdicts, one per observation.
    """
    verdicts = []
    for i, ch in enumerate(pattern):
        gate.observe(key, ch == "#", BASE_TS + i * CYCLE_S)
        verdicts.append(gate.admit(key)[0])
    return verdicts


# ── Defaults and shape ───────────────────────────────────────────────────────

class TestDefaults:
    def test_default_min_consecutive_is_a_positive_int(self):
        assert isinstance(DEFAULT_MIN_CONSECUTIVE, int)
        assert DEFAULT_MIN_CONSECUTIVE >= 1

    def test_evidence_is_immutable(self):
        ev = Evidence(observations=1, consecutive=1, window_s=0,
                      confidence=1.0, basis="x")
        with pytest.raises(Exception):
            ev.confidence = 0.5   # type: ignore[misc]

    def test_rejects_a_nonsense_min_consecutive(self):
        with pytest.raises(ValueError):
            EvidenceGate(min_consecutive=0)


# ── The edge: admit exactly once per episode ─────────────────────────────────

class TestEdgeSemantics:
    def test_admits_on_the_confirming_observation_only(self):
        gate = EvidenceGate(min_consecutive=3)
        assert _observe_run(gate, "h", "######") == [
            False, False, True, False, False, False
        ]

    def test_min_consecutive_one_admits_immediately(self):
        gate = EvidenceGate(min_consecutive=1)
        assert _observe_run(gate, "h", "###") == [True, False, False]

    def test_a_healthy_observation_re_arms_the_edge(self):
        gate = EvidenceGate(min_consecutive=1)
        assert _observe_run(gate, "h", "##.##") == [
            True, False, False, True, False
        ]

    def test_a_broken_streak_restarts_the_count(self):
        gate = EvidenceGate(min_consecutive=3)
        # Never three in a row until the final run.
        assert _observe_run(gate, "h", "##.##.###") == [
            False, False, False, False, False, False, False, False, True
        ]

    def test_admit_is_stable_within_one_observation(self):
        """Two rules asking about the same host in the same cycle must get the
        same answer — admit() reads the streak, it does not consume a token."""
        gate = EvidenceGate(min_consecutive=2)
        gate.observe("h", True, BASE_TS)
        gate.observe("h", True, BASE_TS + CYCLE_S)
        assert gate.admit("h")[0] is True
        assert gate.admit("h")[0] is True

    def test_keys_are_independent(self):
        gate = EvidenceGate(min_consecutive=2)
        gate.observe("a", True, BASE_TS)
        gate.observe("b", True, BASE_TS)
        gate.observe("a", True, BASE_TS + CYCLE_S)
        assert gate.admit("a")[0] is True
        assert gate.admit("b")[0] is False

    def test_admit_on_an_unseen_key_is_false_not_an_error(self):
        gate = EvidenceGate()
        ok, ev = gate.admit("never-seen")
        assert ok is False
        assert ev.consecutive == 0

    def test_reset_re_arms_without_a_healthy_observation(self):
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h")[0] is True
        gate.observe("h", True, BASE_TS + CYCLE_S)
        assert gate.admit("h")[0] is False
        gate.reset("h")
        gate.observe("h", True, BASE_TS + 2 * CYCLE_S)
        assert gate.admit("h")[0] is True

    def test_forget_drops_the_key_entirely(self):
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        gate.forget("h")
        assert gate.admit("h")[0] is False
        assert gate.admit("h")[1].observations == 0


# ── The Evidence payload ─────────────────────────────────────────────────────

class TestEvidencePayload:
    def test_counts_observations_and_window(self):
        gate = EvidenceGate(min_consecutive=2)
        for i in range(4):
            gate.observe("h", True, BASE_TS + i * CYCLE_S)
        _, ev = gate.admit("h")
        assert ev.consecutive == 4
        assert ev.observations == 4
        assert ev.window_s == 3 * CYCLE_S

    def test_window_is_zero_for_a_single_observation(self):
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h")[1].window_s == 0

    def test_basis_names_the_corroboration(self):
        gate = EvidenceGate(min_consecutive=3)
        for i in range(3):
            gate.observe("h", True, BASE_TS + i * CYCLE_S)
        basis = gate.admit("h")[1].basis
        assert "3" in basis and "consecutive" in basis.lower()

    def test_confidence_rises_with_corroboration(self):
        gate = EvidenceGate(min_consecutive=4)
        seen = []
        for i in range(4):
            gate.observe("h", True, BASE_TS + i * CYCLE_S)
            seen.append(gate.admit("h")[1].confidence)
        assert seen == sorted(seen)
        assert seen[0] < seen[-1]
        assert 0.0 <= seen[0] and seen[-1] <= 1.0


# ── Identity and baseline predicates ─────────────────────────────────────────

class TestIdentityAndBaseline:
    def test_an_unstable_identity_is_never_admitted(self):
        """A device the app cannot speak about does not become speakable by
        being broken repeatedly (acceptance criterion 4's spirit)."""
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        ok, ev = gate.admit("h", identity_stable=False)
        assert ok is False
        assert ev.confidence == 0.0

    def test_baseline_deviation_is_not_required_by_default(self):
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h", baseline_deviates=False)[0] is True

    def test_required_baseline_deviation_suppresses_expected_behaviour(self):
        gate = EvidenceGate(min_consecutive=1, require_baseline_deviation=True)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h", baseline_deviates=False)[0] is False

    def test_required_baseline_deviation_admits_a_real_deviation(self):
        gate = EvidenceGate(min_consecutive=1, require_baseline_deviation=True)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h", baseline_deviates=True)[0] is True

    def test_an_unknown_baseline_does_not_suppress(self):
        """Over-suppression is the failure mode the program plan calls out. No
        baseline yet must mean 'speak', not 'stay silent'."""
        gate = EvidenceGate(min_consecutive=1, require_baseline_deviation=True)
        gate.observe("h", True, BASE_TS)
        assert gate.admit("h", baseline_deviates=None)[0] is True

    def test_a_confirmed_deviation_raises_confidence(self):
        gate = EvidenceGate(min_consecutive=1)
        gate.observe("h", True, BASE_TS)
        plain = gate.admit("h")[1].confidence
        deviating = gate.admit("h", baseline_deviates=True)[1].confidence
        assert deviating > plain


# ── Housekeeping ─────────────────────────────────────────────────────────────

def test_healthy_keys_do_not_accumulate_state():
    """The gate lives for the life of the process and sees every host every
    cycle; a key that has never been symptomatic must not retain an entry."""
    gate = EvidenceGate(min_consecutive=2)
    for i in range(200):
        gate.observe(f"h{i}", False, BASE_TS + i)
    assert gate.tracked_keys() == 0


def test_a_recovered_key_is_released():
    gate = EvidenceGate(min_consecutive=2)
    gate.observe("h", True, BASE_TS)
    assert gate.tracked_keys() == 1
    gate.observe("h", False, BASE_TS + CYCLE_S)
    assert gate.tracked_keys() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

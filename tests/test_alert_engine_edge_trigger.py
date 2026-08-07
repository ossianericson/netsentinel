"""
Signal Quality Phase 3 — HOST_DOWN edge-triggering and duplicate-outage dedup.

Phase 0 measured two defects in the alert engine that survive the Phase 2 tier
gate and account for essentially all of the 6.6 claims/day that remained:

  1. HOST_DOWN is *level*-triggered. `_eval_rule_for_host` fires on every cycle
     where `state == "DOWN"`, bounded only by a 120 s cooldown, so one overnight
     outage produced ~240 alerts. Measured on the reference network: 1,637
     firings against 164 resolutions, a 10:1 ratio, for an event layer that
     recorded the same outages as 192 DOWN events.

  2. The same outage is reported twice under two names. HOST_DOWN
     (`state == "DOWN"`) and LOSS_THRESHOLD (`rtt < 0`) both fire from the same
     cycle for the same unreachable host.

Both fixes are opt-in via `experimental/signal_quality_v2` (RULE-EXP1), so the
default-off path must stay byte-identical — that is asserted here too, not just
the new behaviour.
"""
from __future__ import annotations

import pytest

from modules.alert_engine import AlertEngine, AlertRule


CYCLE_S = 60


def _engine(*rules) -> AlertEngine:
    return AlertEngine(store=None, rules=list(rules))


def _cycle(ts: int, states: dict, rtts: dict | None = None) -> dict:
    """A cycle dict in the shape evaluate_cycle() consumes.

    rtts defaults to -1.0 for DOWN and a healthy value otherwise, so a test
    that only cares about state does not have to restate the RTT contract.
    """
    if rtts is None:
        rtts = {h: (-1.0 if s == "DOWN" else 5.0) for h, s in states.items()}
    return {"ts": ts, "states": states, "rtts": rtts}


def _run(eng: AlertEngine, states_per_cycle, base_ts: int = 1_780_000_000):
    """Drive `eng` through consecutive cycles; return every AlertFired."""
    out = []
    for i, states in enumerate(states_per_cycle):
        out.extend(eng.evaluate_cycle(_cycle(base_ts + i * CYCLE_S, states)))
    return out


def _host_down(fired):
    return [a for a in fired if a.rule_type == "HOST_DOWN" and not a.is_resolution]


def _resolutions(fired):
    return [a for a in fired if a.is_resolution]


def _loss(fired):
    return [a for a in fired if a.rule_type == "LOSS_THRESHOLD"]


# ── Defect 1: level-triggered HOST_DOWN ──────────────────────────────────────

class TestEdgeTriggeredHostDown:
    def test_level_triggered_by_default_is_unchanged(self):
        """The legacy path must not move. Six DOWN cycles, cooldown 0, six alerts."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 6)
        assert len(_host_down(fired)) == 6

    def test_one_alert_per_outage_episode(self):
        """The defect itself: an outage spanning six cycles is one outage."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 6)
        assert len(_host_down(fired)) == 1

    def test_a_second_outage_after_recovery_alerts_again(self):
        """Over-suppression is the failure mode to watch — a new episode is news."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        fired = _run(eng, [
            {"10.0.0.9": "DOWN"}, {"10.0.0.9": "DOWN"},
            {"10.0.0.9": "UP"},
            {"10.0.0.9": "DOWN"}, {"10.0.0.9": "DOWN"},
        ])
        assert len(_host_down(fired)) == 2

    def test_resolution_still_fires_once_per_episode(self):
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        fired = _run(eng, [
            {"10.0.0.9": "DOWN"}, {"10.0.0.9": "DOWN"}, {"10.0.0.9": "UP"},
        ])
        assert len(_host_down(fired)) == 1
        assert len(_resolutions(fired)) == 1

    def test_a_single_cycle_blip_is_not_an_outage(self):
        """Consecutive confirmation: one missed ping is not a device going down."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(3)
        fired = _run(eng, [
            {"10.0.0.9": "UP"}, {"10.0.0.9": "DOWN"}, {"10.0.0.9": "UP"},
        ])
        assert _host_down(fired) == []

    def test_fires_exactly_on_the_confirming_observation(self):
        """min_consecutive=3 must fire on the 3rd DOWN, not the 1st and not the 4th."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(3)
        base = 1_780_000_000
        seen = []
        for i in range(6):
            fired = eng.evaluate_cycle(_cycle(base + i * CYCLE_S, {"10.0.0.9": "DOWN"}))
            seen.append(len(_host_down(fired)))
        assert seen == [0, 0, 1, 0, 0, 0]

    def test_streak_survives_a_suppressed_firing(self):
        """The streak is a property of the observation, not of whether an alert
        was emitted — a scope-suppressed host must not re-arm the edge."""
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        eng.set_alert_scope_checker(lambda host: False)   # suppress everything
        _run(eng, [{"10.0.0.9": "DOWN"}] * 3)
        eng.set_alert_scope_checker(None)                 # scope opens mid-outage
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 3)
        assert _host_down(fired) == [], (
            "the edge was consumed during the suppressed cycles; re-opening "
            "scope mid-episode must not manufacture a new outage"
        )

    def test_independent_hosts_keep_independent_edges(self):
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        fired = _run(eng, [
            {"10.0.0.9": "DOWN", "10.0.0.8": "UP"},
            {"10.0.0.9": "DOWN", "10.0.0.8": "DOWN"},
            {"10.0.0.9": "DOWN", "10.0.0.8": "DOWN"},
        ])
        hosts = sorted(a.host for a in _host_down(fired))
        assert hosts == ["10.0.0.8", "10.0.0.9"]

    def test_none_restores_the_legacy_path(self):
        eng = _engine(AlertRule("Host Down", "HOST_DOWN", cooldown_s=0))
        eng.set_availability_edge_trigger(1)
        eng.set_availability_edge_trigger(None)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 4)
        assert len(_host_down(fired)) == 4


# ── Defect 2: one outage, two names ──────────────────────────────────────────

class TestDuplicateOutageSuppression:
    def test_both_rules_fire_by_default(self):
        """Characterization of the defect — the legacy path is unchanged."""
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        fired = _run(eng, [{"10.0.0.9": "DOWN"}])
        assert len(_host_down(fired)) == 1
        assert len(_loss(fired)) == 1

    def test_loss_is_dropped_when_host_down_covers_the_host(self):
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng.set_duplicate_outage_suppression(True)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}])
        assert len(_host_down(fired)) == 1
        assert _loss(fired) == []

    def test_loss_survives_when_no_host_down_rule_is_enabled(self):
        """A user running LOSS_THRESHOLD alone must lose nothing — the dedup
        removes a duplicate, never the only report of an outage."""
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0, enabled=False),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng.set_duplicate_outage_suppression(True)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}])
        assert len(_loss(fired)) == 1

    def test_loss_survives_when_host_down_rule_targets_another_host(self):
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", host="10.0.0.1", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng.set_duplicate_outage_suppression(True)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}])
        assert len(_loss(fired)) == 1

    def test_loss_still_fires_for_a_lossy_host_that_is_not_down(self):
        """rtt < 0 with state != DOWN is a genuinely different fact."""
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng.set_duplicate_outage_suppression(True)
        fired = _run(eng, [
            {"10.0.0.9": "DEGRADED"},
        ])
        # DEGRADED with a dropped packet — HOST_DOWN says nothing about this.
        eng2 = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng2.set_duplicate_outage_suppression(True)
        fired = eng2.evaluate_cycle(
            {"ts": 1_780_000_000, "states": {"10.0.0.9": "DEGRADED"},
             "rtts": {"10.0.0.9": -1.0}}
        )
        assert len(_loss(fired)) == 1


# ── The two together: what the flag actually turns on ────────────────────────

class TestCombinedPhase3Path:
    def test_one_outage_produces_one_alert_and_one_resolution(self):
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        eng.set_availability_edge_trigger(3)
        eng.set_duplicate_outage_suppression(True)
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 10 + [{"10.0.0.9": "UP"}])
        assert len(_host_down(fired)) == 1
        assert _loss(fired) == []
        assert len(_resolutions(fired)) == 1

    def test_legacy_default_is_the_measured_flood(self):
        """Same history, both switches untouched: 10 + 10 + 1 = 21 claims."""
        eng = _engine(
            AlertRule("Host Down", "HOST_DOWN", cooldown_s=0),
            AlertRule("Packet Loss", "LOSS_THRESHOLD", cooldown_s=0),
        )
        fired = _run(eng, [{"10.0.0.9": "DOWN"}] * 10 + [{"10.0.0.9": "UP"}])
        assert len(_host_down(fired)) == 10
        assert len(_loss(fired)) == 10
        assert len(_resolutions(fired)) == 1


# ── Latency budget — acceptance criterion 5 ──────────────────────────────────

def test_confirmation_delay_stays_inside_the_three_minute_budget():
    """Criterion 5 requires gateway loss to alert within 3 minutes. At the
    shipped 60 s availability interval the engine's confirmation must therefore
    cost at most 3 cycles, and the monitor's own confirmation (Phase 3b) stacks
    on top of it — so this is the ceiling for BOTH, not for the engine alone."""
    from modules.availability_monitor import DEFAULT_INTERVAL_S
    from modules.evidence import DEFAULT_MIN_CONSECUTIVE
    from modules.device_baseline import DOWN_CONFIRMATION_CYCLES

    total_cycles = DEFAULT_MIN_CONSECUTIVE + DOWN_CONFIRMATION_CYCLES - 1
    assert total_cycles * DEFAULT_INTERVAL_S <= 180, (
        f"engine confirmation ({DEFAULT_MIN_CONSECUTIVE}) + monitor "
        f"confirmation ({DOWN_CONFIRMATION_CYCLES}) = {total_cycles} cycles at "
        f"{DEFAULT_INTERVAL_S}s exceeds the 3-minute acceptance budget"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

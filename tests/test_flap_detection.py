"""
Tests for flap/oscillation detection in AlertEngine (T2#11).
"""

from __future__ import annotations

import time
from typing import List


from modules.alert_engine import AlertEngine, AlertRule


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cycle(host: str, state: str, ts: int, rtt: float = 5.0) -> dict:
    return {"ts": ts, "states": {host: state}, "rtts": {host: rtt}}


def _multi_cycle(host: str, states: List[str], base_ts: int = 1000,
                 interval: int = 60) -> List[dict]:
    """Build a list of cycle dicts cycling through the given states."""
    return [
        _cycle(host, s, base_ts + i * interval)
        for i, s in enumerate(states)
    ]


def _flap_rule(flap_count: int = 4, flap_window_s: int = 600,
               cooldown_s: int = 0, host=None) -> AlertRule:
    return AlertRule(
        name="Host Flapping",
        rule_type="FLAP",
        host=host,
        flap_count=flap_count,
        flap_window_s=flap_window_s,
        cooldown_s=cooldown_s,
    )


def _down_rule(cooldown_s: int = 0, host=None) -> AlertRule:
    return AlertRule(
        name="Host Down",
        rule_type="HOST_DOWN",
        cooldown_s=cooldown_s,
        host=host,
    )


# ── Transition counting ───────────────────────────────────────────────────────

class TestCountTransitions:
    def test_no_history_returns_zero(self):
        assert AlertEngine._count_transitions([], 600, 1000) == 0

    def test_single_entry_returns_zero(self):
        assert AlertEngine._count_transitions([(1000, "UP")], 600, 1000) == 0

    def test_same_state_twice_returns_zero(self):
        history = [(800, "UP"), (900, "UP")]
        assert AlertEngine._count_transitions(history, 600, 1000) == 0

    def test_one_transition(self):
        history = [(800, "UP"), (900, "DOWN")]
        assert AlertEngine._count_transitions(history, 600, 1000) == 1

    def test_multiple_transitions(self):
        history = [(700, "UP"), (750, "DOWN"), (800, "UP"), (850, "DOWN")]
        assert AlertEngine._count_transitions(history, 600, 1000) == 3

    def test_entries_outside_window_excluded(self):
        # Only the last two entries are inside the 200s window
        history = [(300, "UP"), (400, "DOWN"), (850, "UP"), (950, "DOWN")]
        # now=1000, window=200 → cutoff=800 → only (850, UP) and (950, DOWN) visible
        assert AlertEngine._count_transitions(history, 200, 1000) == 1

    def test_window_exactly_boundary_included(self):
        # Entry at exactly now - window_s should be included
        history = [(400, "UP"), (401, "DOWN")]
        # now=1000, window=600 → cutoff=400 → both included
        assert AlertEngine._count_transitions(history, 600, 1000) == 1

    def test_alternating_many(self):
        states = ["UP", "DOWN"] * 5
        history = [(1000 + i * 10, s) for i, s in enumerate(states)]
        now = 1000 + (len(states) - 1) * 10 + 1
        # 10 entries → 9 transitions (alternates every time)
        assert AlertEngine._count_transitions(history, 600, now) == 9


# ── FLAP rule firing ──────────────────────────────────────────────────────────

class TestFlapRuleFiring:
    def test_flap_fires_when_transitions_meet_threshold(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        # UP→DOWN→UP→DOWN→UP = 4 transitions
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        assert len(flap_alerts) >= 1
        assert flap_alerts[0].host == "10.0.0.1"

    def test_flap_does_not_fire_below_threshold(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=6)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]  # only 4 transitions
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        assert not any(a.rule_type == "FLAP" for a in fired_all)

    def test_flap_does_not_fire_for_stable_host(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP"] * 10
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        assert not any(a.rule_type == "FLAP" for a in fired_all)

    def test_flap_does_not_fire_for_host_down_and_stays_down(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP", "DOWN", "DOWN", "DOWN", "DOWN"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        assert not any(a.rule_type == "FLAP" for a in fired_all)

    def test_flap_alert_contains_transition_count_as_value(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        assert flap_alerts[0].value is not None
        assert flap_alerts[0].value >= 4

    def test_flap_alert_message_contains_host(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        fired_all = []
        for cycle in _multi_cycle("192.168.1.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        assert "192.168.1.1" in flap_alerts[0].message
        assert "online and offline" in flap_alerts[0].message

    def test_flap_severity_is_warning(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        assert flap_alerts[0].severity == "WARNING"

    def test_flap_respects_cooldown(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4, cooldown_s=9999)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP", "DOWN", "UP", "DOWN"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        assert len(flap_alerts) == 1  # cooldown suppresses subsequent firings

    def test_flap_host_filter(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4, host="watched.host")])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        fired_all = []
        for cycle in _multi_cycle("other.host", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        assert not any(a.rule_type == "FLAP" for a in fired_all)

    def test_flap_window_excludes_old_transitions(self):
        """Transitions outside flap_window_s should not count."""
        engine = AlertEngine(rules=[_flap_rule(flap_count=4, flap_window_s=120)])
        now = 2000
        # 4 transitions well outside the 120s window, 1 transition inside
        old_cycles = [
            _cycle("10.0.0.1", "UP",   now - 500),
            _cycle("10.0.0.1", "DOWN", now - 400),
            _cycle("10.0.0.1", "UP",   now - 300),
            _cycle("10.0.0.1", "DOWN", now - 200),
        ]
        # Only 1 transition inside window
        recent_cycles = [
            _cycle("10.0.0.1", "UP",   now - 60),
        ]
        for cyc in old_cycles + recent_cycles:
            engine.evaluate_cycle(cyc)
        # At now-60 there is only 1 transition in the 120s window
        fired = engine.evaluate_cycle(_cycle("10.0.0.1", "DOWN", now))
        assert not any(a.rule_type == "FLAP" for a in fired)

    def test_default_rules_include_flap(self):
        engine = AlertEngine()
        types = {r.rule_type for r in engine.get_rules()}
        assert "FLAP" in types


# ── HOST_DOWN suppression during flap ────────────────────────────────────────

class TestHostDownSuppression:
    def test_host_down_suppressed_when_flapping(self):
        rules = [
            _down_rule(cooldown_s=0),
            _flap_rule(flap_count=4, cooldown_s=0),
        ]
        engine = AlertEngine(rules=rules)
        # Build enough transitions to trigger flap
        states = ["UP", "DOWN", "UP", "DOWN", "UP", "DOWN"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        down_alerts = [a for a in fired_all if a.rule_type == "HOST_DOWN"]
        flap_alerts = [a for a in fired_all if a.rule_type == "FLAP"]
        # Flap fires
        assert len(flap_alerts) >= 1
        # HOST_DOWN should not fire once flapping is detected
        # (it may fire early before the flap threshold is reached, then stop)
        # Find the ts of the first FLAP alert
        first_flap_ts = flap_alerts[0].ts
        late_down = [a for a in down_alerts if a.ts >= first_flap_ts]
        assert len(late_down) == 0, "HOST_DOWN fired after flap was detected"

    def test_host_down_fires_normally_when_not_flapping(self):
        rules = [
            _down_rule(cooldown_s=0),
            _flap_rule(flap_count=10, cooldown_s=0),  # threshold too high to trigger
        ]
        engine = AlertEngine(rules=rules)
        # stable down
        states = ["UP", "DOWN"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        assert any(a.rule_type == "HOST_DOWN" for a in fired_all)

    def test_host_down_suppression_only_for_flapping_host(self):
        """HOST_DOWN should still fire for a non-flapping host."""
        rules = [
            _down_rule(cooldown_s=0),
            _flap_rule(flap_count=4, cooldown_s=0),
        ]
        engine = AlertEngine(rules=rules)
        now = 1000
        # host A flaps
        flap_states = ["UP", "DOWN", "UP", "DOWN", "UP", "DOWN"]
        for cycle in _multi_cycle("flapping.host", flap_states, base_ts=now):
            engine.evaluate_cycle(cycle)
        # host B just goes down once (no flap)
        fired = engine.evaluate_cycle({
            "ts": now + 600,
            "states": {"stable.host": "DOWN"},
            "rtts": {"stable.host": -1.0},
        })
        assert any(a.rule_type == "HOST_DOWN" and a.host == "stable.host"
                   for a in fired)

    def test_host_down_fires_when_flap_rule_disabled(self):
        """Disabling the FLAP rule means no suppression occurs."""
        rules = [
            _down_rule(cooldown_s=0),
            AlertRule(
                name="Host Flapping",
                rule_type="FLAP",
                flap_count=4,
                flap_window_s=600,
                cooldown_s=0,
                enabled=False,
            ),
        ]
        engine = AlertEngine(rules=rules)
        states = ["UP", "DOWN", "UP", "DOWN", "UP", "DOWN"]
        fired_all = []
        for cycle in _multi_cycle("10.0.0.1", states):
            fired_all.extend(engine.evaluate_cycle(cycle))
        # With FLAP rule disabled, no flapping classification → HOST_DOWN fires
        assert any(a.rule_type == "HOST_DOWN" for a in fired_all)


# ── get_flapping_hosts() ──────────────────────────────────────────────────────

class TestGetFlappingHosts:
    def test_empty_initially(self):
        engine = AlertEngine(rules=[_flap_rule()])
        assert engine.get_flapping_hosts() == set()

    def test_host_appears_after_transitions(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]
        for cycle in _multi_cycle("10.0.0.1", states):
            engine.evaluate_cycle(cycle)
        assert "10.0.0.1" in engine.get_flapping_hosts()

    def test_host_absent_below_threshold(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=6)])
        states = ["UP", "DOWN", "UP", "DOWN", "UP"]  # only 4 transitions
        for cycle in _multi_cycle("10.0.0.1", states):
            engine.evaluate_cycle(cycle)
        assert "10.0.0.1" not in engine.get_flapping_hosts()

    def test_host_leaves_flapping_after_stabilising(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4, flap_window_s=200)])
        now = 5000
        # Flap a lot in the past (outside window)
        for i in range(8):
            state = "UP" if i % 2 == 0 else "DOWN"
            engine.evaluate_cycle(_cycle("10.0.0.1", state, now - 500 + i * 10))
        # After the window expires, host stabilises as UP
        engine.evaluate_cycle(_cycle("10.0.0.1", "UP", now))
        # No transitions in last 200s → not flapping anymore
        assert "10.0.0.1" not in engine.get_flapping_hosts()

    def test_returns_copy_not_reference(self):
        engine = AlertEngine(rules=[_flap_rule(flap_count=4)])
        hosts = engine.get_flapping_hosts()
        hosts.add("injected.host")
        assert "injected.host" not in engine.get_flapping_hosts()


# ── State history management ──────────────────────────────────────────────────

class TestStateHistory:
    def test_history_trimmed_to_24h(self):
        engine = AlertEngine(rules=[_flap_rule()])
        now = int(time.time())
        old_ts = now - 90000   # >24h ago
        engine.evaluate_cycle(_cycle("10.0.0.1", "UP",   old_ts))
        engine.evaluate_cycle(_cycle("10.0.0.1", "DOWN", now))
        history = engine._state_history.get("10.0.0.1", [])
        assert all(ts >= now - 86400 for ts, _ in history)

    def test_host_removed_when_history_empty(self):
        engine = AlertEngine(rules=[_flap_rule()])
        very_old = int(time.time()) - 90000
        engine.evaluate_cycle(_cycle("10.0.0.1", "UP", very_old))
        # Force a trim by running a new cycle
        engine.evaluate_cycle(_cycle("other.host", "UP", int(time.time())))
        # 10.0.0.1 should have been cleaned up only if its entry became empty,
        # but since we added a recent entry for other.host, only old ones trimmed
        for host_history in engine._state_history.values():
            assert host_history, "Host with empty history should be removed"

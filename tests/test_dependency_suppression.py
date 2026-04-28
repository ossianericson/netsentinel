"""
Tests for T3#12 — parent/child dependency suppression in AlertEngine.

When a parent host is DOWN, HOST_DOWN alerts for its registered children are
suppressed. Suppression lifts when the parent recovers.  All other rule types
(RTT_THRESHOLD, HOST_DEGRADED, etc.) are NOT suppressed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.alert_engine import AlertEngine, AlertRule


# ── helpers ───────────────────────────────────────────────────────────────────

def _minimal_engine() -> AlertEngine:
    """Engine with a single HOST_DOWN rule and no default clutter."""
    engine = AlertEngine(rules=[
        AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, cooldown_s=0),
    ])
    return engine


def _cycle(states: dict, ts: int = 1000, rtts: dict | None = None) -> dict:
    return {"ts": ts, "states": states, "rtts": rtts or {}}


# ── set / get / clear dependency map ─────────────────────────────────────────

class TestDependencyMapAPI:
    def test_set_and_get(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2", "10.0.0.3"])
        m = e.get_dependency_map()
        assert m["10.0.0.1"] == ["10.0.0.2", "10.0.0.3"]

    def test_set_replaces_existing(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        e.set_dependency_map("10.0.0.1", ["10.0.0.5"])
        assert e.get_dependency_map()["10.0.0.1"] == ["10.0.0.5"]

    def test_get_returns_copy(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        m = e.get_dependency_map()
        m["10.0.0.1"].append("MUTATED")
        assert "MUTATED" not in e.get_dependency_map()["10.0.0.1"]

    def test_clear_removes_all(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        e.set_dependency_map("10.0.0.9", ["10.0.0.10"])
        e.clear_dependency_map()
        assert e.get_dependency_map() == {}

    def test_multiple_parents_stored(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        e.set_dependency_map("10.0.0.100", ["10.0.0.101", "10.0.0.102"])
        m = e.get_dependency_map()
        assert len(m) == 2
        assert "10.0.0.100" in m


# ── basic suppression ─────────────────────────────────────────────────────────

class TestBasicSuppression:
    def test_child_suppressed_when_parent_down(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "DOWN",
            "10.0.0.2": "DOWN",
        }))
        hosts = [a.host for a in alerts]
        assert "10.0.0.1" in hosts        # parent fires
        assert "10.0.0.2" not in hosts    # child suppressed

    def test_parent_host_down_still_fires(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "DOWN",
            "10.0.0.2": "DOWN",
        }))
        assert any(a.host == "10.0.0.1" for a in alerts)

    def test_child_fires_when_parent_up(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "UP",
            "10.0.0.2": "DOWN",
        }))
        assert any(a.host == "10.0.0.2" for a in alerts)

    def test_child_fires_when_parent_absent_from_states(self):
        """If parent isn't in the current cycle, suppression does NOT apply."""
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({"10.0.0.2": "DOWN"}))
        assert any(a.host == "10.0.0.2" for a in alerts)

    def test_no_suppression_without_dependency_map(self):
        e = _minimal_engine()
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "DOWN",
            "10.0.0.2": "DOWN",
        }))
        hosts = {a.host for a in alerts}
        assert "10.0.0.1" in hosts
        assert "10.0.0.2" in hosts

    def test_suppression_lifts_when_parent_recovers(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])

        # Cycle 1: parent + child both down → child suppressed
        e.evaluate_cycle(_cycle({"10.0.0.1": "DOWN", "10.0.0.2": "DOWN"}, ts=1000))
        # Cycle 2: parent recovers, child still down → child should now fire
        alerts2 = e.evaluate_cycle(_cycle({"10.0.0.1": "UP", "10.0.0.2": "DOWN"}, ts=1010))
        assert any(a.host == "10.0.0.2" for a in alerts2)


# ── multiple children ─────────────────────────────────────────────────────────

class TestMultipleChildren:
    def test_all_children_suppressed(self):
        e = _minimal_engine()
        e.set_dependency_map("gw", ["host-a", "host-b", "host-c"])
        alerts = e.evaluate_cycle(_cycle({
            "gw":     "DOWN",
            "host-a": "DOWN",
            "host-b": "DOWN",
            "host-c": "DOWN",
        }))
        hosts = {a.host for a in alerts}
        assert "gw" in hosts
        assert "host-a" not in hosts
        assert "host-b" not in hosts
        assert "host-c" not in hosts

    def test_unrelated_host_not_suppressed(self):
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "DOWN",
            "10.0.0.2": "DOWN",
            "10.0.0.99": "DOWN",   # unrelated
        }))
        assert any(a.host == "10.0.0.99" for a in alerts)


# ── rule-type specificity ─────────────────────────────────────────────────────

class TestRuleTypeSpecificity:
    def test_rtt_threshold_not_suppressed(self):
        e = AlertEngine(rules=[
            AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, cooldown_s=0),
            AlertRule(name="High RTT",  rule_type="RTT_THRESHOLD", host=None,
                      threshold_ms=10.0, cooldown_s=0),
        ])
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle(
            {"10.0.0.1": "DOWN", "10.0.0.2": "UP"},
            rtts={"10.0.0.2": 999.0},
        ))
        types = {a.rule_type for a in alerts if a.host == "10.0.0.2"}
        assert "RTT_THRESHOLD" in types

    def test_host_degraded_not_suppressed(self):
        e = AlertEngine(rules=[
            AlertRule(name="Host Down",     rule_type="HOST_DOWN",     host=None, cooldown_s=0),
            AlertRule(name="Host Degraded", rule_type="HOST_DEGRADED", host=None, cooldown_s=0),
        ])
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle(
            {"10.0.0.1": "DOWN", "10.0.0.2": "DEGRADED"},
            rtts={"10.0.0.2": 500.0},
        ))
        assert any(a.host == "10.0.0.2" and a.rule_type == "HOST_DEGRADED" for a in alerts)

    def test_parent_degraded_does_not_suppress_child(self):
        """Only a DOWN parent triggers suppression; DEGRADED does not."""
        e = _minimal_engine()
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        alerts = e.evaluate_cycle(_cycle({
            "10.0.0.1": "DEGRADED",
            "10.0.0.2": "DOWN",
        }))
        assert any(a.host == "10.0.0.2" for a in alerts)


# ── on_alert callback ─────────────────────────────────────────────────────────

class TestCallbackSuppression:
    def test_callback_not_called_for_suppressed_child(self):
        cb = MagicMock()
        e = AlertEngine(
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, cooldown_s=0)],
            on_alert=cb,
        )
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        e.evaluate_cycle(_cycle({"10.0.0.1": "DOWN", "10.0.0.2": "DOWN"}))
        called_hosts = [call.args[0].host for call in cb.call_args_list]
        assert "10.0.0.2" not in called_hosts
        assert "10.0.0.1" in called_hosts


# ── interaction with flap suppression ────────────────────────────────────────

class TestFlapInteraction:
    def test_both_suppression_types_coexist(self):
        """A host can be independently suppressed by flap OR dependency."""
        e = AlertEngine(rules=[
            AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, cooldown_s=0),
            AlertRule(name="Flap",      rule_type="FLAP",      host=None,
                      flap_count=3, flap_window_s=600, cooldown_s=0),
        ])
        e.set_dependency_map("gw", ["child"])

        # Make child flap (3 transitions) then end on DOWN
        now = 1000
        for state in ["UP", "DOWN", "UP", "DOWN"]:
            e.evaluate_cycle(_cycle({"child": state}, ts=now))
            now += 1

        # Separate parent going down
        alerts = e.evaluate_cycle(_cycle({"gw": "DOWN", "child": "DOWN"}, ts=now + 10))
        child_alerts = [a for a in alerts if a.host == "child" and a.rule_type == "HOST_DOWN"]
        # child should NOT fire HOST_DOWN (suppressed by both dependency AND flap)
        assert not child_alerts

    def test_clear_dependency_map_re_enables_suppression_only_for_dependency(self):
        """After clearing map, flap suppression still works independently."""
        e = AlertEngine(rules=[
            AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, cooldown_s=0),
        ])
        e.set_dependency_map("10.0.0.1", ["10.0.0.2"])
        e.clear_dependency_map()
        alerts = e.evaluate_cycle(_cycle({"10.0.0.1": "DOWN", "10.0.0.2": "DOWN"}))
        hosts = {a.host for a in alerts}
        assert "10.0.0.2" in hosts   # suppression removed

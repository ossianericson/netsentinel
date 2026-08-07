"""
Tests for the tier-based alert scope gate (Signal Quality Phase 2).

The legacy gate is one boolean: `inferred_role in ("gateway","infrastructure")
or alert_opt_in`. Measured against a real 25.4-day database it admitted 53.4 %
of every candidate alert, on the strength of a column that was wrong for 8 of
its 13 assignments.

This replaces it with a floor comparison — `AlertRule.min_tier` against the
device's `device_importance.Tier` — while leaving the legacy path intact and
selected by default, per RULE-EXP1. Both paths are covered here: injecting a
tier provider switches the engine over; injecting nothing must behave exactly
as it did before.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from modules.alert_types import AlertRule
from modules.device_importance import Tier


def _make_engine():
    from modules.alert_engine import AlertEngine
    store = MagicMock()
    store.get_known_devices.return_value = {}
    return AlertEngine(store=store)


def _enable_only(engine, rule_type: str):
    rules = engine.get_rules()
    for r in rules:
        r.enabled = r.rule_type == rule_type
    engine.set_rules(rules)


def _down_cycle(host: str):
    return {
        "devices": [{"ip": host, "mac": "3c:64:cf:e0:27:02", "risk_level": "LOW"}],
        "rtts": {host: -1.0},
        "states": {host: "DOWN"},
        "ts": int(time.time()),
    }


# ── AlertRule.min_tier ───────────────────────────────────────────────────────

def test_alert_rule_min_tier_defaults_to_none():
    """None means "use the engine's default floor" — an existing persisted rule
    must not change behaviour just because the field appeared."""
    assert AlertRule(name="x", rule_type="HOST_DOWN").min_tier is None


def test_alert_rule_accepts_a_tier_name():
    rule = AlertRule(name="x", rule_type="HOST_DOWN", min_tier="critical")
    assert rule.min_tier == "critical"


def test_alert_rule_rejects_an_unknown_tier_name():
    with pytest.raises(ValueError):
        AlertRule(name="x", rule_type="HOST_DOWN", min_tier="important")


def test_alert_rule_normalises_tier_name_case():
    assert AlertRule(name="x", rule_type="HOST_DOWN", min_tier="CRITICAL").min_tier == "critical"


# ── Tier comparison replaces the boolean ─────────────────────────────────────

class TestTierGate:
    def test_device_below_the_default_floor_does_not_fire(self):
        """A Chromecast tiers PERSONAL. It produced 306 state events on the
        reference network and was admitted to every device-scoped rule."""
        engine = _make_engine()
        _enable_only(engine, "HOST_DOWN")
        engine.set_device_tier_provider(lambda host: Tier.PERSONAL)
        assert engine.evaluate_cycle(_down_cycle("192.168.68.54")) == []

    def test_device_at_the_default_floor_fires(self):
        engine = _make_engine()
        _enable_only(engine, "HOST_DOWN")
        engine.set_device_tier_provider(lambda host: Tier.INFRASTRUCTURE)
        assert len(engine.evaluate_cycle(_down_cycle("192.168.68.1"))) == 1

    def test_gateway_still_fires_above_the_floor(self):
        """ACCEPTANCE CRITERION 3 — the gate gets quieter, but never about the
        gateway."""
        engine = _make_engine()
        _enable_only(engine, "HOST_DOWN")
        engine.set_device_tier_provider(lambda host: Tier.CRITICAL)
        assert len(engine.evaluate_cycle(_down_cycle("192.168.68.1"))) == 1

    def test_provider_may_return_a_tier_name_string(self):
        engine = _make_engine()
        _enable_only(engine, "HOST_DOWN")
        engine.set_device_tier_provider(lambda host: "transient")
        assert engine.evaluate_cycle(_down_cycle("192.168.68.99")) == []

    def test_rule_min_tier_raises_the_floor_above_the_default(self):
        engine = _make_engine()
        rules = engine.get_rules()
        for r in rules:
            r.enabled = r.rule_type == "HOST_DOWN"
            if r.rule_type == "HOST_DOWN":
                r.min_tier = "critical"
        engine.set_rules(rules)
        engine.set_device_tier_provider(lambda host: Tier.INFRASTRUCTURE)
        assert engine.evaluate_cycle(_down_cycle("192.168.1.10")) == []

    def test_rule_min_tier_can_lower_the_floor(self):
        engine = _make_engine()
        rules = engine.get_rules()
        for r in rules:
            r.enabled = r.rule_type == "HOST_DOWN"
            if r.rule_type == "HOST_DOWN":
                r.min_tier = "transient"
        engine.set_rules(rules)
        engine.set_device_tier_provider(lambda host: Tier.TRANSIENT)
        assert len(engine.evaluate_cycle(_down_cycle("192.168.1.99"))) == 1

    def test_non_device_scoped_rules_are_never_tier_gated(self):
        """A rogue DHCP server must alert regardless of whose device it is."""
        engine = _make_engine()
        engine.set_device_tier_provider(lambda host: Tier.TRANSIENT)
        assert engine._out_of_scope("192.168.1.50", "ROGUE_DHCP") is False

    def test_a_raising_provider_never_suppresses_an_alert(self):
        engine = _make_engine()

        def boom(host):
            raise RuntimeError("db locked")

        engine.set_device_tier_provider(boom)
        assert engine._out_of_scope("192.168.1.50", "HOST_DOWN") is False

    def test_an_unparseable_tier_falls_back_to_the_default_floor(self):
        engine = _make_engine()
        engine.set_device_tier_provider(lambda host: "wildly-invalid")
        assert engine._out_of_scope("192.168.1.50", "HOST_DOWN") is True


# ── Legacy path is untouched (RULE-EXP1) ─────────────────────────────────────

class TestLegacyPathPreserved:
    def test_boolean_checker_still_used_when_no_tier_provider(self):
        engine = _make_engine()
        engine.set_alert_scope_checker(lambda host: False)
        assert engine._out_of_scope("192.168.1.50", "HOST_DOWN") is True

    def test_tier_provider_takes_precedence_over_the_boolean_checker(self):
        engine = _make_engine()
        engine.set_alert_scope_checker(lambda host: False)
        engine.set_device_tier_provider(lambda host: Tier.CRITICAL)
        assert engine._out_of_scope("192.168.1.1", "HOST_DOWN") is False

    def test_clearing_the_provider_restores_the_legacy_path(self):
        engine = _make_engine()
        engine.set_alert_scope_checker(lambda host: True)
        engine.set_device_tier_provider(lambda host: Tier.TRANSIENT)
        engine.set_device_tier_provider(None)
        assert engine._out_of_scope("192.168.1.1", "HOST_DOWN") is False

    def test_neither_injected_means_everything_in_scope(self):
        engine = _make_engine()
        assert engine._out_of_scope("192.168.1.1", "HOST_DOWN") is False

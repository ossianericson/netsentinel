"""
Tests for alert opt-in behaviour in modules/alert_engine.py

Covers:
  • All default rules are created with enabled=False
  • A disabled rule never fires even when its threshold is exceeded
  • An enabled rule fires when its threshold is exceeded
  • Toggling enabled=True/False at runtime controls firing
  • rule_settings_key() returns a stable, safe QSettings path
  • Cooldown prevents re-firing within the cooldown window
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    from modules.alert_engine import AlertEngine
    store = MagicMock()
    store.get_known_devices.return_value = {}
    return AlertEngine(store=store)


def _make_cycle(host: str = "1.1.1.1", rtt: float = 9999.0, up: bool = True):
    """Build a minimal cycle dict that will trigger RTT / host-down rules."""
    return {
        "devices": [{"ip": host, "mac": "aa:bb:cc:dd:ee:01", "risk_level": "LOW"}],
        "rtts": {host: rtt},
        "states": {host: "UP" if up else "DOWN"},
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# Default rules state
# ---------------------------------------------------------------------------

class TestDefaultRulesDisabled:
    def test_all_default_rules_disabled(self):
        from modules.alert_engine import _default_rules
        rules = _default_rules()
        assert rules, "Expected at least one default rule"
        for rule in rules:
            assert rule.enabled is False, (
                f"Rule '{rule.name}' should default to enabled=False"
            )

    def test_engine_has_default_rules(self):
        engine = _make_engine()
        rules = engine.get_rules()
        assert len(rules) > 0


# ---------------------------------------------------------------------------
# Disabled rule never fires
# ---------------------------------------------------------------------------

class TestDisabledRuleDoesNotFire:
    def test_disabled_rtt_rule_does_not_fire(self):
        engine = _make_engine()
        # Ensure all rules are disabled (default)
        rules = engine.get_rules()
        for r in rules:
            r.enabled = False
        engine.set_rules(rules)
        # RTT way above any threshold
        cycle = _make_cycle(rtt=99999.0)
        fired = engine.evaluate_cycle(cycle)
        assert fired == [], "No alert should fire when all rules are disabled"

    def test_disabled_host_down_does_not_fire(self):
        engine = _make_engine()
        rules = engine.get_rules()
        for r in rules:
            r.enabled = False
        engine.set_rules(rules)
        cycle = _make_cycle(up=False)
        fired = engine.evaluate_cycle(cycle)
        assert fired == []


# ---------------------------------------------------------------------------
# Enabled rule fires when threshold exceeded
# ---------------------------------------------------------------------------

class TestEnabledRuleFires:
    def test_rtt_rule_fires_when_enabled(self):
        engine = _make_engine()
        rules = engine.get_rules()
        # Enable only the RTT_THRESHOLD rule (matched by rule_type)
        for r in rules:
            r.enabled = r.rule_type == "RTT_THRESHOLD"
        engine.set_rules(rules)
        # RTT way above threshold (default 200 ms)
        cycle = _make_cycle(rtt=99999.0)
        fired = engine.evaluate_cycle(cycle)
        assert any(a.rule_type == "RTT_THRESHOLD" for a in fired), (
            "RTT_THRESHOLD rule should fire when rtt is extreme and rule is enabled"
        )

    def test_only_enabled_rule_fires(self):
        engine = _make_engine()
        rules = engine.get_rules()
        rule_types = [r.rule_type for r in rules]
        assert len(rule_types) >= 2, "Need at least 2 rules for this test"
        # Enable only the first rule type
        for r in rules:
            r.enabled = r.rule_type == rule_types[0]
        engine.set_rules(rules)
        fired = engine.evaluate_cycle(_make_cycle(rtt=99999.0, up=False))
        for a in fired:
            assert a.rule_type == rule_types[0], (
                f"Only '{rule_types[0]}' should fire; got '{a.rule_type}'"
            )


# ---------------------------------------------------------------------------
# Runtime toggle
# ---------------------------------------------------------------------------

class TestRuntimeToggle:
    def test_enable_then_disable_stops_firing(self):
        engine = _make_engine()
        rules = engine.get_rules()
        rtt_rule = next((r for r in rules if r.rule_type == "RTT_THRESHOLD"), None)
        if rtt_rule is None:
            return  # rule not present, skip
        rtt_rule.enabled = True
        engine.set_rules(rules)
        # First cycle — should fire
        cycle = _make_cycle(rtt=99999.0)
        fired1 = engine.evaluate_cycle(cycle)
        assert any(a.rule_type == "RTT_THRESHOLD" for a in fired1)
        # Disable and advance time past cooldown
        rtt_rule.enabled = False
        engine.set_rules(rules)
        # Force cooldown to expire
        engine._last_fired.clear()
        cycle2 = _make_cycle(rtt=99999.0)
        fired2 = engine.evaluate_cycle(cycle2)
        assert not any(a.name == "RTT_THRESHOLD" for a in fired2)


# ---------------------------------------------------------------------------
# rule_settings_key
# ---------------------------------------------------------------------------

class TestRuleSettingsKey:
    def test_returns_string(self):
        from modules.alert_engine import rule_settings_key
        key = rule_settings_key("RTT_THRESHOLD")
        assert isinstance(key, str)

    def test_key_contains_safe_path(self):
        from modules.alert_engine import rule_settings_key
        key = rule_settings_key("Host Down")
        # Must be a QSettings-compatible path: no spaces, uses /
        assert " " not in key
        assert "/" in key

    def test_different_names_produce_different_keys(self):
        from modules.alert_engine import rule_settings_key
        k1 = rule_settings_key("RTT_THRESHOLD")
        k2 = rule_settings_key("HOST_DOWN")
        assert k1 != k2


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------

class TestCooldown:
    def test_cooldown_prevents_immediate_refire(self):
        engine = _make_engine()
        rules = engine.get_rules()
        rtt_rule = next((r for r in rules if r.rule_type == "RTT_THRESHOLD"), None)
        if rtt_rule is None:
            return
        rtt_rule.enabled = True
        rtt_rule.cooldown_s = 300
        engine.set_rules(rules)

        ts = time.time()
        cycle1 = {**_make_cycle(rtt=99999.0), "ts": ts}
        cycle2 = {**_make_cycle(rtt=99999.0), "ts": ts + 5}  # 5 s later, within cooldown

        fired1 = engine.evaluate_cycle(cycle1)
        fired2 = engine.evaluate_cycle(cycle2)

        assert any(a.rule_type == "RTT_THRESHOLD" for a in fired1), "Should fire on first cycle"
        assert not any(a.rule_type == "RTT_THRESHOLD" for a in fired2), (
            "Should NOT refire within cooldown window"
        )

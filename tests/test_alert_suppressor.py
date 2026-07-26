"""Tests for modules/alert_suppressor.py — see also test_sprint20_splits.py."""


def test_import():
    from modules import alert_suppressor as m
    assert hasattr(m, "EscalationPolicy")
    assert hasattr(m, "_default_rules")
    assert hasattr(m, "rule_settings_key")


def test_escalation_policy():
    from modules.alert_suppressor import EscalationPolicy
    ep = EscalationPolicy(rule_name="Test", wait_minutes=30)
    assert ep.wait_minutes == 30
    assert ep.enabled is True


def test_default_rules_all_disabled():
    from modules.alert_suppressor import _default_rules
    rules = _default_rules()
    assert len(rules) > 0
    assert all(not r.enabled for r in rules)


def test_every_rule_type_has_a_default_rule():
    """Phase 7.5 -- LOSS_THRESHOLD had no _default_rules() entry, so that
    rule type could never fire regardless of settings."""
    from modules.alert_types import RULE_TYPES
    from modules.alert_suppressor import _default_rules
    default_types = {r.rule_type for r in _default_rules()}
    missing = RULE_TYPES - default_types
    assert missing == set(), f"Rule types with no default rule: {sorted(missing)}"


def test_loss_threshold_default_rule_exists_and_is_disabled():
    from modules.alert_suppressor import _default_rules
    rule = next((r for r in _default_rules() if r.rule_type == "LOSS_THRESHOLD"), None)
    assert rule is not None
    assert rule.enabled is False


def test_rule_settings_key_format():
    from modules.alert_suppressor import rule_settings_key
    assert rule_settings_key("Host Down") == "alert_rules/host_down/enabled"
    assert rule_settings_key("High RTT") == "alert_rules/high_rtt/enabled"

"""Tests for modules/alert_sensitivity.py — V6 Sprint 5.4 alert-fatigue guardrail.

A global sensitivity control (Conservative/Balanced/Aggressive) scales the
noise-relevant numeric fields on every AlertRule so users can dial down a
noisy rule without disabling it outright, and dial up an under-sensitive
one — while the per-rule enable toggles (already shipped in Sprints 1–4)
remain the primary opt-in gate.
"""


def _rule(**overrides):
    from modules.alert_types import AlertRule
    defaults = dict(name="test", rule_type="BASELINE_DROP", cooldown_s=300)
    defaults.update(overrides)
    return AlertRule(**defaults)


def test_import():
    from modules.alert_sensitivity import apply_sensitivity, SENSITIVITY_LEVELS, DEFAULT_SENSITIVITY
    assert apply_sensitivity
    assert DEFAULT_SENSITIVITY in SENSITIVITY_LEVELS
    assert set(SENSITIVITY_LEVELS) == {"conservative", "balanced", "aggressive"}


def test_balanced_leaves_rules_unchanged():
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(warn_pct=50.0, high_pct=75.0, min_samples=4, cooldown_s=300, sigma=2.0)
    apply_sensitivity([rule], "balanced")
    assert rule.warn_pct == 50.0
    assert rule.high_pct == 75.0
    assert rule.min_samples == 4
    assert rule.cooldown_s == 300
    assert rule.sigma == 2.0


def test_conservative_raises_thresholds_and_cooldowns():
    """Conservative = fewer, higher-confidence alerts: bigger drop needed,
    more samples required, longer cooldown between repeats."""
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(warn_pct=50.0, high_pct=75.0, min_samples=4, cooldown_s=300, sigma=2.0)
    apply_sensitivity([rule], "conservative")
    assert rule.warn_pct > 50.0
    assert rule.high_pct > 75.0
    assert rule.min_samples >= 4
    assert rule.cooldown_s > 300
    assert rule.sigma > 2.0


def test_aggressive_lowers_thresholds_and_cooldowns():
    """Aggressive = more, earlier alerts: smaller drop triggers, fewer
    samples needed, shorter cooldown between repeats."""
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(warn_pct=50.0, high_pct=75.0, min_samples=20, cooldown_s=300, sigma=2.0)
    apply_sensitivity([rule], "aggressive")
    assert rule.warn_pct < 50.0
    assert rule.high_pct < 75.0
    assert rule.min_samples <= 20
    assert rule.cooldown_s < 300
    assert rule.sigma < 2.0


def test_min_samples_never_drops_below_floor():
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(min_samples=2)
    apply_sensitivity([rule], "aggressive")
    assert rule.min_samples >= 2


def test_cooldown_never_drops_below_floor():
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(cooldown_s=30)
    apply_sensitivity([rule], "aggressive")
    assert rule.cooldown_s >= 30


def test_unknown_level_is_treated_as_balanced():
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(warn_pct=50.0)
    apply_sensitivity([rule], "not-a-real-level")
    assert rule.warn_pct == 50.0


def test_threshold_ms_scaled_for_rtt_rules():
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(rule_type="RTT_THRESHOLD", threshold_ms=200.0)
    apply_sensitivity([rule], "conservative")
    assert rule.threshold_ms > 200.0


def test_disabled_rules_are_still_scaled():
    """Scaling applies regardless of enabled state — enable/disable and
    sensitivity are independent knobs."""
    from modules.alert_sensitivity import apply_sensitivity
    rule = _rule(warn_pct=50.0, enabled=False)
    apply_sensitivity([rule], "conservative")
    assert rule.warn_pct > 50.0
    assert rule.enabled is False


def test_apply_sensitivity_mutates_all_rules_in_list():
    from modules.alert_sensitivity import apply_sensitivity
    rules = [_rule(warn_pct=50.0), _rule(name="b", warn_pct=40.0)]
    apply_sensitivity(rules, "aggressive")
    assert rules[0].warn_pct < 50.0
    assert rules[1].warn_pct < 40.0

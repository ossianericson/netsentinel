"""Tests for modules/alert_engine_routing.py (RULE-AH1 split from alert_engine.py)."""
from __future__ import annotations


def test_import():
    from modules.alert_engine_routing import RULE_CTA, cta_for_rule, ACTION_STEPS, append_action
    assert RULE_CTA is not None
    assert cta_for_rule is not None
    assert ACTION_STEPS is not None
    assert append_action is not None


def test_cta_for_rule_known_and_unknown():
    from modules.alert_engine_routing import cta_for_rule
    page, host = cta_for_rule("HOST_DOWN", "192.168.1.1")
    assert page == "Inventory"
    assert host == "192.168.1.1"

    page, host = cta_for_rule("NOT_A_REAL_RULE", "192.168.1.1")
    assert page is None
    assert host is None


def test_append_action_adds_step_once():
    from modules.alert_engine_routing import append_action
    msg = append_action("Host is down.", "HOST_DOWN")
    assert "Check the device is powered on" in msg
    # Calling again on the already-appended message must not duplicate the step.
    msg2 = append_action(msg, "HOST_DOWN")
    assert msg2 == msg


def test_append_action_unknown_rule_type_is_noop():
    from modules.alert_engine_routing import append_action
    msg = append_action("Something happened.", "NOT_A_REAL_RULE")
    assert msg == "Something happened."


def test_new_v6_sprint4_rule_types_have_cta_and_action():
    from modules.alert_engine_routing import RULE_CTA, ACTION_STEPS
    for rule_type in ("ARP_SPOOF", "ROGUE_DHCP", "CONFIG_DRIFT"):
        assert rule_type in RULE_CTA
        assert rule_type in ACTION_STEPS


def test_action_steps_covers_every_rule_type():
    """Phase 7.1 -- 8 of 25 rule types had no ACTION_STEPS entry at all."""
    from modules.alert_types import RULE_TYPES
    from modules.alert_engine_routing import ACTION_STEPS
    missing = RULE_TYPES - set(ACTION_STEPS)
    assert missing == set(), f"Missing ACTION_STEPS entries: {sorted(missing)}"


def test_rule_cta_covers_every_rule_type():
    from modules.alert_types import RULE_TYPES
    from modules.alert_engine_routing import RULE_CTA
    missing = RULE_TYPES - set(RULE_CTA)
    assert missing == set(), f"Missing RULE_CTA entries: {sorted(missing)}"

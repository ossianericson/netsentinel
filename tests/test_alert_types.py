"""Tests for modules/alert_types.py — AlertRule, AlertFired, RULE_TYPES."""
import pytest


def test_import():
    from modules.alert_types import AlertRule, AlertFired, RULE_TYPES
    assert AlertRule is not None
    assert AlertFired is not None
    assert RULE_TYPES is not None


def test_rule_types_is_frozenset():
    from modules.alert_types import RULE_TYPES
    assert isinstance(RULE_TYPES, frozenset)
    assert "RTT_THRESHOLD" in RULE_TYPES
    assert "HOST_DOWN" in RULE_TYPES
    assert "CERT_EXPIRY" in RULE_TYPES
    assert "SERVICE_DOWN" in RULE_TYPES


def test_alert_rule_valid():
    from modules.alert_types import AlertRule
    r = AlertRule(name="test", rule_type="HOST_DOWN")
    assert r.rule_type == "HOST_DOWN"
    assert r.enabled is True


def test_alert_rule_normalises_case():
    from modules.alert_types import AlertRule
    r = AlertRule(name="test", rule_type="host_down")
    assert r.rule_type == "HOST_DOWN"


def test_alert_rule_invalid_type():
    from modules.alert_types import AlertRule
    with pytest.raises(ValueError, match="Unknown rule_type"):
        AlertRule(name="bad", rule_type="NONEXISTENT")


def test_alert_fired_fields():
    from modules.alert_types import AlertFired
    af = AlertFired(
        rule_name="r",
        rule_type="HOST_DOWN",
        host="192.168.1.1",
        message="down",
        severity="CRITICAL",
        ts=1000,
    )
    assert af.host == "192.168.1.1"
    assert af.is_resolution is False
    assert af.value is None


def test_alert_fired_remediation_field_defaults_empty():
    """Phase 7.4 -- per-alert remediation override; '' means 'use the
    alert_remediation table'. Added as the LAST field so every existing
    positional/keyword construction stays valid."""
    from modules.alert_types import AlertFired
    af = AlertFired(
        rule_name="r", rule_type="HOST_DOWN", host="192.168.1.1",
        message="down", severity="CRITICAL", ts=1000,
    )
    assert af.remediation == ""


def test_alert_fired_remediation_field_can_be_set():
    from modules.alert_types import AlertFired
    af = AlertFired(
        rule_name="r", rule_type="IOT_BEHAVIOR", host="192.168.1.1",
        message="new destination", severity="WARNING", ts=1000,
        remediation="Block this device in your router.",
    )
    assert af.remediation == "Block this device in your router."


def test_alert_types_re_exported_from_alert_engine():
    """alert_engine.py must still export AlertRule, AlertFired, RULE_TYPES for backward compat."""
    from modules.alert_engine import AlertRule, AlertFired, RULE_TYPES
    assert AlertRule is not None
    assert AlertFired is not None
    assert RULE_TYPES is not None

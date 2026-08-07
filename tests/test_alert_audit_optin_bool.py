"""RULES_OPT_IN must not depend on QSettings' boolean representation.

Found by running `python app.py --audit` with rules genuinely enabled for the
first time (the acceptance-criterion-5 live verification armed five of them).

`app.py`'s audit path reads rule state with an explicit type — `qs.value(key,
False, type=bool)` — so `AlertRule.enabled` is a real `True`. But the
`settings_get` callable it hands to `audit_alert_config()` is
`lambda key, default=None: qs.value(key, default)`, with no `type=`. On Windows
QSettings uses NativeFormat (the registry), which returns booleans as the
*string* `"true"`. `RULES_OPT_IN` compared with `is not True`, so `"true" is
not True` — and every genuinely enabled rule was reported as "enabled without a
matching opt-in setting".

The check has only ever been exercised in its passing state, because all 25
built-in rules ship `enabled=False`; nothing was enabled, so nothing was
compared. Phase 6's curated default-on set (acceptance criterion 7) turns rules
on by default, which would have made this fire for every user.

`alert_audit.py` already owns `_truthy()` and already uses it for TOAST_OPT_IN,
which reads the same kind of value — this is the same fix applied to the check
that was missed.
"""
from __future__ import annotations

import pytest

from modules.alert_audit import audit_alert_config
from modules.alert_suppressor import rule_settings_key
from modules.alert_types import AlertRule


def _rules():
    return [AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None,
                      enabled=True)]


def _find(findings, name):
    return next(f for f in findings if f.code == name)


@pytest.mark.parametrize("stored", [True, "true", "True", 1, "1"])
def test_truthy_optin_representations_all_pass(stored):
    """Every shape QSettings can hand back for a set boolean must count."""
    rules = _rules()

    def settings_get(key, default=None):
        if key == rule_settings_key("Host Down"):
            return stored
        return default

    findings = audit_alert_config(settings_get, rules, [], [])
    f = _find(findings, "RULES_OPT_IN")
    assert f.ok, f.detail


@pytest.mark.parametrize("stored", [False, "false", "False", 0, "0", None])
def test_a_rule_enabled_without_its_optin_is_still_caught(stored):
    """The check must keep catching the real defect it exists for."""
    rules = _rules()

    def settings_get(key, default=None):
        if key == rule_settings_key("Host Down"):
            return stored
        return default

    findings = audit_alert_config(settings_get, rules, [], [])
    f = _find(findings, "RULES_OPT_IN")
    assert not f.ok
    assert "Host Down" in f.detail


def test_a_disabled_rule_is_never_flagged():
    rules = [AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None,
                       enabled=False)]
    findings = audit_alert_config(lambda k, d=None: d, rules, [], [])
    assert _find(findings, "RULES_OPT_IN").ok

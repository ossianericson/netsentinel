"""
Phase 7.2 -- modules/alert_remediation.py.

Moves ui/widgets/alert_drawer.py's _RULE_FIX table out of Qt so it is
unit-testable and reusable. REMEDIATION is keyed by the 25 canonical
RULE_TYPES; remediation_for() falls back to the legacy substring-on-rule_name
match for alert_fired rows written before rule_type was persisted.
"""
from __future__ import annotations


def test_remediation_covers_every_rule_type():
    from modules.alert_types import RULE_TYPES
    from modules.alert_remediation import REMEDIATION
    missing = RULE_TYPES - set(REMEDIATION)
    assert missing == set(), f"Missing REMEDIATION entries: {sorted(missing)}"


def test_every_entry_is_non_empty_text():
    from modules.alert_remediation import REMEDIATION
    for rule_type, text in REMEDIATION.items():
        assert isinstance(text, str) and text.strip(), f"{rule_type} has empty remediation text"


def test_prefers_canonical_rule_type():
    from modules.alert_remediation import remediation_for, REMEDIATION
    result = remediation_for("HOST_DOWN")
    assert result == REMEDIATION["HOST_DOWN"]


def test_falls_back_to_legacy_substring_match_on_rule_name():
    """A pre-rule_type alert_fired row has rule_type='' but a rule_name like
    'ARP Spoof Detected' -- the OLD ui/widgets/alert_drawer.py behaviour
    matched 'ARP' as a substring of the upper-cased rule_name."""
    from modules.alert_remediation import remediation_for
    result = remediation_for("", rule_name="ARP Spoof Detected")
    assert result != ""
    assert "ARP" in result.upper() or "impersonation" in result.lower()


def test_legacy_fallback_covers_threat_intel_and_bandwidth():
    """THREAT_INTEL and BANDWIDTH have no RULE_TYPES counterpart at all --
    they must still resolve via the legacy rule_name path, not disappear."""
    from modules.alert_remediation import remediation_for
    assert remediation_for("", rule_name="THREAT_INTEL_MATCH") != ""
    assert remediation_for("", rule_name="BANDWIDTH_SPIKE") != ""


def test_unknown_rule_type_and_name_returns_empty_string():
    from modules.alert_remediation import remediation_for
    assert remediation_for("NOT_A_REAL_TYPE", rule_name="Nonsense Rule") == ""


def test_unknown_rule_type_with_no_rule_name_returns_empty_string():
    from modules.alert_remediation import remediation_for
    assert remediation_for("NOT_A_REAL_TYPE") == ""


def test_canonical_rule_type_takes_priority_over_legacy_name_match():
    """Even if rule_name would ALSO match a legacy substring, an explicit
    canonical rule_type always wins -- no ambiguity."""
    from modules.alert_remediation import remediation_for, REMEDIATION
    result = remediation_for("CERT_EXPIRED", rule_name="Cert Expiring")
    assert result == REMEDIATION["CERT_EXPIRED"]

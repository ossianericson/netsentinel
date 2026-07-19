"""
Regression tests for critical-UX Phase 1.3 + addendum: suggestion rules
pointed at pages with no data, or with no way to discover the page at all.

_rule_high_risk and _rule_poor_grade both originally targeted "Dashboard" ->
_overview_page, whose tile registry has no risk tile at all.

_rule_poor_grade now targets "Security Overview", which genuinely renders a
grade.

_rule_high_risk now targets "Devices": that page's per-device notes column
(recognised vendor + known network issues) is populated by the same M1 scan
pass that computes high_risk_count itself (modules/rogue_device.py), so it is
never out of sync -- no guard needed. A separate, lower-priority suggestion
(_rule_risk_remediation_available) points at "Device Risk Score" -- a
genuinely additive destination (dedicated top_remediation column from
modules.risk_scorer.score_devices()), but only once that separate pipeline
has actually produced data, since it can lag or fail independently of the
M1 scan.

RULE-T3: must fail before the fix (_rule_high_risk still targets "Device
Risk Score" and is gated on risk_assessments_available; the remediation
suggestion doesn't exist yet).
"""
from __future__ import annotations

from modules.suggestion_engine import SuggestionContext, compute_suggestions


def _by_key(suggestions):
    return {s["action_key"]: s for s in suggestions}


def test_high_risk_targets_devices_page():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=2, risk_assessments_available=False,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "high_risk_check" in got
    assert got["high_risk_check"]["target"] == "Devices"


def test_high_risk_emits_without_risk_assessment_data():
    """No guard on the primary rule -- Devices' notes column is populated by
    the same scan pass as high_risk_count, so it's always in sync."""
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=2, risk_assessments_available=False,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "high_risk_check" in got


def test_high_risk_does_not_emit_when_count_is_zero():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=0, risk_assessments_available=True,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "high_risk_check" not in got


def test_poor_grade_targets_security_overview_page():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        overall_grade="D",
    )
    got = _by_key(compute_suggestions(ctx))
    assert "fix_network_grade" in got
    assert got["fix_network_grade"]["target"] == "Security Overview"


# ── Secondary "View remediation steps" suggestion ────────────────────────────

def test_risk_remediation_fires_when_assessments_available():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=2, risk_assessments_available=True,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "risk_remediation_available" in got
    assert got["risk_remediation_available"]["target"] == "Device Risk Score"
    assert got["risk_remediation_available"]["priority"] == "low"


def test_risk_remediation_absent_without_assessments():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=2, risk_assessments_available=False,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "risk_remediation_available" not in got


def test_risk_remediation_absent_when_no_high_risk_devices():
    ctx = SuggestionContext(
        has_scan_result=True, logger_running=True, logger_started_once=True,
        high_risk_count=0, risk_assessments_available=True,
    )
    got = _by_key(compute_suggestions(ctx))
    assert "risk_remediation_available" not in got

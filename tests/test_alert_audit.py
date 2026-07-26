"""
Tests for modules/alert_audit.py — the --audit-alerts diagnostic.

audit_alert_config() and audit_static_coverage() are pure-function checks
against synthetic input, so they are green from day one. audit_source_tree()
checks the real repo tree and is expected to FAIL some codes until the phase
that fixes the underlying call site lands (documented per-test below).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _finding(findings, code):
    return next(f for f in findings if f.code == code)


# ── audit_alert_config ────────────────────────────────────────────────────────

class TestToastOptIn:
    def test_fails_when_setting_off_but_channel_enabled(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import ToastChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: False if k == "notif/toast_enabled" else d,
            rules=[], channels=[ToastChannel(enabled=True)], escalation_policies=[],
        )
        assert _finding(findings, "TOAST_OPT_IN").ok is False

    def test_passes_when_setting_off_and_channel_disabled(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import ToastChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: False if k == "notif/toast_enabled" else d,
            rules=[], channels=[ToastChannel(enabled=False)], escalation_policies=[],
        )
        assert _finding(findings, "TOAST_OPT_IN").ok is True

    def test_passes_when_setting_on_and_channel_enabled(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import ToastChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: True if k == "notif/toast_enabled" else d,
            rules=[], channels=[ToastChannel(enabled=True)], escalation_policies=[],
        )
        assert _finding(findings, "TOAST_OPT_IN").ok is True


class TestRulesOptIn:
    def test_fails_when_rule_enabled_but_setting_missing(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule

        rule = AlertRule(name="High RTT", rule_type="RTT_THRESHOLD", enabled=True)
        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[rule], channels=[], escalation_policies=[],
        )
        assert _finding(findings, "RULES_OPT_IN").ok is False

    def test_passes_when_rule_enabled_and_setting_matches(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule
        from modules.alert_suppressor import rule_settings_key

        rule = AlertRule(name="High RTT", rule_type="RTT_THRESHOLD", enabled=True)
        key = rule_settings_key(rule.name)
        findings = audit_alert_config(
            settings_get=lambda k, d=None: True if k == key else d,
            rules=[rule], channels=[], escalation_policies=[],
        )
        assert _finding(findings, "RULES_OPT_IN").ok is True

    def test_passes_when_no_rules_enabled(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule

        rule = AlertRule(name="High RTT", rule_type="RTT_THRESHOLD", enabled=False)
        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[rule], channels=[], escalation_policies=[],
        )
        assert _finding(findings, "RULES_OPT_IN").ok is True


class TestChannelCreds:
    def test_fails_when_pushover_enabled_without_token(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import PushoverChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d, rules=[],
            channels=[PushoverChannel(enabled=True, api_token="", user_key="u")],
            escalation_policies=[],
        )
        assert _finding(findings, "CHANNEL_CREDS").ok is False

    def test_passes_when_pushover_enabled_with_creds(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import PushoverChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d, rules=[],
            channels=[PushoverChannel(enabled=True, api_token="t", user_key="u")],
            escalation_policies=[],
        )
        assert _finding(findings, "CHANNEL_CREDS").ok is True

    def test_passes_when_channel_disabled_regardless_of_creds(self):
        from modules.alert_audit import audit_alert_config
        from modules.notification_router import EmailChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d, rules=[],
            channels=[EmailChannel(enabled=False, smtp_host="", to_addrs=[])],
            escalation_policies=[],
        )
        assert _finding(findings, "CHANNEL_CREDS").ok is True


class TestNoOrphanKeys:
    def test_fails_when_an_orphan_key_has_a_value(self):
        from modules.alert_audit import audit_alert_config

        findings = audit_alert_config(
            settings_get=lambda k, d=None: "smtp.example.com" if k == "notifications/smtp_host" else d,
            rules=[], channels=[], escalation_policies=[],
        )
        assert _finding(findings, "NO_ORPHAN_KEYS").ok is False

    def test_passes_when_all_orphan_keys_empty(self):
        from modules.alert_audit import audit_alert_config

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d, rules=[], channels=[], escalation_policies=[],
        )
        assert _finding(findings, "NO_ORPHAN_KEYS").ok is True


class TestEscalationRules:
    def test_fails_when_policy_names_unknown_rule(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule
        from modules.alert_suppressor import EscalationPolicy

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN")],
            channels=[],
            escalation_policies=[EscalationPolicy(rule_name="host down")],
        )
        assert _finding(findings, "ESCALATION_RULES").ok is False

    def test_passes_when_policy_names_match_exactly(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule
        from modules.alert_suppressor import EscalationPolicy

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN")],
            channels=[],
            escalation_policies=[EscalationPolicy(rule_name="Host Down")],
        )
        assert _finding(findings, "ESCALATION_RULES").ok is True


class TestDeliverability:
    def test_fails_when_enabled_rule_has_no_matching_channel(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule
        from modules.notification_router import ToastChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN", enabled=True)],
            channels=[ToastChannel(enabled=False)],
            escalation_policies=[],
        )
        f = _finding(findings, "DELIVERABILITY")
        assert f.ok is False
        assert "Host Down" in f.detail

    def test_passes_when_enabled_rule_has_a_matching_channel(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule
        from modules.notification_router import ToastChannel

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN", enabled=True)],
            channels=[ToastChannel(enabled=True, min_severity="INFO")],
            escalation_policies=[],
        )
        assert _finding(findings, "DELIVERABILITY").ok is True

    def test_disabled_rules_are_not_checked(self):
        from modules.alert_audit import audit_alert_config
        from modules.alert_types import AlertRule

        findings = audit_alert_config(
            settings_get=lambda k, d=None: d,
            rules=[AlertRule(name="Host Down", rule_type="HOST_DOWN", enabled=False)],
            channels=[],
            escalation_policies=[],
        )
        assert _finding(findings, "DELIVERABILITY").ok is True


# ── audit_static_coverage ─────────────────────────────────────────────────────

class TestStaticCoverage:
    def test_action_coverage_passes_after_phase_7(self):
        """Phase 7.1 added the 8 missing ACTION_STEPS entries."""
        from modules.alert_audit import audit_static_coverage

        findings = audit_static_coverage()
        f = _finding(findings, "ACTION_COVERAGE")
        assert f.ok is True

    def test_cta_coverage_passes_today(self):
        """RULE_CTA already covers every rule type — this should be green from day one."""
        from modules.alert_audit import audit_static_coverage

        findings = audit_static_coverage()
        assert _finding(findings, "CTA_COVERAGE").ok is True

    def test_remediation_coverage_passes_after_phase_7(self):
        from modules.alert_audit import audit_static_coverage

        findings = audit_static_coverage()
        f = _finding(findings, "REMEDIATION_COVERAGE")
        assert f.ok is True

    def test_rule_type_coverage_passes_after_phase_7(self):
        """Phase 7.5 added the missing LOSS_THRESHOLD default rule."""
        from modules.alert_audit import audit_static_coverage

        findings = audit_static_coverage()
        f = _finding(findings, "RULE_TYPE_COVERAGE")
        assert f.ok is True

    def test_severity_vocab_passes_after_phase_4(self):
        """Phase 4 added HEALTHY/HIGH/MEDIUM to _SEVERITY_ORDER."""
        from modules.alert_audit import audit_static_coverage

        findings = audit_static_coverage()
        f = _finding(findings, "SEVERITY_VOCAB")
        assert f.ok is True


# ── audit_source_tree ─────────────────────────────────────────────────────────

class TestSourceTree:
    def test_toast_call_sites_passes_after_phase_1(self):
        """Phase 1 repointed every direct call site to _surface_alert_in_app();
        _show_alert_toast now has exactly one caller (app.py's set_toast_callback)."""
        from modules.alert_audit import audit_source_tree

        findings = audit_source_tree(REPO_ROOT)
        f = _finding(findings, "TOAST_CALL_SITES")
        assert f.ok is True

    def test_ungated_tray_passes_after_phase_2(self):
        """Weekly-digest dup, config-drift dup, and the raw ARP balloon are
        gated/removed by Phase 2; every remaining show_notification() call
        site is in the ALLOWED_TRAY_FUNCTIONS allow-list."""
        from modules.alert_audit import audit_source_tree

        findings = audit_source_tree(REPO_ROOT)
        f = _finding(findings, "UNGATED_TRAY")
        assert f.ok is True


# ── channels_from_settings ────────────────────────────────────────────────────

class TestChannelsFromSettings:
    def test_builds_six_channels_from_empty_settings(self):
        from modules.alert_audit import channels_from_settings

        channels = channels_from_settings(
            settings_get=lambda k, d=None: d, secret_get=lambda k: "",
        )
        assert len(channels) == 6
        assert all(ch.enabled is False for ch in channels)

    def test_pushover_enabled_only_when_both_secrets_present(self):
        from modules.alert_audit import channels_from_settings
        from modules.notification_router import PushoverChannel

        settings = {"notif/pushover_enabled": True}
        channels = channels_from_settings(
            settings_get=lambda k, d=None: settings.get(k, d),
            secret_get=lambda k: "tok" if k == "notif/pushover_token" else "",
        )
        po = next(c for c in channels if isinstance(c, PushoverChannel))
        assert po.enabled is False  # missing user_key secret

        channels = channels_from_settings(
            settings_get=lambda k, d=None: settings.get(k, d),
            secret_get=lambda k: "secret",
        )
        po = next(c for c in channels if isinstance(c, PushoverChannel))
        assert po.enabled is True


# ── format_findings ────────────────────────────────────────────────────────────

class TestFormatFindings:
    def test_text_format_includes_pass_fail_and_summary(self):
        from modules.alert_audit import AuditFinding, format_findings

        findings = [AuditFinding("A", True, "ok"), AuditFinding("B", False, "bad")]
        text = format_findings(findings)
        assert "PASS  A  ok" in text
        assert "FAIL  B  bad" in text
        assert "1/2 checks passed" in text

    def test_json_format_round_trips(self):
        import json
        from modules.alert_audit import AuditFinding, format_findings

        findings = [AuditFinding("A", True, "ok")]
        data = json.loads(format_findings(findings, as_json=True))
        assert data == [{"code": "A", "ok": True, "detail": "ok"}]


def test_app_exposes_audit_alerts_flag():
    """AST-scan app.py for the '--audit-alerts' literal (RULE-T4 companion)."""
    import ast

    tree = ast.parse((REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    found = any(
        isinstance(node, ast.Constant) and node.value == "--audit-alerts"
        for node in ast.walk(tree)
    )
    assert found, "app.py must reference the literal '--audit-alerts'"

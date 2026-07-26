"""
alert_audit.py — pure-Python self-test for the alert/notification pipeline.

Encodes the invariants that make NetSentinel's alerting strictly opt-in and
every alert actionable. Each check returns an AuditFinding; nothing here
raises on a failed invariant — a FAIL is a normal, expected result until the
phase that fixes the underlying defect lands.

Driven by ``python app.py --audit-alerts`` (app.py's CLI entry point) and
exercised directly by tests/test_alert_audit.py against synthetic input, so
this module stays PyQt-free (ARCH RULE 3) and has no QSettings/QApplication
dependency of its own — callers inject a settings_get callable.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass
class AuditFinding:
    code:   str    # stable machine code, e.g. "TOAST_OPT_IN"
    ok:     bool
    detail: str    # one human-readable line


def _truthy(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


# ── Orphan QSettings keys — read somewhere, written nowhere (defect 5/6) ──────

_ORPHAN_KEYS = (
    "notifications/smtp_host", "notifications/smtp_port", "notifications/smtp_user",
    "notifications/email_address", "notifications/webhook_url",
    "notifications/pushover_user_key", "notifications/telegram_chat_id",
    "notifications/ntfy_topic_url",
    "tray/alerts_enabled", "digest/enabled", "digest/email",
    "notif/any_rule_enabled",
)

# ── Typical severity per rule_type — used only to test channel deliverability,
#    not persisted or asserted anywhere else in the app. ──────────────────────

_TYPICAL_SEVERITY: Dict[str, str] = {
    "RTT_THRESHOLD": "WARNING", "LOSS_THRESHOLD": "CRITICAL", "HOST_DOWN": "CRITICAL",
    "HOST_DEGRADED": "WARNING", "NEW_DEVICE": "WARNING", "DEVICE_GONE": "WARNING",
    "CERT_EXPIRY": "WARNING", "CERT_EXPIRED": "CRITICAL", "FLAP": "WARNING",
    "SERVICE_DOWN": "CRITICAL", "BASELINE_DROP": "WARNING", "JITTER_HIGH": "WARNING",
    "MESH_DEGRADED": "WARNING", "MODEM_SIGNAL_DROP": "WARNING", "GRADE_REGRESSION": "WARNING",
    "IP_CHURN": "WARNING", "RTT_ANOMALY": "WARNING", "IOT_BEHAVIOR": "WARNING",
    "TREND_FORECAST": "INFO", "NEW_OPEN_PORT": "WARNING", "NEW_CVE": "WARNING",
    "NEW_EXPOSURE": "WARNING", "ARP_SPOOF": "CRITICAL", "ROGUE_DHCP": "CRITICAL",
    "CONFIG_DRIFT": "WARNING",
}

# ── Required credential fields per channel type (defect 4/8) ─────────────────

_REQUIRED_CREDS: Dict[str, tuple] = {
    "PushoverChannel": ("api_token", "user_key"),
    "TelegramChannel": ("bot_token", "chat_id"),
    "EmailChannel": ("smtp_host", "to_addrs"),
    "NtfyChannel": ("topic_url",),
    "WebhookChannel": ("url",),
}


def audit_alert_config(
    settings_get: Callable[[str, Any], Any],
    rules: list,
    channels: list,
    escalation_policies: list,
) -> List[AuditFinding]:
    from modules.alert_suppressor import rule_settings_key
    from modules.notification_router import ToastChannel, _severity_gte

    findings: List[AuditFinding] = []

    # RULES_OPT_IN
    mismatched = [
        r.name for r in rules
        if r.enabled and settings_get(rule_settings_key(r.name), False) is not True
    ]
    findings.append(AuditFinding(
        "RULES_OPT_IN", not mismatched,
        "Every enabled rule has a matching opt-in setting" if not mismatched
        else f"Rules enabled without a matching opt-in setting: {', '.join(mismatched)}",
    ))

    # TOAST_OPT_IN
    toast_setting_on = _truthy(settings_get("notif/toast_enabled", False))
    stray_toast = any(isinstance(ch, ToastChannel) and ch.enabled for ch in channels) and not toast_setting_on
    findings.append(AuditFinding(
        "TOAST_OPT_IN", not stray_toast,
        "No enabled ToastChannel while notif/toast_enabled is off" if not stray_toast
        else "notif/toast_enabled is off but an enabled ToastChannel exists — balloons would still show",
    ))

    # CHANNEL_CREDS
    cred_gaps = []
    for ch in channels:
        if not getattr(ch, "enabled", False):
            continue
        required = _REQUIRED_CREDS.get(type(ch).__name__)
        if not required:
            continue
        missing = [f for f in required if not getattr(ch, f, None)]
        if missing:
            cred_gaps.append(f"{type(ch).__name__} missing {', '.join(missing)}")
    findings.append(AuditFinding(
        "CHANNEL_CREDS", not cred_gaps,
        "Every enabled channel has its required credentials" if not cred_gaps
        else "; ".join(cred_gaps),
    ))

    # NO_ORPHAN_KEYS
    populated = [k for k in _ORPHAN_KEYS if settings_get(k, "") not in ("", False, None)]
    findings.append(AuditFinding(
        "NO_ORPHAN_KEYS", not populated,
        "No orphan settings keys are populated" if not populated
        else f"Orphan keys with a stored value: {', '.join(populated)}",
    ))

    # ESCALATION_RULES
    rule_names = {r.name for r in rules}
    unknown_policies = [p.rule_name for p in escalation_policies if p.rule_name not in rule_names]
    findings.append(AuditFinding(
        "ESCALATION_RULES", not unknown_policies,
        "Every escalation policy names a real rule" if not unknown_policies
        else f"Escalation policies naming an unknown rule: {', '.join(unknown_policies)}",
    ))

    # DELIVERABILITY
    undeliverable = []
    for r in rules:
        if not r.enabled:
            continue
        typical = _TYPICAL_SEVERITY.get(r.rule_type, "WARNING")
        deliverable = any(
            getattr(ch, "enabled", False)
            and _severity_gte(typical, ch.min_severity)
            and (not ch.rule_types or r.rule_type in ch.rule_types)
            for ch in channels
        )
        if not deliverable:
            undeliverable.append(r.name)
    findings.append(AuditFinding(
        "DELIVERABILITY", not undeliverable,
        "Every enabled rule has at least one channel that would accept it" if not undeliverable
        else f"Enabled rules with no channel that would ever deliver them: {', '.join(undeliverable)}",
    ))

    return findings


def audit_static_coverage() -> List[AuditFinding]:
    from modules.alert_types import RULE_TYPES
    from modules.alert_engine_routing import ACTION_STEPS, RULE_CTA
    from modules.notification_router import _SEVERITY_ORDER
    from modules.alert_suppressor import _default_rules

    findings: List[AuditFinding] = []

    missing_action = sorted(RULE_TYPES - set(ACTION_STEPS))
    findings.append(AuditFinding(
        "ACTION_COVERAGE", not missing_action,
        "ACTION_STEPS covers every rule type" if not missing_action
        else f"Missing ACTION_STEPS entries: {', '.join(missing_action)}",
    ))

    missing_cta = sorted(RULE_TYPES - set(RULE_CTA))
    findings.append(AuditFinding(
        "CTA_COVERAGE", not missing_cta,
        "RULE_CTA covers every rule type" if not missing_cta
        else f"Missing RULE_CTA entries: {', '.join(missing_cta)}",
    ))

    try:
        from modules.alert_remediation import REMEDIATION
        missing_rem = sorted(RULE_TYPES - set(REMEDIATION))
        findings.append(AuditFinding(
            "REMEDIATION_COVERAGE", not missing_rem,
            "REMEDIATION covers every rule type" if not missing_rem
            else f"Missing REMEDIATION entries: {', '.join(missing_rem)}",
        ))
    except ModuleNotFoundError:
        findings.append(AuditFinding(
            "REMEDIATION_COVERAGE", False, "modules.alert_remediation does not exist yet",
        ))

    default_types = {r.rule_type for r in _default_rules()}
    missing_default = sorted(RULE_TYPES - default_types)
    findings.append(AuditFinding(
        "RULE_TYPE_COVERAGE", not missing_default,
        "Every rule type has a _default_rules() entry" if not missing_default
        else f"Rule types with no default rule: {', '.join(missing_default)}",
    ))

    required_vocab = {"INFO", "WARNING", "CRITICAL", "HEALTHY", "HIGH", "MEDIUM"}
    missing_vocab = sorted(required_vocab - set(_SEVERITY_ORDER))
    findings.append(AuditFinding(
        "SEVERITY_VOCAB", not missing_vocab,
        "Severity vocabulary is complete" if not missing_vocab
        else f"Missing from _SEVERITY_ORDER: {', '.join(missing_vocab)}",
    ))

    return findings


# ── Source-tree AST guards ────────────────────────────────────────────────────

def _target_py_files(repo_root: Path) -> List[Path]:
    files = [repo_root / "app.py"]
    files.extend(sorted((repo_root / "ui").rglob("*.py")))
    return [f for f in files if f.is_file()]


class _ToastSiteVisitor(ast.NodeVisitor):
    """Counts real identifier references to _show_alert_toast — ignores
    docstrings/comments, which are not identifiers in the AST."""

    def __init__(self) -> None:
        self.sites: List[int] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name == "_show_alert_toast":
            self.sites.append(node.lineno)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "_show_alert_toast":
            self.sites.append(node.lineno)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "_show_alert_toast":
            self.sites.append(node.lineno)
        self.generic_visit(node)


# Final allow-list (post-Phase 2): every show_notification() call site in
# ui/**/*.py or app.py must be lexically inside one of these functions. Each
# entry's justification is the gate that already protects it.
ALLOWED_TRAY_FUNCTIONS: Dict[str, str] = {
    "_show_alert_toast":         "router-gated — NotificationRouter already applied "
                                  "snooze + ToastChannel.enabled + min_severity + rule_types",
    "closeEvent":                "one-time hide-to-tray hint, gated on tray/hide_hint_shown",
    "_check_weekly_digest":      "gated on notif/weekly_digest_enabled",
    "_m1_track_devices":         "gated on tray/notify_new_device / tray/notify_device_gone",
    "main":                      "quiet notifier — gated on alerts/quiet_notify_enabled",
    "_do_morning_briefing_check": "gated on briefing/enabled",
}


class _ShowNotificationVisitor(ast.NodeVisitor):
    """Records (enclosing_function_name, lineno) for every .show_notification(
    call — enclosing function is the innermost def/async def, or "<module>"
    for a call made at module scope."""

    def __init__(self) -> None:
        self.sites: List[tuple] = []
        self._stack: List[str] = []

    def _visit_func(self, node) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "show_notification":
            funcname = self._stack[-1] if self._stack else "<module>"
            self.sites.append((funcname, node.lineno))
        self.generic_visit(node)


def audit_source_tree(repo_root: Path) -> List[AuditFinding]:
    """AST checks against the real repo tree — CLI-only durable regression
    guards. Expected to FAIL some codes until the phase that fixes the
    underlying call site lands; see ALLOWED_TRAY_FUNCTIONS above."""
    findings: List[AuditFinding] = []
    files = _target_py_files(repo_root)

    toast_sites: List[str] = []
    tray_sites: List[str] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (SyntaxError, UnicodeDecodeError):
            continue  # non-fatal — a file that fails to parse is not this check's concern
        rel = f.relative_to(repo_root).as_posix()

        tv = _ToastSiteVisitor()
        tv.visit(tree)
        toast_sites.extend(f"{rel}:{ln}" for ln in tv.sites)

        sv = _ShowNotificationVisitor()
        sv.visit(tree)
        for funcname, lineno in sv.sites:
            if funcname not in ALLOWED_TRAY_FUNCTIONS:
                tray_sites.append(f"{rel}:{lineno} (in {funcname})")

    findings.append(AuditFinding(
        "TOAST_CALL_SITES", len(toast_sites) == 2,
        "Exactly 2 references to _show_alert_toast (its def + the set_toast_callback wiring)"
        if len(toast_sites) == 2
        else f"Expected exactly 2 references to _show_alert_toast, found {len(toast_sites)}: "
             + ", ".join(toast_sites),
    ))

    findings.append(AuditFinding(
        "UNGATED_TRAY", not tray_sites,
        "Every show_notification() call site is in the allow-list" if not tray_sites
        else "Ungated show_notification() call sites: " + "; ".join(tray_sites),
    ))

    return findings


# ── Shared channel-construction helper (CLI + tests) ──────────────────────────

def channels_from_settings(
    settings_get: Callable[[str, Any], Any],
    secret_get: Callable[[str], str],
) -> list:
    """Build the live channel list from settings, exactly as
    NotificationsPage._apply_to_router() does — pure Python, no widgets.
    secret_get(kr_key) supplies keychain-backed fields (password/token/etc)."""
    from modules.notification_router import (
        Channel, ToastChannel, WebhookChannel, EmailChannel,
        PushoverChannel, NtfyChannel, TelegramChannel,
    )

    channels: list[Channel] = []
    channels.append(ToastChannel(
        enabled=_truthy(settings_get("notif/toast_enabled", False)),
        min_severity=str(settings_get("notif/toast_severity", "WARNING")),
    ))

    url = str(settings_get("notif/webhook_url", "")).strip()
    channels.append(WebhookChannel(
        enabled=_truthy(settings_get("notif/webhook_enabled", False)) and bool(url),
        url=url,
        min_severity=str(settings_get("notif/webhook_severity", "CRITICAL")),
    ))

    host = str(settings_get("notif/email_host", "")).strip()
    try:
        port = int(str(settings_get("notif/email_port", "587")).strip() or "587")
    except ValueError:
        port = 587
    to_addrs = [a.strip() for a in str(settings_get("notif/email_to", "")).split(",") if a.strip()]
    channels.append(EmailChannel(
        enabled=_truthy(settings_get("notif/email_enabled", False)) and bool(host),
        smtp_host=host, smtp_port=port, use_tls=port != 465,
        username=str(settings_get("notif/email_user", "")).strip(),
        password=secret_get("notif/email_pass"),
        from_addr=str(settings_get("notif/email_from", "")).strip(),
        to_addrs=to_addrs,
        min_severity=str(settings_get("notif/email_severity", "CRITICAL")),
    ))

    po_token = secret_get("notif/pushover_token")
    po_user = secret_get("notif/pushover_user")
    channels.append(PushoverChannel(
        enabled=_truthy(settings_get("notif/pushover_enabled", False)) and bool(po_token) and bool(po_user),
        api_token=po_token, user_key=po_user,
        min_severity=str(settings_get("notif/pushover_severity", "WARNING")),
    ))

    ntfy_url = str(settings_get("notif/ntfy_url", "")).strip()
    channels.append(NtfyChannel(
        enabled=_truthy(settings_get("notif/ntfy_enabled", False)) and bool(ntfy_url),
        topic_url=ntfy_url,
        access_token=secret_get("notif/ntfy_token"),
        min_severity=str(settings_get("notif/ntfy_severity", "WARNING")),
    ))

    tg_token = secret_get("notif/telegram_token")
    tg_chat = str(settings_get("notif/telegram_chat", "")).strip()
    channels.append(TelegramChannel(
        enabled=_truthy(settings_get("notif/telegram_enabled", False)) and bool(tg_token) and bool(tg_chat),
        bot_token=tg_token, chat_id=tg_chat,
        min_severity=str(settings_get("notif/telegram_severity", "WARNING")),
    ))

    return channels


def format_findings(findings: List[AuditFinding], as_json: bool = False) -> str:
    if as_json:
        return json.dumps(
            [{"code": f.code, "ok": f.ok, "detail": f.detail} for f in findings], indent=2,
        )
    lines = [f"{'PASS' if f.ok else 'FAIL'}  {f.code}  {f.detail}" for f in findings]
    passed = sum(1 for f in findings if f.ok)
    lines.append(f"{passed}/{len(findings)} checks passed")
    return "\n".join(lines)

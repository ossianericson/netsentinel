"""
suggestion_engine.py — pure "What to do next" home-page suggestion rules.

Extracted from ui/tabs_logger.py::_compute_suggestions (Phase B4, data-wiring
audit). Every rule reads only SuggestionContext — no QSettings, no MetricStore
handle, no Qt import anywhere in this module — so each rule is unit-testable
without a running app or a Dashboard.

Output contract is unchanged from the original mixin method: a list of dicts
with keys action_key/text/action_label/target/priority, consumed by
ui/pages/home_suggestions.py::set_suggestions() (suppression-by-action_key and
the 4-item cap both stay there — this module returns every rule that
currently matches, sorted high > medium > low priority, and lets the caller
filter/cap).

NOT touched here (see .claude/rules/session-workflow.md invariants for Plan
B): Root Cause Correlator, Health Score, Alert rules, NL Query, and
ui/nav/builder.py::_refresh_home_suggestions remain separate surfaces —
unifying them is explicitly out of scope.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Candidate pages for the F8 "you've scanned N times but never seen X" nudge.
# Exported so ui/tabs_logger.py can check QSettings usage/visits/<label> for
# exactly these labels without duplicating the list.
USAGE_NUDGE_CANDIDATE_PAGES: tuple = ("Network Map", "Network Timeline")

_GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


@dataclass
class SuggestionContext:
    """Plain-value snapshot of everything the suggestion rules read.

    Built by ui/tabs_logger.py::_compute_suggestions from self/_store/
    QSettings — this dataclass itself touches none of those.
    """

    # ── Ported from the original 9 rules (verbatim behaviour) ────────────────
    has_scan_result: bool = False
    security_any_scan_done: bool = False
    stale_security_tools: List[str] = field(default_factory=list)
    high_risk_count: int = 0
    unknown_device_count: int = 0
    open_port_count: int = 0
    dns_grade: Optional[str] = None
    dns_value_label: str = ""
    logger_running: bool = False
    store_available: bool = True
    days_since_speed_test: Optional[float] = None
    open_cve_count: int = 0
    overall_grade: Optional[str] = None
    logger_started_once: bool = False

    # ── New context — Phase B4 step 2 ─────────────────────────────────────────
    cert_expiring_host: Optional[str] = None
    cert_expiring_days: Optional[int] = None
    trend_alert_host: Optional[str] = None
    trend_alert_message: Optional[str] = None
    grade_prev: Optional[str] = None
    grade_current: Optional[str] = None
    new_devices_since_last_visit: int = 0
    recent_arp_or_storm_event: bool = False

    # ── New context — Phase B4 step 3 (F8 usage signal) ───────────────────────
    scans_done: int = 0
    never_visited_key_pages: List[str] = field(default_factory=list)

    # ── New context — critical-UX Phase 1.3 (risk-page data guard) ───────────
    # True once self._risk_assessments has been populated by _run_risk_scorer()
    # -- the actual data source of the Device Risk Score page _rule_high_risk
    # targets. Distinct from high_risk_count, which comes from a different
    # pipeline (rogue_device.py, during the M1 scan itself) and can be
    # non-zero before the risk scorer has run.
    risk_assessments_available: bool = False


def compute_suggestions(ctx: SuggestionContext) -> List[dict]:
    """Return candidate suggestions, priority-sorted high > medium > low.

    Callers apply suppression/cap — this returns every rule that currently
    matches (fallback only when nothing else matched).
    """
    suggestions: List[dict] = []

    _rule_security_audit_nudge(ctx, suggestions)
    _rule_security_stale_nudge(ctx, suggestions)
    _rule_high_risk(ctx, suggestions)
    _rule_risk_remediation_available(ctx, suggestions)
    _rule_unknown_devices(ctx, suggestions)
    _rule_open_ports(ctx, suggestions)
    _rule_slow_dns(ctx, suggestions)
    _rule_logger_not_running(ctx, suggestions)
    _rule_speed_test_stale(ctx, suggestions)
    _rule_open_cves(ctx, suggestions)
    _rule_poor_grade(ctx, suggestions)

    _rule_cert_expiring(ctx, suggestions)
    _rule_trend_forecast(ctx, suggestions)
    _rule_grade_regression(ctx, suggestions)
    _rule_new_devices_since_last_visit(ctx, suggestions)
    _rule_arp_or_storm_protocol_viz(ctx, suggestions)
    _rule_never_visited_key_pages(ctx, suggestions)

    if not suggestions:
        _rule_fallback(ctx, suggestions)

    suggestions.sort(key=lambda s: _PRIORITY_RANK.get(s.get("priority", "medium"), 1))
    return suggestions


# ── Ported rules (verbatim text/action_keys/targets/priorities) ─────────────

def _rule_security_audit_nudge(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.has_scan_result and not ctx.security_any_scan_done:
        out.append({
            "action_key": "security_audit_nudge",
            "text": "Security audit not run — check for open ports, CVEs, and TLS issues",
            "action_label": "Open Security Audit →",
            "target": "Security Overview",
            "priority": "high",
        })


def _rule_security_stale_nudge(ctx: SuggestionContext, out: List[dict]) -> None:
    # The original inline-checked _suggestion_is_suppressed() here, but
    # set_suggestions() already applies the identical action_key suppression
    # filter to every suggestion before its own 4-item cap — the inline check
    # was provably redundant in every state, so it's dropped rather than
    # threading a QSettings read into this pure module.
    if not ctx.stale_security_tools:
        return
    n = len(ctx.stale_security_tools)
    tool_str = ", ".join(ctx.stale_security_tools[:2]) + (" + more" if n > 2 else "")
    out.append({
        "action_key": "security_stale_nudge",
        "text": (
            f"{tool_str} scan{'s are' if n > 1 else ' is'}"
            " stale or never run — re-run Security Audit"
        ),
        "action_label": "Open Security Audit →",
        "target": "Security Overview",
        "priority": "high",
    })


def _rule_high_risk(ctx: SuggestionContext, out: List[dict]) -> None:
    # Devices' per-device notes column (recognised vendor + known network
    # issues) is populated by the same M1 scan pass that computes
    # high_risk_count itself (modules/rogue_device.py) -- always in sync, no
    # guard needed.
    if ctx.high_risk_count > 0:
        s = "s" if ctx.high_risk_count != 1 else ""
        out.append({
            "action_key": "high_risk_check",
            "text": f"{ctx.high_risk_count} high-risk device{s} found — review security findings",
            "action_label": "View Devices →",
            "target": "Devices",
            "priority": "high",
        })


def _rule_risk_remediation_available(ctx: SuggestionContext, out: List[dict]) -> None:
    """Secondary, lower-priority nudge alongside _rule_high_risk: Device Risk
    Score's dedicated top_remediation column (from
    modules.risk_scorer.score_devices()) is genuinely additive over Devices'
    freeform notes -- but that pipeline is separate from the M1 scan and can
    lag or fail independently, so only surface it once it has actually
    produced data (mirrors the guard _rule_high_risk used to carry)."""
    if ctx.high_risk_count > 0 and ctx.risk_assessments_available:
        out.append({
            "action_key": "risk_remediation_available",
            "text": "Detailed remediation steps are available for your high-risk devices",
            "action_label": "View remediation steps →",
            "target": "Device Risk Score",
            "priority": "low",
        })


def _rule_unknown_devices(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.unknown_device_count > 0:
        s = "s" if ctx.unknown_device_count != 1 else ""
        out.append({
            "action_key": "unknown_devices_found",
            "text": f"{ctx.unknown_device_count} unidentified device{s} on your network — name them or flag as rogue",
            "action_label": "View Devices →",
            "target": "Devices",
            "priority": "medium",
        })


def _rule_open_ports(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.open_port_count > 0:
        s = "s" if ctx.open_port_count != 1 else ""
        out.append({
            "action_key": "open_ports_found",
            "text": f"{ctx.open_port_count} open port{s} found on your network — check for known vulnerabilities",
            "action_label": "View CVEs →",
            "target": "CVE Tracker",
            "priority": "medium",
        })


def _rule_slow_dns(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.dns_grade in ("D", "F"):
        out.append({
            "action_key": "slow_dns_response",
            "text": f"DNS response is slow ({ctx.dns_value_label}) — every site visit is delayed",
            "action_label": "View DNS & Stability →",
            "target": "DNS & Stability",
            "priority": "medium",
        })


def _rule_logger_not_running(ctx: SuggestionContext, out: List[dict]) -> None:
    if not ctx.logger_running:
        out.append({
            "action_key": "start_logger",
            "text": "Network stability is not being monitored — start logging to detect outages",
            "action_label": "Start Monitoring →",
            "target": None,
            "priority": "medium",
        })


def _rule_speed_test_stale(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.store_available and (ctx.days_since_speed_test is None or ctx.days_since_speed_test > 7):
        out.append({
            "action_key": "run_speed_test",
            "text": "No speed test in the last 7 days — check your internet performance",
            "action_label": "Run Speed Test →",
            "target": "Speed Test",
            "priority": "low",
        })


def _rule_open_cves(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.open_cve_count > 0:
        s = "s" if ctx.open_cve_count != 1 else ""
        out.append({
            "action_key": "view_open_cves",
            "text": f"{ctx.open_cve_count} open CVE{s} need remediation",
            "action_label": "View CVEs →",
            "target": "CVE Tracker",
            "priority": "high",
        })


def _rule_poor_grade(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.overall_grade in ("C", "D", "F"):
        out.append({
            "action_key": "fix_network_grade",
            "text": f"Your network grade is {ctx.overall_grade} — run a health check for recommendations",
            "action_label": "View Overview →",
            "target": "Security Overview",
            "priority": "medium",
        })


def _rule_fallback(ctx: SuggestionContext, out: List[dict]) -> None:
    if not ctx.logger_started_once:
        out.append({
            "action_key": "start_logger_fallback",
            "text": "Enable the Network Logger to track stability over time",
            "action_label": "Start →",
            "target": "Network Logger",
            "priority": "low",
        })


# ── New rules — Phase B4 step 2 ──────────────────────────────────────────────

def _rule_cert_expiring(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.cert_expiring_host is None or ctx.cert_expiring_days is None:
        return
    if ctx.cert_expiring_days >= 30:
        return
    n = ctx.cert_expiring_days
    out.append({
        "action_key": "cert_expiring_soon",
        "text": f"Certificate for {ctx.cert_expiring_host} expires in {n} day{'s' if n != 1 else ''}",
        "action_label": "View TLS & Exposure →",
        "target": "TLS & Exposure",
        "priority": "high" if n < 14 else "medium",
    })


def _rule_trend_forecast(ctx: SuggestionContext, out: List[dict]) -> None:
    if not ctx.trend_alert_host or not ctx.trend_alert_message:
        return
    out.append({
        "action_key": "trend_forecast_degrading",
        "text": ctx.trend_alert_message,
        "action_label": "View Trend Forecasts →",
        "target": "Trend Forecasts",
        "priority": "medium",
    })


def _rule_grade_regression(ctx: SuggestionContext, out: List[dict]) -> None:
    if not ctx.grade_prev or not ctx.grade_current:
        return
    if ctx.grade_prev == ctx.grade_current:
        return
    if _GRADE_RANK.get(ctx.grade_current, -1) >= _GRADE_RANK.get(ctx.grade_prev, -1):
        return  # unchanged or improved — not a regression
    out.append({
        "action_key": "grade_regressed",
        "text": f"Your grade dropped {ctx.grade_prev}→{ctx.grade_current} since last check",
        "action_label": "View Network Grade →",
        "target": "Network Grade",
        "priority": "medium",
    })


def _rule_new_devices_since_last_visit(ctx: SuggestionContext, out: List[dict]) -> None:
    n = ctx.new_devices_since_last_visit
    if n <= 0:
        return
    s = "s" if n != 1 else ""
    pronoun = "them" if n != 1 else "it"
    out.append({
        "action_key": "new_devices_since_last_visit",
        "text": f"{n} new device{s} joined while you were away — name {pronoun}",
        "action_label": "View Devices →",
        "target": "Devices",
        "priority": "medium",
    })


def _rule_arp_or_storm_protocol_viz(ctx: SuggestionContext, out: List[dict]) -> None:
    if not ctx.recent_arp_or_storm_event:
        return
    out.append({
        "action_key": "arp_storm_protocol_viz_crosssell",
        "text": "See what an ARP spoof looks like — animated",
        "action_label": "Open Protocol Visualizer →",
        "target": "Protocol Visualizer",
        "priority": "low",
    })


# ── New rule — Phase B4 step 3 (F8 usage signal) ─────────────────────────────

def _rule_never_visited_key_pages(ctx: SuggestionContext, out: List[dict]) -> None:
    if ctx.scans_done < 10:
        return
    for label in ctx.never_visited_key_pages:
        slug = label.lower().replace(" ", "_").replace("&", "and")
        out.append({
            "action_key": f"never_visited_{slug}",
            "text": f"You've scanned {ctx.scans_done} times but never seen your {label}",
            "action_label": f"Open {label} →",
            "target": label,
            "priority": "low",
        })

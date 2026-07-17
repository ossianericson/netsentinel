"""
Tests for modules/suggestion_engine.py — Phase B4 (data-wiring audit).

Golden test freezes the pre-extraction behaviour of
ui/tabs_logger.py::_compute_suggestions (captured by hand-running the original
mixin against a rich stub before the extraction) so the port is verifiably
zero-behaviour-change for the 9 ported rules. Priority is compared, not list
position — compute_suggestions() priority-sorts (high > medium > low), which
the original insertion-order list did not.
"""
from __future__ import annotations

from modules.suggestion_engine import (
    SuggestionContext,
    USAGE_NUDGE_CANDIDATE_PAGES,
    compute_suggestions,
)


def _by_key(suggestions):
    return {s["action_key"]: s for s in suggestions}


# ── Purity guard ────────────────────────────────────────────────────────────

def test_module_has_no_qt_or_qsettings_import():
    import ast
    import inspect
    from modules import suggestion_engine as mod
    tree = ast.parse(inspect.getsource(mod))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    assert not any("PyQt6" in m or "QtCore" in m for m in imported_modules), imported_modules


# ── Golden test — frozen snapshot of the pre-extraction 9 ported rules ──────
# Captured by running the original ui.tabs_logger._compute_suggestions()
# against a stub with: _m1_result (high_risk_count=2, 1 unknown device),
# _last_portscan_result.open_ports = 3 entries, DNS dimension grade "D"
# ("85ms"), _logger_worker=None, store with empty speed-test history + 2 open
# CVEs, _last_benchmark_result.overall_grade="D", _scan_registry with
# "Port Scan (TCP)"=stale and "Exposed to Internet"=never, and QSettings
# security/any_scan_done=False / logger_started_once=False (both defaults).

def _golden_context() -> SuggestionContext:
    return SuggestionContext(
        has_scan_result=True,
        security_any_scan_done=False,
        stale_security_tools=["Port Scan (TCP)", "Exposed to Internet"],
        high_risk_count=2,
        unknown_device_count=1,
        open_port_count=3,
        dns_grade="D",
        dns_value_label="85ms",
        logger_running=False,
        store_available=True,
        days_since_speed_test=None,
        open_cve_count=2,
        overall_grade="D",
        logger_started_once=False,
    )


_GOLDEN_EXPECTED = {
    "security_audit_nudge": {
        "text": "Security audit not run — check for open ports, CVEs, and TLS issues",
        "action_label": "Open Security Audit →",
        "target": "Security Overview",
        "priority": "high",
    },
    "security_stale_nudge": {
        "text": "Port Scan (TCP), Exposed to Internet scans are stale or never run — re-run Security Audit",
        "action_label": "Open Security Audit →",
        "target": "Security Overview",
        "priority": "high",
    },
    "high_risk_check": {
        "text": "2 high-risk devices found — review security findings",
        "action_label": "View Overview →",
        "target": "Dashboard",
        "priority": "high",
    },
    "unknown_devices_found": {
        "text": "1 unidentified device on your network — name them or flag as rogue",
        "action_label": "View Devices →",
        "target": "Devices",
        "priority": "medium",
    },
    "open_ports_found": {
        "text": "3 open ports found on your network — check for known vulnerabilities",
        "action_label": "View CVEs →",
        "target": "CVE Tracker",
        "priority": "medium",
    },
    "slow_dns_response": {
        "text": "DNS response is slow (85ms) — every site visit is delayed",
        "action_label": "View DNS & Stability →",
        "target": "DNS & Stability",
        "priority": "medium",
    },
    "start_logger": {
        "text": "Network stability is not being monitored — start logging to detect outages",
        "action_label": "Start Monitoring →",
        "target": None,
        "priority": "medium",
    },
    "run_speed_test": {
        "text": "No speed test in the last 7 days — check your internet performance",
        "action_label": "Run Speed Test →",
        "target": "Speed Test",
        "priority": "low",
    },
    "view_open_cves": {
        "text": "2 open CVEs need remediation",
        "action_label": "View CVEs →",
        "target": "CVE Tracker",
        "priority": "high",
    },
    "fix_network_grade": {
        "text": "Your network grade is D — run a health check for recommendations",
        "action_label": "View Overview →",
        "target": "Dashboard",
        "priority": "medium",
    },
}


def test_golden_ported_rules_match_pre_extraction_output():
    suggestions = compute_suggestions(_golden_context())
    got = _by_key(suggestions)
    assert set(got.keys()) == set(_GOLDEN_EXPECTED.keys())
    for key, expected in _GOLDEN_EXPECTED.items():
        actual = got[key]
        assert actual["text"] == expected["text"], key
        assert actual["action_label"] == expected["action_label"], key
        assert actual["target"] == expected["target"], key
        assert actual["priority"] == expected["priority"], key


def test_golden_output_is_priority_sorted():
    suggestions = compute_suggestions(_golden_context())
    ranks = {"high": 0, "medium": 1, "low": 2}
    priorities = [ranks[s["priority"]] for s in suggestions]
    assert priorities == sorted(priorities)


# ── Per-rule tests — ported rules, edge cases not covered by the golden test ─

def test_no_suggestions_when_context_is_all_clean():
    ctx = SuggestionContext(
        has_scan_result=True,
        security_any_scan_done=True,
        logger_running=True,
        store_available=True,
        days_since_speed_test=1.0,
        overall_grade="A",
        logger_started_once=True,
    )
    assert compute_suggestions(ctx) == []


def test_fallback_fires_when_nothing_else_and_logger_never_started():
    ctx = SuggestionContext(logger_running=True, days_since_speed_test=1.0,
                             overall_grade="A", logger_started_once=False)
    suggestions = compute_suggestions(ctx)
    keys = [s["action_key"] for s in suggestions]
    assert keys == ["start_logger_fallback"]
    assert suggestions[0]["target"] == "Network Logger"


def test_fallback_does_not_fire_when_logger_started_once():
    ctx = SuggestionContext(logger_running=True, days_since_speed_test=1.0,
                             overall_grade="A", logger_started_once=True)
    assert compute_suggestions(ctx) == []


def test_security_audit_nudge_requires_scan_result():
    ctx = SuggestionContext(has_scan_result=False, security_any_scan_done=False, logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "security_audit_nudge" not in keys


def test_run_speed_test_suppressed_when_store_unavailable():
    """Original code skips the speed-test check entirely when self._store is
    None — this must not be conflated with 'never run' (which DOES suggest)."""
    ctx = SuggestionContext(store_available=False, days_since_speed_test=None,
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "run_speed_test" not in keys


def test_run_speed_test_fires_when_over_7_days():
    ctx = SuggestionContext(store_available=True, days_since_speed_test=9.5,
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "run_speed_test" in keys


def test_run_speed_test_does_not_fire_within_7_days():
    ctx = SuggestionContext(store_available=True, days_since_speed_test=2.0,
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "run_speed_test" not in keys


# ── New rule: cert_expiring_soon ─────────────────────────────────────────────

def test_cert_expiring_high_priority_under_14_days():
    ctx = SuggestionContext(cert_expiring_host="example.com:443", cert_expiring_days=5,
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "cert_expiring_soon")
    assert match["priority"] == "high"
    assert "example.com:443" in match["text"]
    assert "5" in match["text"]
    assert match["target"] == "TLS & Exposure"


def test_cert_expiring_medium_priority_between_14_and_30_days():
    ctx = SuggestionContext(cert_expiring_host="example.com:443", cert_expiring_days=20,
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "cert_expiring_soon")
    assert match["priority"] == "medium"


def test_cert_not_expiring_soon_no_suggestion():
    ctx = SuggestionContext(cert_expiring_host="example.com:443", cert_expiring_days=90,
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "cert_expiring_soon" not in keys


def test_no_cert_data_no_suggestion():
    ctx = SuggestionContext(logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "cert_expiring_soon" not in keys


# ── New rule: trend_forecast_degrading ───────────────────────────────────────

def test_trend_forecast_suggestion_uses_alert_message_verbatim():
    ctx = SuggestionContext(
        trend_alert_host="192.168.1.1",
        trend_alert_message="192.168.1.1 — RTT rising at 45.0ms; projected to reach 100ms in ~3.2 h (high confidence, R²=0.91)",
        logger_running=True, logger_started_once=True,
    )
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "trend_forecast_degrading")
    assert match["text"] == ctx.trend_alert_message
    assert match["target"] == "Trend Forecasts"


def test_no_trend_alert_no_suggestion():
    ctx = SuggestionContext(logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "trend_forecast_degrading" not in keys


# ── New rule: grade_regressed ────────────────────────────────────────────────

def test_grade_regression_fires_on_drop():
    ctx = SuggestionContext(grade_prev="B", grade_current="C",
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "grade_regressed")
    assert match["text"] == "Your grade dropped B→C since last check"
    assert match["target"] == "Network Grade"


def test_grade_regression_does_not_fire_on_improvement():
    ctx = SuggestionContext(grade_prev="C", grade_current="B",
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "grade_regressed" not in keys


def test_grade_regression_does_not_fire_when_unchanged():
    ctx = SuggestionContext(grade_prev="B", grade_current="B",
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "grade_regressed" not in keys


def test_grade_regression_does_not_fire_with_only_one_grade():
    ctx = SuggestionContext(grade_prev=None, grade_current="C",
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "grade_regressed" not in keys


# ── New rule: new_devices_since_last_visit ───────────────────────────────────

def test_new_devices_since_last_visit_plural():
    ctx = SuggestionContext(new_devices_since_last_visit=2,
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "new_devices_since_last_visit")
    assert match["text"] == "2 new devices joined while you were away — name them"
    assert match["target"] == "Devices"


def test_new_devices_since_last_visit_singular():
    ctx = SuggestionContext(new_devices_since_last_visit=1,
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "new_devices_since_last_visit")
    assert match["text"] == "1 new device joined while you were away — name it"


def test_no_new_devices_no_suggestion():
    ctx = SuggestionContext(new_devices_since_last_visit=0,
                             logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "new_devices_since_last_visit" not in keys


# ── New rule: arp_storm_protocol_viz_crosssell ───────────────────────────────

def test_recent_arp_or_storm_event_crosssell():
    ctx = SuggestionContext(recent_arp_or_storm_event=True,
                             logger_running=True, logger_started_once=True)
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "arp_storm_protocol_viz_crosssell")
    assert match["text"] == "See what an ARP spoof looks like — animated"
    assert match["target"] == "Protocol Visualizer"
    assert match["priority"] == "low"


def test_no_recent_arp_or_storm_event_no_suggestion():
    ctx = SuggestionContext(logger_running=True, logger_started_once=True)
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "arp_storm_protocol_viz_crosssell" not in keys


# ── New rule: never_visited_key_pages (F8 usage signal) ─────────────────────

def test_usage_nudge_candidates_is_a_stable_public_tuple():
    assert isinstance(USAGE_NUDGE_CANDIDATE_PAGES, tuple)
    assert "Network Map" in USAGE_NUDGE_CANDIDATE_PAGES
    assert "Network Timeline" in USAGE_NUDGE_CANDIDATE_PAGES


def test_never_visited_key_pages_fires_with_enough_scans():
    ctx = SuggestionContext(
        scans_done=12, never_visited_key_pages=["Network Map"],
        logger_running=True, logger_started_once=True,
    )
    suggestions = compute_suggestions(ctx)
    match = next(s for s in suggestions if s["action_key"] == "never_visited_network_map")
    assert "12" in match["text"]
    assert "Network Map" in match["text"]
    assert match["target"] == "Network Map"
    assert match["priority"] == "low"


def test_never_visited_key_pages_suppressed_below_10_scans():
    ctx = SuggestionContext(
        scans_done=3, never_visited_key_pages=["Network Map"],
        logger_running=True, logger_started_once=True,
    )
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert "never_visited_network_map" not in keys


def test_never_visited_key_pages_empty_list_no_suggestions():
    ctx = SuggestionContext(
        scans_done=50, never_visited_key_pages=[],
        logger_running=True, logger_started_once=True,
    )
    keys = [s["action_key"] for s in compute_suggestions(ctx)]
    assert not any(k.startswith("never_visited_") for k in keys)


def test_never_visited_key_pages_multiple_candidates_each_get_a_suggestion():
    ctx = SuggestionContext(
        scans_done=15, never_visited_key_pages=["Network Map", "Network Timeline"],
        logger_running=True, logger_started_once=True,
    )
    keys = {s["action_key"] for s in compute_suggestions(ctx)}
    assert "never_visited_network_map" in keys
    assert "never_visited_network_timeline" in keys

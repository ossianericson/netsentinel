"""
modules/digest_bullets.py — overnight summary bullets for Morning Briefing (Sprint 4).

Rolls up the two flagship proactive-monitoring domains built in Sprints 1 and 3
(SERVICE_DOWN root-cause escalation, scheduled BASELINE_DROP speed tests) into
plain-English bullets appended to the existing 3-bullet Morning Briefing.

Each builder is independently gated on the *other* feature's own opt-in state —
per the plan's explicit "don't mention speed trends if scheduled testing is
off" instruction — not on Morning Briefing's own enabled flag (that gate is
already applied by proactive_digest.is_due() before these builders run).

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected — never instantiated here.
  • QSettings accessed via a callable getter, not imported directly.
"""
from __future__ import annotations

from typing import Callable, List

from modules.alert_suppressor import rule_settings_key
from modules.service_escalation import is_filtered_message

MAX_BULLETS = 5

_SERVICE_DOWN_RULE_NAME = "Service Down"
_BASELINE_DROP_RULE_NAME = "Baseline Speed Drop"
_SCHEDULED_SPEEDTEST_KEY = "speedtest/scheduled_enabled"

# V6 Sprint 1 — new rule names, gated on their own alert_rules/*/enabled key.
_JITTER_HIGH_RULE_NAME = "Jitter High"
_MESH_DEGRADED_RULE_NAME = "Mesh Degraded"
_MODEM_SIGNAL_DROP_RULE_NAME = "Modem Signal Drop"
_GRADE_REGRESSION_RULE_NAME = "Grade Regression"
_IP_CHURN_RULE_NAME = "IP Churn"

# V6 Sprint 2 — dormant baseline engines, same gating pattern as Sprint 1.
_RTT_ANOMALY_RULE_NAME = "RTT Anomaly"
_IOT_BEHAVIOR_RULE_NAME = "IoT Behavior Anomaly"
_TREND_FORECAST_RULE_NAME = "Trend Forecast"

# V6 Sprint 3 — scheduled security posture + diffing, same gating pattern.
_NEW_OPEN_PORT_RULE_NAME = "New Open Port"
_NEW_CVE_RULE_NAME = "New CVE Found"
_NEW_EXPOSURE_RULE_NAME = "New Internet Exposure"

# V6 Sprint 4 — passive always-on guards, same gating pattern.
_ARP_SPOOF_RULE_NAME = "ARP Spoof Detected"
_ROGUE_DHCP_RULE_NAME = "Rogue DHCP Server"
_CONFIG_DRIFT_RULE_NAME = "Config Drift"


def build_digest_bullets(
    store,
    settings_get: Callable[[str], object],
    hours: float = 24.0,
) -> List[str]:
    """
    Compose overnight summary bullets for the two flagship domains, capped at
    MAX_BULLETS with a "+N more" suffix. Returns an empty list if neither
    underlying feature has any overnight activity worth reporting.
    """
    bullets: List[str] = list(_service_health_bullets(store, settings_get, hours))
    speed_bullet = _speed_trend_bullet(store, settings_get, hours)
    if speed_bullet:
        bullets.append(speed_bullet)
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _JITTER_HIGH_RULE_NAME,
        lambda a: f"{a.get('host', 'A host')}: {a.get('message', 'unstable jitter overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _MESH_DEGRADED_RULE_NAME,
        lambda a: f"Mesh: {a.get('message', 'degraded overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _MODEM_SIGNAL_DROP_RULE_NAME,
        lambda a: f"Modem: {a.get('message', 'signal degraded overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _GRADE_REGRESSION_RULE_NAME,
        lambda a: f"Network grade: {a.get('message', 'declined overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _IP_CHURN_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'unstable IP address overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _RTT_ANOMALY_RULE_NAME,
        lambda a: f"{a.get('host', 'A host')}: {a.get('message', 'slower than its usual pattern overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _IOT_BEHAVIOR_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'unusual behavior detected overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _TREND_FORECAST_RULE_NAME,
        lambda a: f"Forecast: {a.get('message', 'a metric is trending toward its threshold')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _NEW_OPEN_PORT_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'a new port opened overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _NEW_CVE_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'a new CVE was found overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _NEW_EXPOSURE_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'a port became newly exposed overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _ARP_SPOOF_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'ARP spoofing detected overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _ROGUE_DHCP_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'a rogue DHCP server was seen overnight')}",
    )
    bullets += _simple_rule_bullets(
        store, settings_get, hours, _CONFIG_DRIFT_RULE_NAME,
        lambda a: f"{a.get('host', 'A device')}: {a.get('message', 'drifted from your blessed baseline overnight')}",
    )
    return _cap_bullets(bullets)


# ── Bullet builders ────────────────────────────────────────────────────────────

def _service_health_bullets(store, settings_get, hours: float) -> List[str]:
    """
    One bullet per distinct host with an overnight SERVICE_DOWN alert, gated
    on the SERVICE_DOWN rule itself being enabled — reuses the exact QSettings
    key NotificationsPage already persists (alert_rules/service_down/enabled),
    so there is nothing new to configure.
    """
    if not _truthy(settings_get(rule_settings_key(_SERVICE_DOWN_RULE_NAME))):
        return []
    try:
        alerts = [
            a for a in store.get_recent_alerts(hours=hours, limit=200)
            if a.get("rule_name") == _SERVICE_DOWN_RULE_NAME
        ]
    except Exception:
        return []
    if not alerts:
        return []

    seen_hosts = set()
    bullets: List[str] = []
    for a in alerts:  # newest first — first occurrence per host wins
        host = a.get("host", "") or "a monitored service"
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        if is_filtered_message(a.get("message", "")):
            bullets.append(
                f"{host}: filtered by a firewall/VPN/ISP overnight — not a real outage."
            )
        else:
            bullets.append(f"{host}: unreachable overnight.")
    return bullets


def _speed_trend_bullet(store, settings_get, hours: float) -> str:
    """
    Summarize the most recent overnight BASELINE_DROP alert, gated on
    scheduled speed testing being enabled (speedtest/scheduled_enabled) — the
    same key the Speed Test page's "Automatic Speed Tests" card persists.
    """
    if not _truthy(settings_get(_SCHEDULED_SPEEDTEST_KEY)):
        return ""
    try:
        alerts = [
            a for a in store.get_recent_alerts(hours=hours, limit=200)
            if a.get("rule_name") == _BASELINE_DROP_RULE_NAME
        ]
    except Exception:
        return ""
    if not alerts:
        return ""
    return f"Speed trend: {alerts[0].get('message', 'a speed drop was detected overnight')}"


def _simple_rule_bullets(store, settings_get, hours: float, rule_name: str, formatter) -> List[str]:
    """
    Generic V6 Sprint 1 bullet builder shared by JITTER_HIGH, MESH_DEGRADED,
    MODEM_SIGNAL_DROP, GRADE_REGRESSION, and IP_CHURN — gated on the rule's own
    alert_rules/<name>/enabled key (same key the Notifications page checkbox
    persists), one bullet per distinct host, newest occurrence wins.
    """
    if not _truthy(settings_get(rule_settings_key(rule_name))):
        return []
    try:
        alerts = [
            a for a in store.get_recent_alerts(hours=hours, limit=200)
            if a.get("rule_name") == rule_name
        ]
    except Exception:
        return []
    if not alerts:
        return []

    seen_hosts = set()
    bullets: List[str] = []
    for a in alerts:  # newest first — first occurrence per host wins
        host = a.get("host", "")
        if host in seen_hosts:
            continue
        seen_hosts.add(host)
        bullets.append(formatter(a))
    return bullets


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cap_bullets(bullets: List[str]) -> List[str]:
    if len(bullets) <= MAX_BULLETS:
        return bullets
    kept = bullets[: MAX_BULLETS - 1]
    kept.append(f"+{len(bullets) - len(kept)} more")
    return kept


def _truthy(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)

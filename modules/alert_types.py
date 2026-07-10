"""
Alert type definitions — RULE_TYPES, AlertRule, AlertFired.

Extracted from alert_engine.py so that alert_engine_checks.py and
alert_suppressor.py can import these without creating circular imports.
alert_engine.py re-exports all names for backward compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ── Valid rule types ──────────────────────────────────────────────────────────

RULE_TYPES = frozenset({
    "RTT_THRESHOLD",
    "LOSS_THRESHOLD",
    "HOST_DOWN",
    "HOST_DEGRADED",
    "NEW_DEVICE",
    "DEVICE_GONE",
    "CERT_EXPIRY",
    "CERT_EXPIRED",
    "FLAP",
    "SERVICE_DOWN",
    "BASELINE_DROP",
    "JITTER_HIGH",
    "MESH_DEGRADED",
    "MODEM_SIGNAL_DROP",
    "GRADE_REGRESSION",
    "IP_CHURN",
    "RTT_ANOMALY",
    "IOT_BEHAVIOR",
    "TREND_FORECAST",
    "NEW_OPEN_PORT",
    "NEW_CVE",
    "NEW_EXPOSURE",
    "ARP_SPOOF",
    "ROGUE_DHCP",
    "CONFIG_DRIFT",
})


# ── Alert scoping sets ────────────────────────────────────────────────────────
# Two orthogonal groupings of RULE_TYPES used by the opt-in alert model:
#
#   DEVICE_SCOPED_RULE_TYPES  — per-device health/behaviour rules. These only
#       fire for a host the AlertEngine's injected scope checker approves
#       (infrastructure role + user opt-in). Without this gate they would fire
#       for every transient device seen in a scan — guest phones, IoT bulbs —
#       which no home-network tool should alert on by default.
#
#   SECURITY_RELEVANT_RULE_TYPES — genuine security events. NEVER device-scoped
#       (a rogue DHCP server or ARP spoofer must alert regardless of opt-in).
#       This set also drives the Security Audit rail badge count so the badge
#       reflects only security-meaningful unacked alerts, not device-health noise.
#
# The two sets are deliberately disjoint. Rules absent from both (MESH_DEGRADED,
# MODEM_SIGNAL_DROP, GRADE_REGRESSION, BASELINE_DROP) are singleton/network-wide
# metrics keyed by a literal string, not an arbitrary device — neither gated nor
# counted toward the security badge. NEW_OPEN_PORT is also absent from both: a
# newly opened port is a state change of unknown severity (could be a game server
# the user just started), not an attack signature like ARP_SPOOF/ROGUE_DHCP — it
# still fires and lands in the general Alert History, but doesn't compete for
# attention with genuine security incidents on the Security Audit badge/card.

# Gated set = rules that fire against auto-discovered LAN devices from the scan /
# availability pipeline (the ones that flood when "every device in the scan" is
# evaluated). SERVICE_DOWN and CERT_* are intentionally NOT here: those fire
# against user-configured host:port targets (often external hosts with no
# known_device row), so they are already opt-in by virtue of the user adding the
# target — gating them by the device checker would silently suppress a monitor
# the user explicitly asked for.
DEVICE_SCOPED_RULE_TYPES = frozenset({
    "RTT_THRESHOLD",
    "LOSS_THRESHOLD",
    "HOST_DOWN",
    "HOST_DEGRADED",
    "FLAP",
    "JITTER_HIGH",
    "RTT_ANOMALY",
    "IOT_BEHAVIOR",
    "TREND_FORECAST",
    "IP_CHURN",
})

SECURITY_RELEVANT_RULE_TYPES = frozenset({
    "ARP_SPOOF",
    "ROGUE_DHCP",
    "NEW_CVE",
    "NEW_EXPOSURE",
    "CONFIG_DRIFT",
    "CERT_EXPIRY",
    "CERT_EXPIRED",
})


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class AlertRule:
    name:           str
    rule_type:      str
    host:           Optional[str] = None      # None = any host
    threshold_ms:   float         = 200.0     # RTT_THRESHOLD
    threshold_pct:  float         = 10.0      # LOSS_THRESHOLD
    threshold_days: int           = 30        # CERT_EXPIRY — fire when days_remaining < this
    flap_count:     int           = 4         # FLAP — min transitions to be "flapping"
    flap_window_s:  int           = 600       # FLAP — rolling window (10 min default)
    baseline_metric: str          = "download_mbps"  # BASELINE_DROP — metric name (future use)
    warn_pct:       float         = 50.0      # BASELINE_DROP — % drop for Warning severity
    high_pct:       float         = 75.0      # BASELINE_DROP — % drop for High severity
    min_samples:    int           = 4         # BASELINE_DROP — min prior samples required
    sigma:          float         = 2.0       # RTT_ANOMALY — std-devs above a host's own baseline mean
    cooldown_s:     int           = 300       # 5 min default
    enabled:        bool          = True

    def __post_init__(self):
        rt = self.rule_type.upper()
        if rt not in RULE_TYPES:
            raise ValueError(f"Unknown rule_type {self.rule_type!r}. Valid: {sorted(RULE_TYPES)}")
        self.rule_type = rt


@dataclass
class AlertFired:
    """An alert that has been triggered by a rule evaluation."""
    rule_name:     str
    rule_type:     str
    host:          str
    message:       str
    severity:      str           # "INFO" | "WARNING" | "CRITICAL" | "HEALTHY"
    ts:            int
    value:         Optional[float] = None   # the triggering metric value
    cta_page:      Optional[str]  = None   # nav label of the page that can resolve this alert
    cta_filter:    Optional[str]  = None   # opaque filter string passed to that page (e.g. IP)
    is_resolution: bool           = False  # True when this alert clears a previous one
    downtime_s:    Optional[int]  = None   # seconds the host/service was down (resolutions only)

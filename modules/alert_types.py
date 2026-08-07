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
    "INFRA_UNREACHABLE",
    "DNS_LATENCY",
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
# ("Lands in the general Alert History" now holds for every rule type that
# fires — NEW_DEVICE/DEVICE_GONE tracker alerts were a silent exception,
# shown as a toast/Home-card entry but never persisted, until scan_wiring.py's
# tracker-alert loop gained a persist_alert() call alongside its IP_CHURN
# sibling. Alert History can also now surface any unacked alert regardless of
# age via its "Unacknowledged only" filter, so "lands in history" also means
# "reachable there.")

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

# How long acknowledging an alert mutes further firings of the same
# (rule, host) in AlertEngine. Lives here, not in alert_engine.py, so the UI
# can read the default without importing the engine (ARCH RULE 1); the engine
# re-exports it for existing callers. 0 disables the hold.
DEFAULT_ACK_HOLD_SECONDS = 86400  # 24 h

# Per-rule-type default for AlertRule.min_consecutive (Signal Quality Phase 6).
#
# Keyed by rule TYPE, not left to the field's own default, because the value it
# generalises — alert_engine_checks._SERVICE_DOWN_MIN_CONSECUTIVE_FAILS — was a
# module constant applied to every SERVICE_DOWN rule however it was built. A
# plain field default of 1 would have silently removed that grace period from
# every hand-constructed rule (tests, the Notifications page, any caller that
# does not know the field exists) while leaving only _default_rules() correct.
#
# Anything absent here defaults to 1: pure edge-triggering, which is the shipped
# behaviour for every other rule type.
DEFAULT_MIN_CONSECUTIVE_BY_RULE_TYPE = {
    # A target that was never reachable — added by mistake, or a monkey-test
    # click landing in the add-service field — must not fire CRITICAL on its
    # very first check and then re-fire every cooldown forever.
    "SERVICE_DOWN": 3,
}


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
    # Signal Quality Phase 2 — device_importance.Tier name this rule requires of
    # a device before it will fire for it. None = use the engine's default floor
    # (INFRASTRUCTURE, the tier equivalent of the legacy gateway/infrastructure
    # gate), so an existing persisted rule does not change behaviour just
    # because the field appeared. Only consulted once a tier provider is
    # injected; see alert_suppressor._DeviceScopeMixin.
    min_tier:       Optional[str] = None
    # Signal Quality Phase 6 — consecutive symptomatic observations required
    # before this rule speaks. Generalises _SERVICE_DOWN_MIN_CONSECUTIVE_FAILS
    # (alert_engine_checks.py), a hardcoded 3 that only SERVICE_DOWN had and
    # that no rule could tune.
    #
    # None = "use this rule type's own default" from
    # DEFAULT_MIN_CONSECUTIVE_BY_RULE_TYPE, resolved in __post_init__ so the
    # field is always a concrete int by the time anything reads it. That
    # indirection is what preserves SERVICE_DOWN's grace period for callers
    # that build a rule without naming the field.
    #
    # 1 = pure edge-triggering, the shipped behaviour for every other rule type
    # and one that must stay so: HOST_DOWN's confirmation lives in the monitor
    # layer (device_baseline.DOWN_CONFIRMATION_CYCLES), and stacking a second
    # one here would put the first gateway alert past acceptance criterion 5's
    # three-minute budget. See modules/evidence.py's DEFAULT_MIN_CONSECUTIVE.
    min_consecutive: Optional[int] = None

    def __post_init__(self):
        rt = self.rule_type.upper()
        if rt not in RULE_TYPES:
            raise ValueError(f"Unknown rule_type {self.rule_type!r}. Valid: {sorted(RULE_TYPES)}")
        self.rule_type = rt
        if self.min_consecutive is None:
            self.min_consecutive = DEFAULT_MIN_CONSECUTIVE_BY_RULE_TYPE.get(rt, 1)
        elif int(self.min_consecutive) < 1:
            raise ValueError(
                f"min_consecutive must be >= 1, got {self.min_consecutive!r} — "
                f"0 would admit a condition that was never observed"
            )
        self.min_consecutive = int(self.min_consecutive)
        if self.min_tier is not None:
            # Imported here rather than at module scope: alert_types is imported
            # by ui/ and by every alert_engine_* split, and none of them need
            # the importance model unless a rule actually names a tier.
            from modules.device_importance import Tier, tier_from_name
            tier = tier_from_name(self.min_tier)
            if tier is None:
                raise ValueError(
                    f"Unknown min_tier {self.min_tier!r}. "
                    f"Valid: {sorted(t.value for t in Tier)}"
                )
            self.min_tier = tier.value


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
    remediation:   str            = ""     # per-alert override; "" = use alert_remediation table
    # Signal Quality Phase 6 — what corroborated this claim, carried through to
    # `alert_fired` (schema v22) and read by modules/relevance.py for ordering.
    # `confidence` is evidence.Evidence.confidence: an ordering aid in 0.0..1.0,
    # NOT a probability and never a severity — RULE-A3's vocabulary is untouched.
    # Both are None on the paths that have no evidence gate, which relevance
    # treats as neutral rather than as low confidence.
    confidence:    Optional[float] = None
    evidence_json: Optional[str]   = None

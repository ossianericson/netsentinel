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

"""
Alert suppression policies and default rule set.

Extracted from modules/alert_engine.py (S20-4 sprint split).
All public names remain importable from modules.alert_engine for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.alert_types import AlertRule, DEVICE_SCOPED_RULE_TYPES
from modules.device_importance import Tier, tier_from_name

# The tier equivalent of the legacy `inferred_role in ("gateway",
# "infrastructure")` gate: what a device-scoped rule requires when it does not
# name a floor of its own.
_DEFAULT_MIN_TIER = Tier.INFRASTRUCTURE


# ── Per-device opt-in scope (device-health alert noise reduction) ─────────────

class _DeviceScopeMixin:
    """Mixin for AlertEngine: gate device-health rules by device importance.

    Device-scoped rules (DEVICE_SCOPED_RULE_TYPES) fire against auto-discovered
    LAN devices. Without a filter, that means every transient device seen in a
    scan (guest phones, IoT bulbs) can raise a HOST_DOWN / RTT alert nobody asked
    for. Rules outside DEVICE_SCOPED_RULE_TYPES — security events, singleton
    network metrics — are never gated.

    Two gates exist, and the newer one wins when both are injected:

      * **Tier floor** (Signal Quality Phase 2, `set_device_tier_provider`) —
        compares the device's `device_importance.Tier` against the rule's
        `min_tier`. This is the path `experimental/signal_quality_v2` selects.
      * **Boolean checker** (legacy, `set_alert_scope_checker`) — one
        `is_device_alert_in_scope()` call. Measured on a real database it
        admitted 53.4 % of candidate alerts on the strength of an
        `inferred_role` column that was wrong for 8 of 13 devices.

    Neither injected (the default) disables filtering entirely, so existing
    behaviour and tests are unchanged.
    """

    def set_alert_scope_checker(self, checker: Optional[Callable[[str], bool]]) -> None:
        """Inject callable(host) -> bool: True if alerts are in scope for host.
        None disables the filter (all hosts allowed)."""
        self._scope_checker = checker

    def set_device_tier_provider(
        self, provider: Optional[Callable[[str], object]]
    ) -> None:
        """Inject callable(host) -> Tier | tier name. None restores the legacy
        boolean checker. Takes precedence over set_alert_scope_checker()."""
        self._tier_provider = provider

    def _out_of_scope(
        self, host: str, rule_type: str, min_tier: Optional[str] = None
    ) -> bool:
        """True when a device-scoped rule should be suppressed for this host."""
        if rule_type not in DEVICE_SCOPED_RULE_TYPES:
            return False

        provider = getattr(self, "_tier_provider", None)
        if provider is not None:
            try:
                raw = provider(host)
            except Exception:
                return False  # never let a provider error suppress a real alert
            tier = raw if isinstance(raw, Tier) else tier_from_name(
                raw if isinstance(raw, str) else None
            )
            floor = tier_from_name(min_tier) or _DEFAULT_MIN_TIER
            # An unreadable tier is treated as the lowest, not as "allow": a
            # device the importance model cannot speak about is exactly the
            # kind this gate exists to stay quiet about.
            return (tier or Tier.TRANSIENT) < floor

        checker = getattr(self, "_scope_checker", None)
        if checker is None:
            return False
        try:
            return not checker(host)
        except Exception:
            return False  # never let a checker error suppress a real alert


# ── Maintenance-window suppression (Sprint 5 file-budget split) ───────────────

class _MaintenanceSuppressionMixin:
    """Mixin for AlertEngine: maintenance-window checker + suppression logging.

    Extracted out of alert_engine.py to stay under the 780-line RULE-AH1
    budget. AlertEngine inherits this alongside _AlertChecksMixin.
    """

    def set_maintenance_checker(
        self, checker: Optional[Callable[[str], Optional[str]]]
    ) -> None:
        """Inject callable(host) -> window_label|None from MaintenanceWindowManager.
        When set, any alert whose host is currently under maintenance is silently
        dropped (not dispatched to on_alert). Pass None to disable."""
        self._maintenance_checker = checker

    def set_suppression_recorder(
        self, recorder: Optional[Callable[[str, str, str, str, str], None]]
    ) -> None:
        """callable(window_label, host, rule_name, severity, message) — called
        whenever the maintenance checker drops an alert. None disables logging."""
        self._suppression_recorder = recorder

    def _maintenance_suppresses(
        self, host: str, rule_name: str, severity: str, message: str
    ) -> bool:
        """True if `host` is currently under a maintenance window. Also invokes
        the suppression recorder (if any) as a side effect when suppressing."""
        if self._maintenance_checker is None:
            return False
        window_label = self._maintenance_checker(host)
        if window_label is None:
            return False
        if self._suppression_recorder is not None:
            self._suppression_recorder(window_label, host, rule_name, severity, message)
        return True


# ── Escalation policy ─────────────────────────────────────────────────────────

@dataclass
class EscalationPolicy:
    """
    Defines what happens when an alert is not acknowledged within wait_minutes.

    When an alert matching rule_name fires and remains unacknowledged for
    wait_minutes, the AlertEngine's check_escalations() will return it for
    escalation.  The caller is responsible for re-delivering via the channels
    listed in notify_channels (channel names as stored in notification_router).
    """
    rule_name:       str
    wait_minutes:    int              = 15
    notify_channels: List[str]        = field(default_factory=list)
    enabled:         bool             = True


# ── Default rules ─────────────────────────────────────────────────────────────

# ── The curated default-on set (acceptance criterion 7) ──────────────────────
#
# Signal Quality Phase 6. Every built-in rule shipped disabled, which is the
# only reason Phase 0 could measure the alert engine as "nearly silent" while
# the ungated *event* stream carried 147 claims/day: the alerting layer was not
# quiet, it was switched off. This is the set a fresh install turns on.
#
# It is the union of the app's existing recommendation (surfaced by the
# first-run overlay and the Notifications page's "Enable recommended" button)
# and the four signals Phase 4 built because the user called them real. "High
# RTT" was dropped from that older recommendation on the owner's call: it is
# level-triggered against a fixed 200 ms threshold — the defect class this whole
# program exists to remove — and the per-device HOST_DEGRADED/RTT_ANOMALY path
# supersedes it.
#
# Measured through the v2 tier gate over 23.7 days of the reference database:
# HOST_DOWN 0.30/day plus 0.30/day of resolutions, NEW_DEVICE 0.08, FLAP 0.08,
# CERT_EXPIRY 0 with no configured targets, and the four Phase 4 rules ~0 on a
# healthy network (each is edge-triggered, one claim per episode). Roughly
# 1 claim/day in total, against the 163.6/day an ungated engine produced.
#
# RTT_ANOMALY joined the set in v2.2.6, on measurement rather than intuition.
# Phase 4 revived it but left it uncurated, and it was grouped with the
# level-triggered rules below — a misfiling: it learns a per-host mean+2sigma
# baseline instead of comparing against a fixed constant, which is the exact
# property that got "High RTT" dropped. Measured over 28.8 days of the reference
# database through the v2 tier gate: 0.15 claims/day, quieter than
# MODEM_SIGNAL_DROP which already ships on. Phase 6 also gave it an absolute
# floor (`_RTT_ANOMALY_FLOOR_MS`, alert_engine_checks2.py), so a host whose
# baseline is a few milliseconds cannot alert on a harmless few-ms excursion —
# the failure mode that would otherwise make a learned baseline noisy on a fast
# LAN.
#
# Deliberately NOT here: RTT_THRESHOLD, HOST_DEGRADED, LOSS_THRESHOLD (level-
# triggered); JITTER_HIGH (producer works, but it is a fixed 20 ms threshold —
# the same objection that dropped High RTT — and the gateway is not sampled, so
# the measurement behind it is too thin to curate on); and ARP_SPOOF/ROGUE_DHCP
# — correct candidates, but they only evaluate when their background watcher is
# running, and a default-on rule whose producer may be absent is a promise the
# app cannot keep.
DEFAULT_ENABLED_RULES = frozenset({
    "Host Down",
    "New Device",
    "Cert Expiring",
    "Host Flapping",
    "Infrastructure Unreachable",
    "Mesh Degraded",
    "Modem Signal Drop",
    "DNS Latency",
    "RTT Anomaly",
})


def default_enabled(rule_name: str) -> bool:
    """Whether `rule_name` is on when the user has never expressed a choice.

    **This is the shipped default, and the QSettings fallback is the only lever
    that applies it.** `_default_rules()` keeps `enabled=False` on the dataclass
    on purpose: `AlertEngine()` is constructed headlessly by the test suite and
    by tools/alert_replay.py, and flipping the field would change what those
    measure rather than what a user receives.

    An explicit stored key always wins in both directions, so a user who has
    ever pressed Save on the Notifications page keeps exactly what they chose —
    including everything they turned off.
    """
    return rule_name in DEFAULT_ENABLED_RULES


def rule_settings_key(rule_name: str) -> str:
    """Return the QSettings key used to persist a rule's enabled state.

    Key format: ``alert_rules/<safe_name>/enabled``

    Use this function in both ``app.py`` and ``NotificationsPage`` to ensure
    the key is always consistent.
    """
    safe = rule_name.lower().replace(" ", "_").replace("/", "_")
    return f"alert_rules/{safe}/enabled"


def _default_rules():
    """Built-in rule set — ALL disabled by default (opt-in only).

    Users must explicitly enable each rule in Settings → Notifications before
    any alert fires.  This prevents surprise notifications on first launch.
    """
    return [
        AlertRule(
            name="High RTT",
            rule_type="RTT_THRESHOLD",
            host=None,
            threshold_ms=200.0,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Packet Loss",
            rule_type="LOSS_THRESHOLD",
            host=None,
            threshold_pct=10.0,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Host Down",
            rule_type="HOST_DOWN",
            host=None,
            cooldown_s=120,
            enabled=False,
        ),
        AlertRule(
            name="Host Degraded",
            rule_type="HOST_DEGRADED",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="New Device",
            rule_type="NEW_DEVICE",
            host=None,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="Device Gone",
            rule_type="DEVICE_GONE",
            host=None,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="Cert Expiring",
            rule_type="CERT_EXPIRY",
            host=None,
            threshold_days=30,
            cooldown_s=86400,
            enabled=False,
        ),
        AlertRule(
            name="Cert Expired",
            rule_type="CERT_EXPIRED",
            host=None,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="Host Flapping",
            rule_type="FLAP",
            host=None,
            flap_count=4,
            flap_window_s=600,
            cooldown_s=600,
            enabled=False,
        ),
        AlertRule(
            name="Service Down",
            rule_type="SERVICE_DOWN",
            host=None,
            cooldown_s=300,
            # min_consecutive comes from DEFAULT_MIN_CONSECUTIVE_BY_RULE_TYPE
            # (3), not restated here — one source of truth, and it applies to
            # every SERVICE_DOWN rule however it was constructed.
            enabled=False,
        ),
        AlertRule(
            name="Baseline Speed Drop",
            rule_type="BASELINE_DROP",
            host=None,
            warn_pct=50.0,
            high_pct=75.0,
            min_samples=4,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="Jitter High",
            rule_type="JITTER_HIGH",
            host=None,
            threshold_ms=20.0,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Mesh Degraded",
            rule_type="MESH_DEGRADED",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Modem Signal Drop",
            rule_type="MODEM_SIGNAL_DROP",
            host=None,
            min_samples=20,
            cooldown_s=1800,
            enabled=False,
        ),
        AlertRule(
            name="Grade Regression",
            rule_type="GRADE_REGRESSION",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="IP Churn",
            rule_type="IP_CHURN",
            host=None,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="RTT Anomaly",
            rule_type="RTT_ANOMALY",
            host=None,
            sigma=2.0,
            cooldown_s=600,
            enabled=False,
        ),
        AlertRule(
            name="IoT Behavior Anomaly",
            rule_type="IOT_BEHAVIOR",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Trend Forecast",
            rule_type="TREND_FORECAST",
            host=None,
            cooldown_s=3600,
            enabled=False,
        ),
        AlertRule(
            name="New Open Port",
            rule_type="NEW_OPEN_PORT",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="New CVE Found",
            rule_type="NEW_CVE",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="New Internet Exposure",
            rule_type="NEW_EXPOSURE",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        # ── V6 Sprint 4: passive always-on guards ───────────────────────────
        AlertRule(
            name="ARP Spoof Detected",
            rule_type="ARP_SPOOF",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Rogue DHCP Server",
            rule_type="ROGUE_DHCP",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Config Drift",
            rule_type="CONFIG_DRIFT",
            host=None,
            cooldown_s=300,
            enabled=False,
        ),
        AlertRule(
            name="Infrastructure Unreachable",
            rule_type="INFRA_UNREACHABLE",
            host=None,
            # Long cooldown: the rule is edge-triggered, so this only matters
            # as a backstop against a device that flaps its poll rapidly.
            cooldown_s=1800,
            enabled=False,
        ),
        AlertRule(
            name="DNS Latency",
            rule_type="DNS_LATENCY",
            host=None,
            # Long cooldown for the same reason as INFRA_UNREACHABLE: the rule
            # is edge-triggered, so this only backstops a resolver that
            # oscillates across the threshold cycle after cycle.
            cooldown_s=1800,
            enabled=False,
        ),
    ]

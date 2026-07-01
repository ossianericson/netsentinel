"""
Alert suppression policies and default rule set.

Extracted from modules/alert_engine.py (S20-4 sprint split).
All public names remain importable from modules.alert_engine for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.alert_types import AlertRule


# ── Maintenance-window suppression (Sprint 5 file-budget split) ───────────────

class _MaintenanceSuppressionMixin:
    """Mixin for AlertEngine: maintenance-window checker + suppression logging.

    Extracted out of alert_engine.py to stay under the 600-line RULE-AH1
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
    ]

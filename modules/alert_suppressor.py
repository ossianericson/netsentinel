"""
Alert suppression policies and default rule set.

Extracted from modules/alert_engine.py (S20-4 sprint split).
All public names remain importable from modules.alert_engine for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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
    from modules.alert_engine import AlertRule
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
    ]

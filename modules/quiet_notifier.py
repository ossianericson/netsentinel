"""
quiet_notifier — "All quiet" opt-in daily notification (S4-5).

When enabled, NetSentinel sends one tray notification per day (at a
configurable hour) confirming that no critical or warning alerts fired
in the previous 24 hours.

Integration
-----------
Call ``check_and_maybe_notify(store, settings)`` once at startup.  The
function reads QSettings to decide whether to proceed, then queries
MetricStore for yesterday's alert count and returns a ``QuietResult``
if a notification should be shown.  The caller (app.py) is responsible
for displaying the tray notification — this module is pure Python.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected — never instantiated here.
  • QSettings accessed via a callable getter, not imported directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

# ── QSettings keys ────────────────────────────────────────────────────────────
ENABLED_KEY      = "alerts/quiet_notify_enabled"
LAST_SENT_KEY    = "alerts/quiet_notify_last_sent_day"
NOTIFY_HOUR_KEY  = "alerts/quiet_notify_hour"   # 0–23, default 8

_DEFAULT_HOUR = 8


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class QuietResult:
    """Returned when an all-quiet notification should be shown."""
    headline:   str    # "Your network was healthy all day."
    sub_text:   str    # "5 devices active, no issues detected."
    device_count:  int = 0
    alert_count:   int = 0   # always 0 when returned (that is the condition)


# ── Public API ────────────────────────────────────────────────────────────────

def check_and_maybe_notify(
    store,
    settings_get: Callable[[str], object],
    settings_set: Callable[[str, object], None],
) -> Optional[QuietResult]:
    """
    Return a ``QuietResult`` if a "all quiet" tray notification is due, else None.

    Parameters
    ----------
    store
        MetricStore singleton.
    settings_get
        Callable(key) → value — typically ``QSettings.value``.
    settings_set
        Callable(key, value) — typically ``QSettings.setValue``.
    """
    # Feature disabled by default (opt-in)
    enabled = _truthy(settings_get(ENABLED_KEY))
    if not enabled:
        return None

    # Only fire once per calendar day
    today_str = time.strftime("%Y-%m-%d", time.localtime())
    last_sent = settings_get(LAST_SENT_KEY)
    if last_sent == today_str:
        return None

    # Only fire at or after the configured hour
    configured_hour = _int_val(settings_get(NOTIFY_HOUR_KEY), _DEFAULT_HOUR)
    current_hour = time.localtime().tm_hour
    if current_hour < configured_hour:
        return None

    # Check for critical/warning alerts in the last 24 hours
    recent = store.get_recent_alerts(hours=24.0)
    noisy_alerts = [
        a for a in recent
        if a.get("severity", "").upper() in ("CRITICAL", "WARNING")
        and not a.get("is_resolution", False)
    ]
    if noisy_alerts:
        return None   # not a quiet day

    # Query approximate device count from recent availability data
    try:
        device_count = _estimate_device_count(store)
    except Exception:  # non-fatal — device count is cosmetic
        device_count = 0

    settings_set(LAST_SENT_KEY, today_str)

    sub = f"{device_count} device{'s' if device_count != 1 else ''} active, no issues detected."
    return QuietResult(
        headline="Your network was healthy all day.",
        sub_text=sub,
        device_count=device_count,
        alert_count=0,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truthy(val: object) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def _int_val(val: object, default: int) -> int:
    if not isinstance(val, (int, float, str)):
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _estimate_device_count(store) -> int:
    """Approximate device count from devices seen in the last 24 h."""
    try:
        devices = store.query_known_devices()
        return len(devices) if devices else 0
    except Exception:  # non-fatal
        return 0

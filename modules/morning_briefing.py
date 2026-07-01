"""
modules/morning_briefing.py — Opt-in daily 3-bullet morning briefing (S8-1).

When enabled, NetSentinel shows one tray notification per day (at a configurable
hour, default 8am) summarising overnight network activity: status, anything new,
and a quick stat. Disabled by default.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected — never instantiated here.
  • QSettings accessed via a callable getter/setter, not imported directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from modules.proactive_digest import DigestConfig, is_due

# ── QSettings keys ────────────────────────────────────────────────────────────
ENABLED_KEY   = "briefing/enabled"
HOUR_KEY      = "briefing/hour"          # 0-23, default 8
LAST_SENT_KEY = "briefing/last_sent_day"

_DEFAULT_HOUR = 8

_DIGEST_CONFIG = DigestConfig(ENABLED_KEY, HOUR_KEY, LAST_SENT_KEY, _DEFAULT_HOUR)


@dataclass
class BriefingResult:
    """Returned when a morning briefing notification should be shown."""
    headline: str = "Your morning briefing"
    bullets:  List[str] = field(default_factory=list)


def check_and_build_briefing(
    store,
    settings_get: Callable[[str], object],
    settings_set: Callable[[str, object], None],
) -> Optional[BriefingResult]:
    """Return a ``BriefingResult`` if the daily briefing is due, else None."""
    if not is_due(_DIGEST_CONFIG, settings_get, settings_set):
        return None

    bullets = build_briefing_bullets(store)
    return BriefingResult(headline="Your morning briefing", bullets=bullets)


def build_briefing_bullets(store) -> List[str]:
    """Compose the three plain-English bullets from already-collected data."""
    return [
        _status_bullet(store),
        _overnight_bullet(store),
        _quick_stat_bullet(store),
    ]


# ── Bullet builders ────────────────────────────────────────────────────────────

def _status_bullet(store) -> str:
    try:
        from modules.health_score import HealthScoreCalculator
        snapshot = HealthScoreCalculator().compute(store)
        return f"Network status: {snapshot.headline}"
    except Exception:
        return "Network status: unavailable"


def _overnight_bullet(store) -> str:
    try:
        joined = store.query_device_events(hours=24.0, event_types=["JOINED"])
        n_new = len(joined)
    except Exception:
        n_new = 0
    try:
        noisy = [
            a for a in store.get_recent_alerts(hours=24.0, limit=50)
            if a.get("severity", "").upper() in ("CRITICAL", "WARNING")
        ]
        n_alerts = len(noisy)
    except Exception:
        n_alerts = 0

    if n_new == 0 and n_alerts == 0:
        return "Overnight: nothing unusual — no new devices or alerts."
    parts = []
    if n_new:
        parts.append(f"{n_new} new device{'s' if n_new != 1 else ''} joined")
    if n_alerts:
        parts.append(f"{n_alerts} alert{'s' if n_alerts != 1 else ''} fired")
    return "Overnight: " + " and ".join(parts) + "."


def _quick_stat_bullet(store) -> str:
    try:
        rows = store.query_speed_test_history(hours=24.0, limit=1)
    except Exception:
        rows = []
    if rows:
        dl = rows[0].download_mbps or 0.0
        return f"Last speed test: {dl:.0f} Mbps download."
    return "No speed test run in the last 24 hours."

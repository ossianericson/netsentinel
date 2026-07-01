"""
modules/proactive_digest.py — generalized due-check/day-tracking for once-daily
proactive digests (Sprint 2 foundation).

Extracted from morning_briefing.py's original check_and_build_briefing() gating
so future once-daily digests reuse the same enabled/hour/last-sent logic instead
of re-deriving it. morning_briefing.py is now a thin wrapper over this module;
its QSettings keys and behavior are unchanged.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • QSettings accessed via a callable getter/setter, not imported directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class DigestConfig:
    """QSettings key triple + default hour for a once-daily digest."""
    enabled_key: str
    hour_key: str
    last_sent_key: str
    default_hour: int = 8


def is_due(
    config: DigestConfig,
    settings_get: Callable[[str], object],
    settings_set: Callable[[str, object], None],
) -> bool:
    """
    Return True and mark today as sent if a once-daily digest gated by
    ``config`` is due right now. Returns False (with no side effect) if the
    digest is disabled, already sent today, or the configured hour hasn't
    arrived yet.
    """
    if not _truthy(settings_get(config.enabled_key)):
        return False

    today_str = time.strftime("%Y-%m-%d", time.localtime())
    if settings_get(config.last_sent_key) == today_str:
        return False

    configured_hour = _int_val(settings_get(config.hour_key), config.default_hour)
    if time.localtime().tm_hour < configured_hour:
        return False

    settings_set(config.last_sent_key, today_str)
    return True


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

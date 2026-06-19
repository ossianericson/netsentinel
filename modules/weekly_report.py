"""
modules/weekly_report.py — Weekly network narrative for the home page (S8-3).

Builds the plain-English bullet list shown on the home page "Your Network
Last Week" card. Reuses the same MetricStore queries as digest_builder.py
and traffic_insights.py — no new persisted data, no PyQt imports.
"""
from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

_WEEK_HOURS = 168.0


def build_weekly_report_bullets(
    store: "MetricStore", plan_speed_mbps: float = 0.0,
) -> List[str]:
    """Return up to four plain-English bullets summarising the last 7 days."""
    bullets = [
        _uptime_bullet(store),
        _speed_bullet(store, plan_speed_mbps),
        _new_devices_bullet(store),
        _usage_bullet(store),
    ]
    return [b for b in bullets if b]


def _uptime_bullet(store) -> Optional[str]:
    try:
        rows = store.query_uptime_table(hours_list=[_WEEK_HOURS])
    except Exception:
        return None
    pcts = [r.get(str(_WEEK_HOURS)) for r in rows if r.get(str(_WEEK_HOURS)) is not None]
    if not pcts:
        return None
    avg_pct = sum(pcts) / len(pcts)
    up_hours = avg_pct / 100.0 * _WEEK_HOURS
    days = int(up_hours // 24)
    hours = int(up_hours % 24)
    return f"{days} day{'s' if days != 1 else ''} {hours} hour{'s' if hours != 1 else ''} uptime ({avg_pct:.1f}%)"


def _speed_bullet(store, plan_speed_mbps: float) -> Optional[str]:
    try:
        rows = store.query_speed_test_history(hours=_WEEK_HOURS, limit=200)
    except Exception:
        return None
    if not rows:
        return None
    avg_dl = sum(r.download_mbps or 0.0 for r in rows) / len(rows)
    text = f"Speed averaged {avg_dl:.0f} Mbps"
    if plan_speed_mbps > 0:
        text += f" (plan: {plan_speed_mbps:.0f} Mbps)"
    return text


def _new_devices_bullet(store) -> Optional[str]:
    try:
        joined = store.query_device_events(hours=_WEEK_HOURS, event_types=["JOINED"])
    except Exception:
        return None
    n = len(joined)
    if n == 0:
        return "No new devices joined this week."
    return f"{n} new device{'s' if n != 1 else ''} joined"


def _usage_bullet(store) -> Optional[str]:
    try:
        from modules.traffic_insights import format_bytes
        totals = store.query_app_traffic_category_totals(hours=_WEEK_HOURS)
    except Exception:
        return None
    if not totals:
        return None
    total_bytes = sum(totals.values())
    if total_bytes == 0:
        return None
    dominant_category, dominant_bytes = max(totals.items(), key=lambda kv: kv[1])
    dominant_pct = (dominant_bytes / total_bytes) * 100.0
    return (
        f"Household used {format_bytes(total_bytes)} "
        f"— {dominant_category.lower()} was {dominant_pct:.0f}%"
    )

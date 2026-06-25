"""
alert_pattern_detector — pattern-based maintenance suppression suggestions (S4-6).

Analyses the last 21 days of ``alert_fired`` history and looks for alerts
that fire at the same time of day on the same day of week across three or
more separate weeks.  When found, it offers to create a MaintenanceWindow
to suppress them automatically.

The detector never auto-suppresses anything — it only returns suggestions
that the user can accept or dismiss from the Notifications page.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • MetricStore injected — never instantiated here.
  • No third-party packages — only stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Tuple
import datetime

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


# ── Tuning constants ──────────────────────────────────────────────────────────
_ANALYSIS_DAYS       = 21   # look back this many days
_MIN_OCCURRENCES     = 3    # same rule+host at same hour across this many weeks
_WINDOW_BUFFER_MINS  = 30   # maintenance window extends ±this long beyond the alert hour


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SuppSuggestion:
    """A candidate maintenance window inferred from repeated alert patterns."""
    rule_name:        str
    host:             str
    day_of_week:      int        # 0=Mon … 6=Sun
    hour_of_day:      int        # local hour (0–23)
    occurrences:      int        # how many times this pattern was seen
    suggested_label:  str        # human-readable window name, e.g. "Monday 2am auto-quiet"
    window_start_h:   int        # local hour when window should open
    window_start_m:   int        # local minute when window should open (always 0 or 30)
    window_end_h:     int        # local hour when window should close
    window_end_m:     int        # local minute when window should close
    description:      str        # plain-English description for the user

    @property
    def day_name(self) -> str:
        return ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"][self.day_of_week % 7]


# ── Core detector ─────────────────────────────────────────────────────────────

class PatternDetector:
    """
    Detect repeated alert patterns and suggest maintenance windows.

    Usage
    -----
    detector = PatternDetector()
    suggestions = detector.find_suggestions(store)
    for s in suggestions:
        print(s.description)
    """

    def find_suggestions(self, store: MetricStore) -> List[SuppSuggestion]:
        """
        Return a list of ``SuppSuggestion`` instances for patterns detected
        in the last 21 days of alert history.  Returns an empty list on any
        error to ensure callers are never broken by detection failures.
        """
        try:
            alerts = store.get_recent_alerts(hours=_ANALYSIS_DAYS * 24.0, limit=5000)
        except Exception:
            return []

        if not alerts:
            return []

        # Index: (rule_name, host, day_of_week, hour) → list of ISO week numbers
        pattern: Dict[Tuple[str, str, int, int], List[int]] = {}

        for alert in alerts:
            rule_name = alert.get("rule_name", "")
            host      = alert.get("host", "")
            ts        = alert.get("ts")
            severity  = alert.get("severity", "").upper()

            # Only look at warning/critical alerts — resolution and info are not patterns
            if severity not in ("WARNING", "CRITICAL"):
                continue
            if not rule_name or not host or not ts:
                continue

            try:
                dt = datetime.datetime.fromtimestamp(float(ts))
            except (TypeError, ValueError, OSError):
                continue

            dow  = dt.weekday()    # 0=Mon
            hour = dt.hour
            week = dt.isocalendar()[1]  # ISO week number

            key = (rule_name, host, dow, hour)
            pattern.setdefault(key, []).append(week)

        suggestions: List[SuppSuggestion] = []
        seen_keys: set = set()

        for (rule_name, host, dow, hour), weeks in pattern.items():
            unique_weeks = set(weeks)
            if len(unique_weeks) < _MIN_OCCURRENCES:
                continue

            # Avoid duplicating adjacent hours (e.g. hour=2 and hour=3 same event)
            dedup_key = (rule_name, host, dow, hour // 2)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            start_h, start_m, end_h, end_m = _window_bounds(hour)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                         "Friday", "Saturday", "Sunday"]
            day_name = day_names[dow % 7]

            label = f"{day_name} {hour:02d}:00 auto-quiet"
            desc = (
                f"The alert \"{rule_name}\" on {host} has fired every {day_name} "
                f"around {hour:02d}:00 for {len(unique_weeks)} weeks in a row. "
                f"This looks like a scheduled maintenance or ISP event. "
                f"Want to suppress alerts for this host between "
                f"{start_h:02d}:{start_m:02d} and {end_h:02d}:{end_m:02d} on {day_name}s?"
            )

            suggestions.append(SuppSuggestion(
                rule_name=rule_name,
                host=host,
                day_of_week=dow,
                hour_of_day=hour,
                occurrences=len(unique_weeks),
                suggested_label=label,
                window_start_h=start_h,
                window_start_m=start_m,
                window_end_h=end_h,
                window_end_m=end_m,
                description=desc,
            ))

        # Sort by most frequent patterns first
        suggestions.sort(key=lambda s: s.occurrences, reverse=True)
        return suggestions[:10]   # cap at 10 suggestions to avoid UI clutter


# ── Helpers ───────────────────────────────────────────────────────────────────

def _window_bounds(hour: int) -> Tuple[int, int, int, int]:
    """
    Return (start_h, start_m, end_h, end_m) for a maintenance window that
    covers ``hour`` with ``_WINDOW_BUFFER_MINS`` on each side.
    """
    total_start_mins = max(0, hour * 60 - _WINDOW_BUFFER_MINS)
    total_end_mins   = min(23 * 60 + 59, hour * 60 + 60 + _WINDOW_BUFFER_MINS)

    start_h, start_m = divmod(total_start_mins, 60)
    end_h,   end_m   = divmod(total_end_mins,   60)
    return start_h, start_m, end_h, end_m

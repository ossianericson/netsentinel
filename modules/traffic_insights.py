"""
modules/traffic_insights.py — Pure data-driven traffic narrative builders (Sprint 6).

Turns raw category/hourly byte totals (already aggregated by MetricStore
queries in metric_store_queries_metrics.py) into the plain-English summaries
used by the home page "Usage insights" card (S6-3), the optional ISP plan
utilization line (S6-4), and the QoS overlap recommendation (S6-5).

No PyQt, no DB access — every function takes plain dicts/numbers and returns
plain dataclasses or strings, per ARCH RULE 1 (module layer has no UI deps).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


def format_bytes(n: int) -> str:
    """Human-readable byte count, scaling up to TB."""
    if n >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.1f} TB"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} GB"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"


# ── S6-3: Usage insights ───────────────────────────────────────────────────

@dataclass
class UsageInsight:
    has_data: bool
    household_total_bytes: int = 0
    dominant_category: Optional[str] = None
    dominant_pct: float = 0.0
    peak_window: Optional[Tuple[int, int]] = None   # (start_hour, end_hour), end exclusive
    change_category: Optional[str] = None
    change_pct: Optional[float] = None              # positive = increase vs last week


def _find_peak_window(hourly: Dict[int, int]) -> Optional[Tuple[int, int]]:
    """Find the contiguous hour range carrying most of one category's traffic."""
    nonzero = {h: b for h, b in hourly.items() if b > 0}
    if not nonzero:
        return None
    peak_hour = max(nonzero, key=lambda h: nonzero[h])
    threshold = nonzero[peak_hour] * 0.5

    start = end = peak_hour
    # expand left/right while neighbouring hours are still "busy", capped at a 5-hour span
    while end - start < 4 and hourly.get((end + 1) % 24, 0) >= threshold and (end + 1) % 24 in nonzero:
        end += 1
    while end - start < 4 and hourly.get((start - 1) % 24, 0) >= threshold and (start - 1) % 24 in nonzero:
        start -= 1
    return (start % 24, (end + 1) % 24)


def format_hour_range(window: Tuple[int, int]) -> str:
    """Format an (start, end) 24h hour window as '7pm and 11pm'."""
    def _fmt(h: int) -> str:
        h = h % 24
        if h == 0:
            return "12am"
        if h == 12:
            return "12pm"
        return f"{h % 12}am" if h < 12 else f"{h % 12}pm"
    start, end = window
    return f"{_fmt(start)} and {_fmt(end)}"


def build_usage_insights(
    category_totals: Dict[str, int],
    dominant_category_hourly: Optional[Dict[int, int]] = None,
    last_week_category_totals: Optional[Dict[str, int]] = None,
    change_category: str = "Gaming",
) -> UsageInsight:
    """Build a household usage narrative from this week's category totals.

    `dominant_category_hourly` should be the hourly distribution for whichever
    category turns out to be dominant (callers query it after totals are known,
    or pass None to skip the peak-window sentence).
    `change_category` is the category tracked for the week-over-week trend line
    (defaults to "Gaming" per the S6-3 backlog example).
    """
    total = sum(category_totals.values())
    if total <= 0:
        return UsageInsight(has_data=False)

    dominant_cat, dominant_bytes = max(category_totals.items(), key=lambda kv: kv[1])
    dominant_pct = dominant_bytes / total * 100

    peak_window = _find_peak_window(dominant_category_hourly) if dominant_category_hourly else None

    change_pct: Optional[float] = None
    if last_week_category_totals is not None:
        last = last_week_category_totals.get(change_category, 0)
        this = category_totals.get(change_category, 0)
        if last > 0:
            change_pct = (this - last) / last * 100
        elif this > 0:
            change_pct = 100.0

    return UsageInsight(
        has_data=True,
        household_total_bytes=total,
        dominant_category=dominant_cat,
        dominant_pct=dominant_pct,
        peak_window=peak_window,
        change_category=change_category if change_pct is not None else None,
        change_pct=change_pct,
    )


def format_insight_summary(insight: UsageInsight) -> str:
    """Compose the full plain-English narrative sentence(s) (S6-3)."""
    if not insight.has_data:
        return "Not enough traffic data yet — start App Traffic monitoring to see usage insights."

    parts = [f"Your household used {format_bytes(insight.household_total_bytes)} this week."]

    if insight.dominant_category:
        cat_sentence = f"Most was {insight.dominant_category.lower()} ({insight.dominant_pct:.0f}%)"
        if insight.peak_window:
            cat_sentence += f", mainly between {format_hour_range(insight.peak_window)}"
        parts.append(cat_sentence + ".")

    if insight.change_category and insight.change_pct is not None:
        direction = "increased" if insight.change_pct >= 0 else "decreased"
        parts.append(
            f"{insight.change_category} traffic {direction} "
            f"{abs(insight.change_pct):.0f}% vs last week."
        )

    return " ".join(parts)


# ── S6-4: ISP plan comparison ─────────────────────────────────────────────

def compute_plan_utilization(used_bytes: int, monthly_cap_gb: Optional[float]) -> Optional[str]:
    """Return 'You used X% of your monthly data cap.' or None if no plan is configured."""
    if not monthly_cap_gb or monthly_cap_gb <= 0:
        return None
    cap_bytes = monthly_cap_gb * 1_000_000_000
    pct = used_bytes / cap_bytes * 100
    return f"You used {pct:.0f}% of your monthly data cap."


# ── S6-5: QoS overlap recommendation ──────────────────────────────────────

def find_category_overlap_window(
    hourly_a: Dict[int, int], hourly_b: Dict[int, int], min_frac: float = 0.3,
) -> Optional[Tuple[int, int]]:
    """Find hours where both categories are simultaneously busy.

    "Busy" means the hour's bytes are at least `min_frac` of that category's own
    peak hour. Returns the contiguous overlapping window, or None if the two
    categories never significantly overlap.
    """
    if not hourly_a or not hourly_b:
        return None
    peak_a = max(hourly_a.values(), default=0)
    peak_b = max(hourly_b.values(), default=0)
    if peak_a <= 0 or peak_b <= 0:
        return None

    busy_hours = sorted(
        h for h in range(24)
        if hourly_a.get(h, 0) >= peak_a * min_frac and hourly_b.get(h, 0) >= peak_b * min_frac
    )
    if not busy_hours:
        return None

    # Return the widest contiguous run of overlapping hours.
    best_start = best_end = run_start = busy_hours[0]
    for prev, cur in zip(busy_hours, busy_hours[1:]):
        if cur == prev + 1:
            run_end = cur
            if run_end - run_start > best_end - best_start:
                best_start, best_end = run_start, run_end
        else:
            run_start = cur
    return (best_start, best_end + 1)


def build_qos_recommendation(
    category_a: str, hourly_a: Dict[int, int],
    category_b: str, hourly_b: Dict[int, int],
) -> Optional[str]:
    """Compose a QoS suggestion sentence if two categories overlap most days (S6-5)."""
    window = find_category_overlap_window(hourly_a, hourly_b)
    if not window or window[1] - window[0] < 2:
        return None
    return (
        f"{category_a} and {category_b} traffic overlap between "
        f"{format_hour_range(window)} most days. Consider QoS prioritisation "
        f"for those devices."
    )

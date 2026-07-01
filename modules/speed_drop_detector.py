"""
modules/speed_drop_detector.py — flags a speed test result that is a severe
relative drop against the user's own recent typical download speed.

The absolute-threshold check in modules/root_cause_correlator.py only fires
below 5 Mbps. A user whose line normally does ~740 Mbps but drops to ~94 Mbps
never crosses that floor, yet the drop is actionable. This module compares
the latest download speed against the median of recent prior tests and
classifies the relative drop.

Architecture rules
-------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • No DB access — caller supplies prior download speeds already queried.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


RESTART_CHECKLIST = [
    "Restart your mesh router/Wi-Fi and wait about 2 minutes",
    "If still slow, restart your 5G modem/ONT",
    "Re-run the speed test",
    "If unchanged, contact your ISP and quote this measurement",
]


@dataclass
class SpeedDropVerdict:
    is_drop: bool
    severity: str  # "" | "Warning" | "High"
    current_mbps: float
    typical_mbps: float
    drop_pct: float
    headline: str
    steps: List[str] = field(default_factory=lambda: list(RESTART_CHECKLIST))


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def evaluate_speed_drop(
    current_mbps: float,
    prior_downloads: List[float],
    *,
    min_samples: int = 4,
    floor_mbps: float = 25.0,
    warn_pct: float = 50.0,
    high_pct: float = 75.0,
) -> SpeedDropVerdict:
    no_drop = SpeedDropVerdict(
        is_drop=False,
        severity="",
        current_mbps=current_mbps,
        typical_mbps=0.0,
        drop_pct=0.0,
        headline="",
        steps=[],
    )

    if current_mbps <= 0 or len(prior_downloads) < min_samples:
        return no_drop

    typical = _median(prior_downloads)
    if typical < floor_mbps:
        return no_drop

    drop_pct = max(0.0, (typical - current_mbps) / typical * 100.0)
    if drop_pct < warn_pct:
        return no_drop

    severity = "High" if drop_pct >= high_pct else "Warning"
    headline = (
        f"Download down {drop_pct:.0f}% — {current_mbps:.0f} Mbps vs "
        f"your usual ~{typical:.0f} Mbps"
    )
    return SpeedDropVerdict(
        is_drop=True,
        severity=severity,
        current_mbps=current_mbps,
        typical_mbps=typical,
        drop_pct=drop_pct,
        headline=headline,
        steps=list(RESTART_CHECKLIST),
    )

"""
lab_achievements — pure badge/curriculum-coverage math for Lab Mode (Scoreboard feature).

Operates on the same lab/progress dict shape as modules/lab_progress.py and the
SCENARIOS list from modules/lab_scenarios.py. No Qt, no I/O beyond the cached
JSON read inside modules/curriculum_map.py — this module stays unit-testable
without a QApplication.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from modules.curriculum_map import cert_for_objective, objectives_for_scenario
from modules.lab_progress import best_verdict, is_complete, summary


@dataclass(frozen=True)
class BadgeState:
    scenario_id:  str
    title:        str
    earned:       bool
    earned_at:    str          # "" when not earned; "YYYY-MM-DD" (date only) when earned
    best_verdict: str          # "" when not earned
    attempts:     int          # 0 when not earned
    protocol:     "str | None"  # carried through for the "See how X works" cross-sell


def badge_states(progress: dict, scenarios: list) -> List[BadgeState]:
    """One BadgeState per scenario, in SCENARIOS order. Never filters — locked badges
    must render too, so the grid is stable and shows what is still available."""
    states = []
    for scenario in scenarios:
        earned = is_complete(progress, scenario.id)
        entry = progress.get(scenario.id, {}) if earned else {}
        states.append(BadgeState(
            scenario_id=scenario.id,
            title=scenario.title,
            earned=earned,
            earned_at=entry.get("completed_at", "")[:10] if earned else "",
            best_verdict=(best_verdict(progress, scenario.id) or "") if earned else "",
            attempts=entry.get("attempts", 0) if earned else 0,
            protocol=scenario.protocol,
        ))
    return states


def earned_count(progress: dict, scenarios: list) -> tuple[int, int]:
    """(earned, total). Delegates to lab_progress.summary() — do not reimplement."""
    return summary(progress, len(scenarios))


def curriculum_coverage(progress: dict, scenarios: list) -> dict:
    """{"Network+": (6, 8), "CCNA": (3, 6), "Security+": (2, 5)}

    Denominator: distinct objective strings across ALL scenarios, attributed to a cert
    via curriculum_map.cert_for_objective().
    Numerator:   the same, restricted to scenarios the user has earned.
    Certs with a zero denominator are omitted from the result entirely.
    """
    all_by_cert: dict = {}
    earned_by_cert: dict = {}
    for scenario in scenarios:
        earned = is_complete(progress, scenario.id)
        for objective in objectives_for_scenario(scenario.title):
            cert = cert_for_objective(objective)
            if cert is None:
                continue
            all_by_cert.setdefault(cert, set()).add(objective)
            if earned:
                earned_by_cert.setdefault(cert, set()).add(objective)
    return {
        cert: (len(earned_by_cert.get(cert, set())), len(objectives))
        for cert, objectives in all_by_cert.items()
    }

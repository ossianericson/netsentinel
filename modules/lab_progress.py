"""
lab_progress — pure progress-tracking logic for Lab Mode (Lab Mode Upgrade Phase L2).

Operates on a plain JSON-serialisable dict shaped as::

    {scenario_id: {"completed_at": str, "verdict": str,
                    "best_verdict": str, "attempts": int}}

The page owns QSettings I/O (key "lab/progress") and passes this dict in/out —
this module stays Qt-free and unit-testable. No MetricStore schema migration
needed; the state is small (at most one entry per scenario in modules/lab_scenarios.py).
"""
from __future__ import annotations

from typing import Optional

_VERDICT_RANK = {"INCOMPLETE": 0, "PARTIAL": 1, "PASS": 2}


def mark_complete(state: dict, scenario_id: str, result_dict: dict) -> dict:
    """Record a completed attempt, keeping the best verdict ever achieved for it."""
    verdict = result_dict.get("verdict") or "INCOMPLETE"
    existing = state.get(scenario_id, {})
    prior_best = existing.get("best_verdict", verdict)
    best = (
        verdict
        if _VERDICT_RANK.get(verdict, 0) > _VERDICT_RANK.get(prior_best, 0)
        else prior_best
    )
    state[scenario_id] = {
        "completed_at": result_dict.get("completed_at", ""),
        "verdict": verdict,
        "best_verdict": best,
        "attempts": existing.get("attempts", 0) + 1,
    }
    return state


def is_complete(state: dict, scenario_id: str) -> bool:
    return scenario_id in state


def summary(state: dict, total: int) -> tuple[int, int]:
    """Return (distinct scenarios completed at least once, total scenario count)."""
    return (len(state), total)


def best_verdict(state: dict, scenario_id: str) -> Optional[str]:
    entry = state.get(scenario_id)
    return entry.get("best_verdict") if entry else None

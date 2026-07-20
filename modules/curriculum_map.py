"""
curriculum_map — Qt-free loader for data/curriculum_map.json.

Single shared copy of the loader previously duplicated inside
ui/widgets/objective_badge.py (which imports PyQt6 and therefore cannot be
imported from modules/, per ARCH RULE 1). Both the UI badge widget and the
Qt-free Lab Mode achievement math (modules/lab_achievements.py) read through
this module.
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_curriculum_map() -> dict:
    try:
        if hasattr(sys, "_MEIPASS"):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent.parent
        path = base / "data" / "curriculum_map.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def entry_for(category: str, key: str) -> dict:
    m = load_curriculum_map()
    return m.get(category, {}).get(key, {})


def objectives_for_scenario(title: str) -> list[str]:
    return entry_for("lab_scenarios", title).get("objectives", [])


def certifications_for_scenario(title: str) -> list[str]:
    return entry_for("lab_scenarios", title).get("certifications", [])


# An objective string is attributed to a certification by its exam-code prefix.
_CERT_BY_PREFIX = {"N10-009": "Network+", "CCNA": "CCNA", "SY0-701": "Security+"}


def cert_for_objective(objective: str) -> str | None:
    """Map 'N10-009 2.1 — ...' -> 'Network+'. Returns None for unrecognised prefixes."""
    prefix = objective.split(" ", 1)[0] if objective else ""
    return _CERT_BY_PREFIX.get(prefix)

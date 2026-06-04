"""
onboarding.py — QSettings helpers for the first-run coach mark flow.

QSettings key: ui/onboarding_v2_done
  True  → user has seen the pre-scan coach mark; do not show again.
  False / absent → show pre-scan CoachMarkChain on next launch.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings

_SETTINGS_KEY = "ui/onboarding_v2_done"
_TOUR_KEY     = "tour/v1_done"


def should_show_onboarding() -> bool:
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(_SETTINGS_KEY, False, type=bool)


def mark_onboarding_done() -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_SETTINGS_KEY, True)
    qs.setValue(_TOUR_KEY, True)

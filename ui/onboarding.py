"""
onboarding.py — Thin shim for the Apple-like onboarding flow (Sprint I1+).

The full onboarding UI lives in ui/widgets/onboarding_overlay.py.
This module only provides the QSettings helpers used by OnboardingOverlay
and by dashboard._maybe_start_onboarding().

QSettings key: ui/onboarding_v2_done
  True  → user has completed (or skipped) onboarding; overlay is not shown.
  False / absent → show OnboardingOverlay on next launch.

Reuses the same key as the old OnboardingOrchestrator so that existing users
who completed the previous onboarding are not shown the new overlay.
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

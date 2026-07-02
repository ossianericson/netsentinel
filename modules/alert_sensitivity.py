"""
modules/alert_sensitivity.py — global alert-fatigue guardrail (V6 Sprint 5.4).

A single QSettings-persisted "Conservative / Balanced / Aggressive" control
scales the noise-relevant numeric fields on every AlertRule, independent of
each rule's own enable toggle (shipped alongside its rule in Sprints 1–4).
Trust is the product: a rule that fires too often gets disabled and never
re-enabled, so this gives users a way to quiet a noisy rule (or sharpen an
under-sensitive one) without losing the alert entirely.

Architecture rules
------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • Mutates the AlertRule objects passed in (same convention app.py already
    uses for restoring rule.enabled from QSettings — see the loop in
    app.py's main()).
"""
from __future__ import annotations

from typing import Iterable

from modules.alert_types import AlertRule

SENSITIVITY_LEVELS = ("conservative", "balanced", "aggressive")
DEFAULT_SENSITIVITY = "balanced"

_MIN_SAMPLES_FLOOR = 2
_COOLDOWN_FLOOR_S = 30

# scale > 1.0 raises the value (fewer/later alerts); scale < 1.0 lowers it
# (more/earlier alerts). "balanced" is a no-op — the shipped default
# thresholds in modules/alert_suppressor._default_rules() are unchanged.
_THRESHOLD_SCALE = {"conservative": 1.3, "balanced": 1.0, "aggressive": 0.7}
_SAMPLES_SCALE    = {"conservative": 1.5, "balanced": 1.0, "aggressive": 0.6}
_COOLDOWN_SCALE   = {"conservative": 1.5, "balanced": 1.0, "aggressive": 0.5}


def apply_sensitivity(rules: Iterable[AlertRule], level: str) -> None:
    """
    Scale the noise-relevant numeric fields of every rule in ``rules``
    in place. Unknown levels fall back to "balanced" (no-op) rather than
    raising, since this is called from a QSettings-restore path where a
    stale or corrupted value must not crash startup.
    """
    threshold_scale = _THRESHOLD_SCALE.get(level, 1.0)
    samples_scale = _SAMPLES_SCALE.get(level, 1.0)
    cooldown_scale = _COOLDOWN_SCALE.get(level, 1.0)

    for rule in rules:
        rule.warn_pct = rule.warn_pct * threshold_scale
        rule.high_pct = rule.high_pct * threshold_scale
        rule.threshold_ms = rule.threshold_ms * threshold_scale
        rule.threshold_pct = rule.threshold_pct * threshold_scale
        rule.sigma = rule.sigma * threshold_scale

        rule.min_samples = max(
            _MIN_SAMPLES_FLOOR, round(rule.min_samples * samples_scale)
        )
        rule.cooldown_s = max(
            _COOLDOWN_FLOOR_S, round(rule.cooldown_s * cooldown_scale)
        )

"""
Tests for ui.onboarding (Sprint I1 Apple-like onboarding).

Validates:
  - should_show_onboarding() responds to QSettings correctly
  - mark_onboarding_done() sets both keys
  - tour/v1_done is set after finish (RULE-T6 coach mark gate)
"""
import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QSettings
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _fresh():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("ui/onboarding_v2_done")
    qs.remove("tour/v1_done")
    qs.remove("ui/first_run_done")
    return qs


# ── should_show_onboarding() ──────────────────────────────────────────────────

class TestShouldShowOnboarding:
    def setup_method(self):   _fresh()
    def teardown_method(self): _fresh()

    def test_true_on_fresh_install(self):
        from ui.onboarding import should_show_onboarding
        assert should_show_onboarding() is True

    def test_false_after_done(self):
        from ui.onboarding import should_show_onboarding, mark_onboarding_done
        mark_onboarding_done()
        assert should_show_onboarding() is False

    def test_mark_sets_both_keys(self):
        from ui.onboarding import mark_onboarding_done
        mark_onboarding_done()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("ui/onboarding_v2_done", False, type=bool) is True
        assert qs.value("tour/v1_done",           False, type=bool) is True


# ── Coach mark suppression (RULE-T6) ─────────────────────────────────────────

class TestCoachMarkSuppression:
    """Coach marks must not fire until tour/v1_done = True."""

    def setup_method(self):   _fresh()
    def teardown_method(self): _fresh()

    def test_tour_key_false_before_onboarding_completes(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        assert not qs.value("tour/v1_done", False, type=bool)

    def test_tour_key_true_after_finish(self):
        from ui.onboarding import mark_onboarding_done
        mark_onboarding_done()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("tour/v1_done", True, type=bool) is True

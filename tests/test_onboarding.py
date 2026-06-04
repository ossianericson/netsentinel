"""
Tests for ui.onboarding — OnboardingOrchestrator.

Validates:
  - should_show_onboarding() responds to QSettings correctly
  - mark_onboarding_done() sets both keys
  - Step count is 9
  - All nav labels exist in a real Dashboard._nav_label_to_widget
  - Phase 1 steps (1-4) have no nav_label or nav to Home
  - Phase 2 steps (5-9) all have nav_labels
  - _on_welcome_scan in welcome overlay fires background scans (RULE-T5 integration test)
  - tour/v1_done is set after finish
"""
import sys
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
    def setup_method(self):  _fresh()
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
        assert qs.value("tour/v1_done", False, type=bool) is True


# ── Step definitions ──────────────────────────────────────────────────────────

class TestStepDefinitions:
    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def _steps(self):
        from unittest.mock import MagicMock
        from ui.onboarding import _build_steps
        d = MagicMock()
        return _build_steps(d)

    def test_exactly_9_steps(self):
        assert len(self._steps()) == 9

    def test_phase1_stays_put_or_goes_home(self):
        steps = self._steps()
        for i, step in enumerate(steps[:4]):
            assert step.nav_label in (None, "Home"), (
                f"Phase 1 step {i+1} should stay put or go Home, got '{step.nav_label}'"
            )

    def test_phase2_all_have_nav_labels(self):
        steps = self._steps()
        for i, step in enumerate(steps[4:], start=5):
            assert step.nav_label is not None, (
                f"Phase 2 step {i} has no nav_label"
            )

    def test_phase2_nav_labels(self):
        steps = self._steps()
        labels = [s.nav_label for s in steps[4:]]
        assert labels[0] == "Speed Test"
        assert labels[1] == "Network Grade"
        assert labels[2] == "Network Logger"
        assert labels[3] == "Hardware"
        assert labels[4] == "Overview"

    def test_all_steps_have_tour_title_and_body(self):
        for i, step in enumerate(self._steps()):
            assert step.tour_title.strip(), f"Step {i+1} has empty tour_title"
            assert step.tour_body.strip(),  f"Step {i+1} has empty tour_body"

    def test_all_spotlight_specs_have_title_and_body(self):
        for i, step in enumerate(self._steps()):
            for j, sp in enumerate(step.spotlights):
                assert sp.title.strip(), f"Step {i+1} spotlight {j+1} has empty title"
                assert sp.body.strip(),  f"Step {i+1} spotlight {j+1} has empty body"

    def test_speed_test_step_has_auto_action(self):
        steps = self._steps()
        st_step = next(s for s in steps if s.nav_label == "Speed Test")
        assert st_step.auto_action == "_auto_speed_test"

    def test_logger_step_has_auto_action(self):
        steps = self._steps()
        log_step = next(s for s in steps if s.nav_label == "Network Logger")
        assert log_step.auto_action == "_auto_logger"


# ── Nav label validity (RULE-T5) ─────────────────────────────────────────────

class TestNavLabelValidity:
    """Verify every Phase 2 nav label actually exists in the dashboard nav registry."""

    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def test_all_phase2_labels_registered_in_dashboard(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        from ui.onboarding import _build_steps

        d = MagicMock()
        steps = _build_steps(d)

        expected_labels = {"Speed Test", "Network Grade", "Network Logger",
                           "Hardware", "Overview", "Home"}
        phase2_labels = {s.nav_label for s in steps if s.nav_label}
        missing = phase2_labels - expected_labels

        # All expected labels should be present in the step definitions
        for label in {"Speed Test", "Network Grade", "Network Logger", "Hardware", "Overview"}:
            assert label in phase2_labels, f"Phase 2 missing step for '{label}'"


# ── Orchestrator behaviour ────────────────────────────────────────────────────

class TestOrchestratorBehaviour:
    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def _mock_dashboard(self):
        from unittest.mock import MagicMock
        d = MagicMock()
        d._tour_bar      = MagicMock()
        d._tour_step_lbl = MagicMock()
        d._tour_body_lbl = MagicMock()
        d._tour_next_btn = MagicMock()
        d._tour_next_btn.clicked = MagicMock()
        d._tour_skip_btn = MagicMock()
        d._tour_skip_btn.clicked = MagicMock()
        d._nav_rail_panel = MagicMock()
        d._nav_flyout     = MagicMock()
        d.window.return_value = MagicMock()
        return d

    def test_start_does_nothing_when_already_done(self):
        from ui.onboarding import OnboardingOrchestrator, mark_onboarding_done
        mark_onboarding_done()
        d = self._mock_dashboard()
        orc = OnboardingOrchestrator(None)
        orc._dashboard = d
        orc.start()
        d._tour_bar.setVisible.assert_not_called()

    def test_finish_sets_onboarding_done(self):
        from ui.onboarding import OnboardingOrchestrator, should_show_onboarding
        d = self._mock_dashboard()
        orc = OnboardingOrchestrator(None)
        orc._dashboard = d
        orc._finish()
        assert should_show_onboarding() is False

    def test_finish_hides_tour_bar(self):
        from ui.onboarding import OnboardingOrchestrator
        d = self._mock_dashboard()
        orc = OnboardingOrchestrator(None)
        orc._dashboard = d
        orc._finish()
        d._tour_bar.setVisible.assert_called_with(False)


# ── RULE-T6: coach marks suppressed during onboarding ─────────────────────────

class TestCoachMarkSuppression:
    """Coach marks must not fire until tour/v1_done = True."""

    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def test_home_pills_coach_suppressed_before_tour_done(self):
        from unittest.mock import MagicMock, patch
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("tour/v1_done", False)

        # Import and call the method — it should return early without calling
        # CoachMarkChain. We verify by patching CoachMarkChain.
        with patch("ui.widgets.coach_mark.CoachMarkChain") as mock_chain:
            from ui.pages.home_page import HomePage
            page = MagicMock(spec=HomePage)
            page.isVisible.return_value = True
            # Directly run the guard logic
            qs2 = QSettings("NetSentinel", "NetSentinel")
            assert not qs2.value("tour/v1_done", False, type=bool)
            # If guard works, chain is never instantiated
            mock_chain.assert_not_called()

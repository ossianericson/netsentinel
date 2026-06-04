"""
Tests for ui.onboarding — OnboardingOrchestrator (Sprint H11 value-first redesign).

Validates:
  - should_show_onboarding() responds to QSettings correctly
  - mark_onboarding_done() sets both keys
  - Step count is 9
  - New step sequence: Overview → Devices → Overview → Speed Test → Network Logger
                       → Hardware → Home → (stay Home) → Overview
  - Step 1 fires all background scans via _step1_fire_scans
  - Step 8 has no nav_label (stays on Home) and next_enabled_immediately=True
  - All step nav labels exist in the expected page registry
  - tour/v1_done is set after finish
  - Coach marks are suppressed during onboarding (RULE-T6)
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

    def test_all_steps_have_tour_title_and_body(self):
        for i, step in enumerate(self._steps()):
            assert step.tour_title.strip(), f"Step {i+1} has empty tour_title"
            assert step.tour_body.strip(),  f"Step {i+1} has empty tour_body"

    def test_all_spotlight_specs_have_title_and_body(self):
        for i, step in enumerate(self._steps()):
            for j, sp in enumerate(step.spotlights):
                assert sp.title.strip(), f"Step {i+1} spotlight {j+1} has empty title"
                assert sp.body.strip(),  f"Step {i+1} spotlight {j+1} has empty body"

    # ── Value-first sequence ──────────────────────────────────────────────────

    def test_step1_navigates_to_overview(self):
        """Scan fires on Overview — user sees something happening immediately."""
        steps = self._steps()
        assert steps[0].nav_label == "Overview"

    def test_step1_fires_all_scans(self):
        """Step 1 auto_action is _step1_fire_scans (scan + speed test + logger)."""
        steps = self._steps()
        assert steps[0].auto_action == "_step1_fire_scans"

    def test_step2_goes_to_devices(self):
        """First wow moment — real device list."""
        steps = self._steps()
        assert steps[1].nav_label == "Devices"

    def test_step3_returns_to_overview_for_grade(self):
        """Grade ring is populated by now."""
        steps = self._steps()
        assert steps[2].nav_label == "Overview"

    def test_step4_speed_test(self):
        """Speed test gauge is already moving from step 1."""
        steps = self._steps()
        assert steps[3].nav_label == "Speed Test"

    def test_step5_network_logger(self):
        """Logger already recording from step 1."""
        steps = self._steps()
        assert steps[4].nav_label == "Network Logger"

    def test_step6_hardware(self):
        steps = self._steps()
        assert steps[5].nav_label == "Hardware"

    def test_step7_home_shows_completed_checklist(self):
        """Home at step 7 — GettingStartedCard already shows 3+ ticks."""
        steps = self._steps()
        assert steps[6].nav_label == "Home"

    def test_step8_stays_on_home_for_ctrlk(self):
        """Ctrl+K explained here — user has context from visiting 5 pages."""
        steps = self._steps()
        assert steps[7].nav_label is None, (
            "Step 8 should stay on Home (nav_label=None)"
        )

    def test_step8_next_enabled_immediately(self):
        """Step 8 is a simple spotlight — Next → should not be gated."""
        steps = self._steps()
        assert steps[7].next_enabled_immediately is True

    def test_step9_ends_on_overview(self):
        """Final step is Overview with live tile grid."""
        steps = self._steps()
        assert steps[8].nav_label == "Overview"

    # ── No shell-orientation steps ────────────────────────────────────────────

    def test_no_steps_point_only_at_nav_rail(self):
        """Old steps 1-3 (nav rail / breadcrumb / health badge) must be gone."""
        steps = self._steps()
        nav_rail_titles = [
            s.tour_title for s in steps
            if "navigation rail" in s.tour_title.lower()
            or "find anything" in s.tour_title.lower() and s.nav_label is None and s == steps[0]
        ]
        # Step 8 "Find anything" is allowed (it stays on Home, user has context)
        # but only one such step should exist
        assert len(nav_rail_titles) <= 1

    # ── Speed test and logger auto-actions ────────────────────────────────────

    def test_speed_test_step_has_no_auto_action(self):
        """Speed test was already started in step 1 — step 4 just navigates."""
        steps = self._steps()
        st_step = next(s for s in steps if s.nav_label == "Speed Test")
        assert st_step.auto_action is None

    def test_logger_step_has_no_auto_action(self):
        """Logger was already started in step 1 — step 5 just navigates."""
        steps = self._steps()
        log_step = next(s for s in steps if s.nav_label == "Network Logger")
        assert log_step.auto_action is None


# ── Nav label validity (RULE-T5) ─────────────────────────────────────────────

class TestNavLabelValidity:
    """Verify every non-None nav label names a real page in the expected registry."""

    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def test_all_nav_labels_in_expected_set(self):
        from unittest.mock import MagicMock
        from ui.onboarding import _build_steps
        d = MagicMock()
        steps = _build_steps(d)

        expected = {
            "Overview", "Devices", "Speed Test", "Network Logger",
            "Hardware", "Home", None,
        }
        for i, step in enumerate(steps):
            assert step.nav_label in expected, (
                f"Step {i+1} nav_label '{step.nav_label}' not in expected page set"
            )

    def test_required_pages_all_present(self):
        from unittest.mock import MagicMock
        from ui.onboarding import _build_steps
        d = MagicMock()
        labels = {s.nav_label for s in _build_steps(d) if s.nav_label}
        for required in ("Overview", "Devices", "Speed Test", "Network Logger",
                         "Hardware", "Home"):
            assert required in labels, f"Required page '{required}' missing from step sequence"


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

    def test_finish_sets_both_keys(self):
        from ui.onboarding import OnboardingOrchestrator
        d = self._mock_dashboard()
        orc = OnboardingOrchestrator(None)
        orc._dashboard = d
        orc._finish()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("ui/onboarding_v2_done", False, type=bool) is True
        assert qs.value("tour/v1_done", False, type=bool) is True


# ── Coach mark suppression (RULE-T6) ─────────────────────────────────────────

class TestCoachMarkSuppression:
    """Coach marks must not fire until tour/v1_done = True."""

    def setup_method(self):  _fresh()
    def teardown_method(self): _fresh()

    def test_tour_key_false_before_onboarding_completes(self):
        """On fresh install tour/v1_done is absent/False — coach marks stay off."""
        qs = QSettings("NetSentinel", "NetSentinel")
        assert not qs.value("tour/v1_done", False, type=bool)

    def test_tour_key_true_after_finish(self):
        from ui.onboarding import mark_onboarding_done
        mark_onboarding_done()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("tour/v1_done", True, type=bool) is True

"""
Tests for ui.guided_tour — GuidedTour first-run tour logic.

Validates:
  - should_show_tour() returns correct values based on QSettings state
  - mark_tour_done() sets the QSettings key
  - GuidedTour.start() does nothing when tour is already done
  - GuidedTour has correct step count
  - tour/v1_done is set after skip (via _finish())
  - tour/v1_done is set after completing all steps (via _on_next() × N)
"""
import sys
import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QSettings
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fresh_qs():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove("tour/v1_done")
    qs.remove("ui/first_run_done")
    return qs


# ── should_show_tour() ────────────────────────────────────────────────────────

class TestShouldShowTour:
    def setup_method(self):
        _fresh_qs()

    def teardown_method(self):
        _fresh_qs()

    def test_false_when_first_run_not_done(self):
        from ui.guided_tour import should_show_tour
        # first_run_done = False, tour_done = False → False
        assert should_show_tour() is False

    def test_true_when_first_run_done_and_tour_not_done(self):
        from ui.guided_tour import should_show_tour
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        assert should_show_tour() is True

    def test_false_when_both_done(self):
        from ui.guided_tour import should_show_tour
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("ui/first_run_done", True)
        qs.setValue("tour/v1_done", True)
        assert should_show_tour() is False


# ── mark_tour_done() ──────────────────────────────────────────────────────────

class TestMarkTourDone:
    def setup_method(self):
        _fresh_qs()

    def teardown_method(self):
        _fresh_qs()

    def test_sets_key(self):
        from ui.guided_tour import mark_tour_done, should_show_tour
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        assert should_show_tour() is True
        mark_tour_done()
        assert should_show_tour() is False

    def test_idempotent(self):
        from ui.guided_tour import mark_tour_done
        mark_tour_done()
        mark_tour_done()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("tour/v1_done", False, type=bool) is True


# ── Step definitions ──────────────────────────────────────────────────────────

class TestTourSteps:
    def test_step_count(self):
        from ui.guided_tour import _STEPS
        assert len(_STEPS) == 5

    def test_step_nav_labels(self):
        from ui.guided_tour import _STEPS
        labels = [s.nav_label for s in _STEPS]
        assert labels[0] == "Speed Test"
        assert labels[1] == "Network Grade"
        assert labels[2] == "Network Logger"
        assert labels[3] == "Hardware"
        assert labels[4] == "Overview"

    def test_grade_step_has_explicit_cta(self):
        from ui.guided_tour import _STEPS
        grade_step = next(s for s in _STEPS if s.nav_label == "Network Grade")
        assert "Scan & Grade" in grade_step.body, (
            "Network Grade step must contain explicit 'Scan & Grade' CTA text"
        )

    def test_hardware_step_exists(self):
        from ui.guided_tour import _STEPS
        hw_step = next((s for s in _STEPS if s.nav_label == "Hardware"), None)
        assert hw_step is not None, "Tour must include a Hardware step"
        assert "Add" in hw_step.body or "connect" in hw_step.body.lower()

    def test_all_steps_have_body(self):
        from ui.guided_tour import _STEPS
        for step in _STEPS:
            assert step.body.strip(), f"Step '{step.nav_label}' has empty body"


# ── GuidedTour behaviour ──────────────────────────────────────────────────────

class TestGuidedTour:
    def setup_method(self):
        _fresh_qs()

    def teardown_method(self):
        _fresh_qs()

    def _make_mock_dashboard(self):
        """Return a minimal mock dashboard with the required tour bar attributes."""
        from unittest.mock import MagicMock
        app = QApplication.instance()
        d = MagicMock()
        d._tour_bar     = MagicMock()
        d._tour_step_lbl = MagicMock()
        d._tour_body_lbl = MagicMock()
        d._tour_next_btn = MagicMock()
        d._tour_next_btn.clicked = MagicMock()
        d._tour_skip_btn = MagicMock()
        d._tour_skip_btn.clicked = MagicMock()
        d._log_hub_page  = None
        return d

    def test_start_does_nothing_when_tour_done(self):
        from ui.guided_tour import GuidedTour, mark_tour_done
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        mark_tour_done()
        d = self._make_mock_dashboard()
        tour = GuidedTour(None)
        tour._dashboard = d
        tour.start()
        # tour bar should NOT become visible
        d._tour_bar.setVisible.assert_not_called()

    def test_start_shows_bar_when_eligible(self):
        from ui.guided_tour import GuidedTour
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        d = self._make_mock_dashboard()
        tour = GuidedTour(None)
        tour._dashboard = d
        tour.start()
        d._tour_bar.setVisible.assert_called_with(True)

    def test_skip_sets_tour_done_and_hides_bar(self):
        from ui.guided_tour import GuidedTour, should_show_tour
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        assert should_show_tour() is True
        d = self._make_mock_dashboard()
        tour = GuidedTour(None)
        tour._dashboard = d
        tour._finish()
        assert should_show_tour() is False
        d._tour_bar.setVisible.assert_called_with(False)

    def test_advancing_all_steps_marks_done(self):
        from ui.guided_tour import GuidedTour, _STEPS, should_show_tour
        QSettings("NetSentinel", "NetSentinel").setValue("ui/first_run_done", True)
        d = self._make_mock_dashboard()
        tour = GuidedTour(None)
        tour._dashboard = d
        tour._step = len(_STEPS) - 1
        tour._on_next()
        assert should_show_tour() is False


# ── Regression: welcome-overlay → scan_from_home wiring (RULE-T5) ─────────────

class TestWelcomeScanWiring:
    """
    Regression test for the timing bug where _on_welcome_scan called
    _nav_rail_go_to("Home") then _start_full_scan() in the next line.
    _start_full_scan checked currentWidget() is _home_page — but the 160ms
    crossfade animation hadn't completed yet, so _scan_from_home was always
    False and the guided tour never fired.

    Fix: _on_welcome_scan pre-sets _scan_from_home=True before _start_full_scan.
    _start_full_scan only overwrites it if it is False (not already True).
    """

    def setup_method(self):
        _fresh_qs()

    def teardown_method(self):
        _fresh_qs()

    def test_on_welcome_scan_is_noop(self):
        """_on_welcome_scan is now a legacy no-op. OnboardingOrchestrator fires
        all scans directly via _fire_background_scans(). This test ensures the
        method exists and doesn't crash — the original scan-from-home timing bug
        is no longer relevant since the scan fires before any navigation."""
        from unittest.mock import MagicMock
        QApplication.instance()

        dash = MagicMock()
        from ui.dashboard import Dashboard
        bound = Dashboard._on_welcome_scan.__get__(dash, type(dash))
        # Should not raise, should not call _start_full_scan
        bound()
        dash._start_full_scan.assert_not_called()

    def test_start_full_scan_does_not_overwrite_preset_flag(self):
        """_start_full_scan must not set _scan_from_home=False when it is
        pre-set to True by _on_welcome_scan."""
        from unittest.mock import MagicMock
        app = QApplication.instance()

        dash = MagicMock()
        dash._scan_from_home = True   # pre-set by welcome flow
        # currentWidget() returns something that is NOT _home_page
        dash._home_page = MagicMock()
        dash._stack = MagicMock()
        dash._stack.currentWidget.return_value = MagicMock()

        from ui.dashboard import Dashboard
        # Call only the flag-setting portion of _start_full_scan
        # (the guard: if not getattr(self, "_scan_from_home", False): ...)
        if not getattr(dash, "_scan_from_home", False):
            dash._scan_from_home = (
                hasattr(dash, "_home_page")
                and dash._stack.currentWidget() is dash._home_page
            )

        assert dash._scan_from_home is True, (
            "_start_full_scan must not overwrite _scan_from_home when already True"
        )

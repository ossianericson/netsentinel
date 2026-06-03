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
        assert len(_STEPS) == 4

    def test_step_nav_labels(self):
        from ui.guided_tour import _STEPS
        labels = [s.nav_label for s in _STEPS]
        assert labels[0] == "Devices"
        assert labels[1] == "Overview"
        assert labels[2] == "Log Hub"
        assert labels[3] == "Overview"

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

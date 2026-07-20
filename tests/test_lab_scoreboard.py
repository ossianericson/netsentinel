"""Tests for ui/widgets/lab_scoreboard.py (Lab Mode Badge Scoreboard)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.lab_scenarios import SCENARIOS


def _teardown(w) -> None:
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def panel():
    from ui.widgets.lab_scoreboard import LabScoreboardPanel
    p = LabScoreboardPanel(SCENARIOS)
    yield p
    _teardown(p)


def test_import():
    from ui.widgets.lab_scoreboard import LabScoreboardPanel  # noqa: F401


def test_instantiation_builds_one_card_per_scenario(panel):
    assert len(panel._cards) == len(SCENARIOS)
    assert len(panel._medallions) == len(SCENARIOS)


def test_starts_with_all_badges_locked(panel):
    assert all(not m.is_earned() for m in panel._medallions.values())
    assert f"0 of {len(SCENARIOS)} earned" in panel._progress_lbl.text()


def test_scoreboard_marks_earned_scenario(panel):
    """RULE-T7: refresh() must flip exactly the earned scenario's medallion and
    update the overall progress label."""
    panel.refresh({"rogue_device": {"completed_at": "2026-07-19 10:00:00",
                                     "verdict": "PASS", "best_verdict": "PASS",
                                     "attempts": 1}})
    assert panel._medallions["rogue_device"].is_earned()
    assert not panel._medallions["slow_dns"].is_earned()
    assert f"1 of {len(SCENARIOS)}" in panel._progress_lbl.text()


def test_status_label_shows_earned_date(panel):
    panel.refresh({"rogue_device": {"completed_at": "2026-07-19 10:00:00",
                                     "verdict": "PASS", "best_verdict": "PASS",
                                     "attempts": 1}})
    assert panel._status_lbls["rogue_device"].text() == "Earned 2026-07-19"
    assert panel._status_lbls["slow_dns"].text() == "Locked"


def test_coverage_rows_have_nonzero_denominators(panel):
    assert panel._coverage_bars, "expected at least one coverage row"
    for cert, bar in panel._coverage_bars.items():
        assert bar.maximum() > 0, cert


def test_back_requested_emits(panel):
    received = []
    panel.back_requested.connect(lambda: received.append(True))
    from PyQt6.QtWidgets import QPushButton
    back_btn = next(
        b for b in panel.findChildren(QPushButton) if b.text() == "← Back to Exercises"
    )
    back_btn.click()
    assert received == [True]


def test_start_requested_emits_scenario_from_locked_card(panel):
    received = []
    panel.start_requested.connect(lambda s: received.append(s))
    scenario = SCENARIOS[0]
    panel._start_btns[scenario.id].click()
    assert received == [scenario]


def test_earned_card_hides_start_button(panel):
    scenario = SCENARIOS[0]
    panel.refresh({scenario.id: {"completed_at": "2026-07-19 10:00:00",
                                  "verdict": "PASS", "best_verdict": "PASS",
                                  "attempts": 1}})
    assert not panel._start_btns[scenario.id].isVisible()

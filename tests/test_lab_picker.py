"""Tests for ui/widgets/lab_picker.py (Lab Mode Upgrade Phase L2)."""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.lab_scenarios import SCENARIOS


@pytest.fixture
def picker():
    from ui.widgets.lab_picker import LabPickerPanel
    p = LabPickerPanel(SCENARIOS)
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_import():
    from ui.widgets.lab_picker import LabPickerPanel  # noqa: F401


def test_instantiation_builds_one_card_per_scenario(picker):
    assert len(picker._cards) == len(SCENARIOS)
    assert len(picker._badges) == len(SCENARIOS)


def test_progress_strip_starts_at_zero(picker):
    assert picker._progress_strip.text() == f"0 of {len(SCENARIOS)} complete"


def test_refresh_progress_updates_strip_and_badge():
    from ui.widgets.lab_picker import LabPickerPanel
    from modules.lab_progress import mark_complete
    p = LabPickerPanel(SCENARIOS)
    p.show()
    scenario_id = SCENARIOS[0].id
    state = mark_complete({}, scenario_id, {"verdict": "PASS", "completed_at": "2026-07-18 10:00:00"})
    p.refresh_progress(state)
    assert p._progress_strip.text() == f"1 of {len(SCENARIOS)} complete"
    assert p._badges[scenario_id].isVisible()
    assert "2026-07-18" in p._badges[scenario_id].text()
    for other in SCENARIOS[1:]:
        assert not p._badges[other.id].isVisible()
    p.deleteLater()


def test_start_requested_emits_with_scenario(picker):
    received = []
    picker.start_requested.connect(lambda s: received.append(s))
    scenario = SCENARIOS[0]
    picker.start_requested.emit(scenario)
    assert received == [scenario]


def test_explore_protocol_requested_emits_key(picker):
    received = []
    picker.explore_protocol_requested.connect(received.append)
    picker.explore_protocol_requested.emit("ARP")
    assert received == ["ARP"]

"""Tests for data/curriculum_map.json and ui/widgets/objective_badge.py (B3)."""

import json
import pytest
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


# ── JSON structure ─────────────────────────────────────────────────────────────

_MAP_PATH = Path(__file__).parent.parent / "data" / "curriculum_map.json"


def test_curriculum_map_exists():
    assert _MAP_PATH.exists(), "data/curriculum_map.json not found"


def test_curriculum_map_valid_json():
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_curriculum_map_top_level_keys():
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    assert "lab_scenarios" in data
    assert "protocol_viz" in data
    assert "pages" in data


def test_curriculum_map_lab_scenarios_structure():
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    scenarios = data["lab_scenarios"]
    assert len(scenarios) >= 4
    for name, entry in scenarios.items():
        assert "certifications" in entry, f"Missing certifications in {name}"
        assert "objectives" in entry, f"Missing objectives in {name}"
        assert isinstance(entry["certifications"], list)
        assert isinstance(entry["objectives"], list)
        assert len(entry["objectives"]) >= 1


def test_curriculum_map_protocol_viz_structure():
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    protocols = data["protocol_viz"]
    for proto in ("ARP", "DNS", "TCP", "DHCP", "STP"):
        assert proto in protocols, f"Protocol {proto} missing from curriculum_map"
        entry = protocols[proto]
        assert "certifications" in entry
        assert "objectives" in entry


def test_curriculum_map_no_empty_objectives():
    data = json.loads(_MAP_PATH.read_text(encoding="utf-8"))
    for category, entries in data.items():
        if category.startswith("_"):
            continue
        for name, entry in entries.items():
            if isinstance(entry, dict) and "objectives" in entry:
                assert entry["objectives"], f"Empty objectives list in {category}/{name}"


# ── ObjectiveBadge — data helpers (no Qt required) ────────────────────────────

def test_objective_badge_import():
    from ui.widgets.objective_badge import ObjectiveBadge  # noqa: F401


def test_objective_badge_load_map():
    from ui.widgets.objective_badge import _load_map, _get_entry
    m = _load_map()
    assert "lab_scenarios" in m
    entry = _get_entry("protocol_viz", "ARP")
    assert "certifications" in entry


# ── ObjectiveBadge — widget tests (Qt required) ───────────────────────────────

@pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")
def test_objective_badge_for_protocol_returns_list():
    from ui.widgets.objective_badge import ObjectiveBadge
    app = QApplication.instance()
    badges = ObjectiveBadge.for_protocol("ARP")
    assert isinstance(badges, list)
    assert len(badges) >= 1
    for b in badges:
        try:
            b.deleteLater()
        except RuntimeError:
            pass
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")
def test_objective_badge_for_scenario_rogue():
    from ui.widgets.objective_badge import ObjectiveBadge
    app = QApplication.instance()
    badges = ObjectiveBadge.for_scenario("Find a Rogue Device")
    assert isinstance(badges, list)
    assert len(badges) >= 1
    for b in badges:
        try:
            b.deleteLater()
        except RuntimeError:
            pass
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")
def test_objective_badge_for_unknown_returns_empty():
    from ui.widgets.objective_badge import ObjectiveBadge
    badges = ObjectiveBadge.for_scenario("Totally Unknown Scenario XYZ")
    assert badges == []


@pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")
def test_objective_badge_cert_labels():
    from ui.widgets.objective_badge import ObjectiveBadge
    app = QApplication.instance()
    badges = ObjectiveBadge.for_protocol("TCP")
    labels = [b.text() for b in badges]
    assert any(lbl in ("N+", "CCNA", "Sec+") for lbl in labels)
    for b in badges:
        try:
            b.deleteLater()
        except RuntimeError:
            pass
    if app:
        for _ in range(3):
            app.processEvents()

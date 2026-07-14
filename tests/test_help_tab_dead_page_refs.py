"""
Regression test for F-20 (claims-audit): ui/help_tab.py's walkthrough and feature list
referenced two pages ("Health Check", "My Network Info") that are built but only
registered via the dead legacy _nav_add_page() path (RULE-NAV2) -- unreachable from
the rail/flyout/command palette. Per product decision, these widgets stay retired
(superseded by the "What's Wrong?" diagnosis flow); the docs are corrected to stop
pointing users at pages they can't open.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent
HELP_TAB_SRC = (ROOT / "ui" / "help_tab.py").read_text(encoding="utf-8")


def test_my_network_info_not_referenced():
    assert "My Network Info" not in HELP_TAB_SRC


def test_health_check_not_referenced_as_a_page():
    assert "Health Check" not in HELP_TAB_SRC


def test_whats_wrong_referenced_as_the_diagnosis_flow():
    assert "What's Wrong?" in HELP_TAB_SRC

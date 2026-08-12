"""
Sprint 5 integration tests.

Covers:
  - DiagnosisPage: 'service_unreachable' symptom tile exists and drives ServiceDiagnosticsWorker
  - ServicePage:   diagnose_service signal exists; _find_service_id() lookup
  - ServiceDiagnosticsPage: set_service() pre-selects the correct combo item
"""
from __future__ import annotations

import pytest


# ── Category-vocabulary coverage ──────────────────────────────────────────────
#
# These maps are keyed by CorrelatedFinding.category, and the correlator is the
# only thing that produces one. A key with no producer is dead weight that reads
# like a live feature: v2.2.6 removed "Service Outage" / "External Routing Issue"
# entries that only the (also-removed, never-wired) _svc_result_to_diag() helper
# could ever have emitted, and the tests here asserted their presence -- green
# the whole time, certifying data nothing could reach. Assert the relationship
# instead of the literals, so neither side can drift again.

def _correlator_categories() -> set:
    """Every category literal root_cause_correlator.py can emit."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "modules" / "root_cause_correlator.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "category":
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.add(node.value.value)
    return found


def test_correlator_categories_are_discoverable():
    """Guard the guard — if this returns nothing the two tests below are vacuous."""
    assert len(_correlator_categories()) >= 5


def test_every_cta_map_key_has_a_producer():
    from ui.pages.diagnosis_page import _CTA_MAP

    orphans = sorted(set(_CTA_MAP) - _correlator_categories())
    assert not orphans, (
        "_CTA_MAP keys that no correlator finding can ever produce: "
        f"{orphans}. Remove them, or wire up whatever should emit them."
    )


def test_every_remediation_key_has_a_producer():
    from ui.pages.diagnosis_page import _REMEDIATION

    orphans = sorted(set(_REMEDIATION) - _correlator_categories())
    assert not orphans, (
        "_REMEDIATION keys that no correlator finding can ever produce: "
        f"{orphans}. Remove them, or wire up whatever should emit them."
    )


# ── ServicePage._find_service_id ──────────────────────────────────────────────

def test_find_service_id_known_host():
    from ui.pages.service_page import ServicePage
    # Netflix uses www.netflix.com as a probe host
    sid = ServicePage._find_service_id("www.netflix.com")
    assert sid == "netflix"


def test_find_service_id_unknown_host():
    from ui.pages.service_page import ServicePage
    sid = ServicePage._find_service_id("192.168.1.1")
    assert sid == ""


def test_find_service_id_empty():
    from ui.pages.service_page import ServicePage
    assert ServicePage._find_service_id("") == ""


def test_find_service_id_steam():
    from ui.pages.service_page import ServicePage
    sid = ServicePage._find_service_id("store.steampowered.com")
    assert sid == "steam"


# ── Qt widget tests ───────────────────────────────────────────────────────────

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark_qt = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


@pytest.fixture
def _diagnosis_page():
    if not _HAS_QT:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance()
    from ui.pages.diagnosis_page import DiagnosisPage
    page = DiagnosisPage()
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already deleted
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def _service_page():
    if not _HAS_QT:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance()
    from ui.pages.service_page import ServicePage
    page = ServicePage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already deleted
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def _svc_diag_page():
    if not _HAS_QT:
        pytest.skip("PyQt6 not available")
    app = QApplication.instance()
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
    page = ServiceDiagnosticsPage(store=None)
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already deleted
    if app:
        for _ in range(3):
            app.processEvents()


@pytestmark_qt
def test_diagnosis_page_has_four_symptom_tiles(_diagnosis_page):
    """The idle state must have the expected checkable symptom buttons."""
    page = _diagnosis_page
    group = page._symptom_group
    buttons = group.buttons()
    keys = [b.property("symptom_key") for b in buttons]
    assert "service_unreachable" in keys, f"service_unreachable not found in {keys}"
    assert "other" in keys, f"'other' symptom tile not found in {keys}"
    assert len(keys) == 5


@pytestmark_qt
def test_diagnosis_page_service_pick_row_hidden_by_default(_diagnosis_page):
    page = _diagnosis_page
    assert page._service_pick_row.isHidden()


@pytestmark_qt
def test_diagnosis_page_service_pick_row_shows_on_tile_click(_diagnosis_page):
    page = _diagnosis_page
    group = page._symptom_group
    target = None
    for btn in group.buttons():
        if btn.property("symptom_key") == "service_unreachable":
            target = btn
            break
    assert target is not None, "service_unreachable tile button not found"
    # Simulate the group buttonClicked signal by calling the connected slot directly
    group.buttonClicked.emit(target)
    # isVisible() requires parent chain to be shown; isHidden() checks only this widget
    assert not page._service_pick_row.isHidden()


@pytestmark_qt
def test_diagnosis_page_symptom_service_combo_populated(_diagnosis_page):
    """The service picker combo must list at least one streaming and one gaming entry."""
    page = _diagnosis_page
    combo = page._symptom_service_combo
    streaming = any("Streaming" in combo.itemText(i) for i in range(combo.count()))
    gaming = any("Gaming" in combo.itemText(i) for i in range(combo.count()))
    assert streaming and gaming


@pytestmark_qt
def test_service_page_diagnose_service_signal_exists(_service_page):
    page = _service_page
    assert hasattr(page, "diagnose_service")
    # Verify the signal can be connected to a slot
    received = []
    page.diagnose_service.connect(received.append)
    page.diagnose_service.emit("netflix")
    assert received == ["netflix"]


@pytestmark_qt
def test_service_diagnostics_page_set_service(_svc_diag_page):
    page = _svc_diag_page
    page.set_service("steam")
    # The combo should now have "steam" as current data
    idx = page._service_combo.currentIndex()
    assert page._service_combo.itemData(idx) == "steam"


@pytestmark_qt
def test_service_diagnostics_page_set_service_unknown_id_no_crash(_svc_diag_page):
    page = _svc_diag_page
    original_idx = page._service_combo.currentIndex()
    page.set_service("nonexistent_service_id_xyz")
    # Should not change selection when ID not found
    assert page._service_combo.currentIndex() == original_idx

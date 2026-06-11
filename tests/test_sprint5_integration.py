"""
Sprint 5 integration tests.

Covers:
  - DiagnosisPage: 'service_unreachable' symptom tile exists and drives ServiceDiagnosticsWorker
  - DiagnosisPage: _svc_result_to_diag() translation (all failure layers)
  - ServicePage:   diagnose_service signal exists; _find_service_id() lookup
  - ServiceDiagnosticsPage: set_service() pre-selects the correct combo item
"""
from __future__ import annotations

import pytest


# ── _svc_result_to_diag helper (pure logic, no Qt) ────────────────────────────

def _make_svc_result(layer: str, name: str = "TestSvc", summary: str = "Summary text"):
    """Build a minimal duck-typed ServiceDiagnosticResult for translation tests."""
    from types import SimpleNamespace
    return SimpleNamespace(failure_layer=layer, service_name=name, summary=summary)


def test_svc_result_to_diag_none_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("none", name="Netflix", summary="Netflix is reachable.")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "INFO"
    assert len(synth.findings) == 0
    assert "Netflix is reachable" in synth.plain_summary


def test_svc_result_to_diag_dns_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("dns", name="Steam")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "HIGH"
    assert len(synth.findings) == 1
    assert synth.findings[0].category == "DNS Resolution Failure"
    assert synth.findings[0].severity == "HIGH"
    assert "Steam" in synth.findings[0].headline


def test_svc_result_to_diag_local_network_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("local_network", name="PSN")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "HIGH"
    assert synth.findings[0].category == "Local Network / Router Unreachable"


def test_svc_result_to_diag_isp_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("isp", name="YouTube")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "MEDIUM"
    assert synth.findings[0].category == "External ISP Issue"


def test_svc_result_to_diag_routing_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("routing", name="Xbox Live")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "MEDIUM"
    assert synth.findings[0].category == "External Routing Issue"
    assert len(synth.findings) == 1


def test_svc_result_to_diag_remote_outage_layer():
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("remote_outage", name="Twitch")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "MEDIUM"
    assert synth.findings[0].category == "Service Outage"


def test_svc_result_to_diag_unknown_layer_treated_as_none():
    """Unknown failure layers should produce no findings (safe fallback)."""
    from ui.pages.diagnosis_page import _svc_result_to_diag
    result = _make_svc_result("unknown_future_layer")
    synth = _svc_result_to_diag(result)
    assert synth.global_severity == "INFO"
    assert len(synth.findings) == 0


# ── _CTA_MAP coverage for new categories ─────────────────────────────────────

def test_cta_map_has_service_outage():
    from ui.pages.diagnosis_page import _CTA_MAP
    assert "Service Outage" in _CTA_MAP
    label, target = _CTA_MAP["Service Outage"]
    assert target == "Service Diagnostics"


def test_cta_map_has_external_routing():
    from ui.pages.diagnosis_page import _CTA_MAP
    assert "External Routing Issue" in _CTA_MAP
    label, target = _CTA_MAP["External Routing Issue"]
    assert target == "Service Diagnostics"


def test_remediation_has_service_outage_steps():
    from ui.pages.diagnosis_page import _REMEDIATION
    assert "Service Outage" in _REMEDIATION
    assert len(_REMEDIATION["Service Outage"]) >= 3


def test_remediation_has_external_routing_steps():
    from ui.pages.diagnosis_page import _REMEDIATION
    assert "External Routing Issue" in _REMEDIATION
    assert len(_REMEDIATION["External Routing Issue"]) >= 3


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
    """The idle state must have exactly 4 checkable symptom buttons."""
    page = _diagnosis_page
    group = page._symptom_group
    buttons = group.buttons()
    keys = [b.property("symptom_key") for b in buttons]
    assert "service_unreachable" in keys, f"service_unreachable not found in {keys}"
    assert len(keys) == 4


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

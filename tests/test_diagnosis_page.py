"""Tests for DiagnosisPage and DiagnosisWorker (Sprint H5)."""

from __future__ import annotations

from dataclasses import dataclass
import pytest

try:
    from PyQt6.QtWidgets import QApplication, QPushButton, QLabel
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# DiagnosisWorker — focused_on parameter
# ---------------------------------------------------------------------------

def test_diagnosis_worker_import():
    from workers.diagnosis_worker import DiagnosisWorker
    assert DiagnosisWorker is not None


def test_diagnosis_worker_focused_on_accepted():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker(focused_on="DNS Resolution Failure")
    assert w._focused_on == "DNS Resolution Failure"
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


def test_diagnosis_worker_focused_on_none_by_default():
    from workers.diagnosis_worker import DiagnosisWorker
    w = DiagnosisWorker()
    assert w._focused_on is None
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


def test_diagnosis_worker_focused_step_categories():
    from workers.diagnosis_worker import (
        _DIAG_STEP_CATEGORIES,
        _STORM_STEP_CATEGORIES,
        _STP_STEP_CATEGORIES,
    )
    assert "DNS Resolution Failure" in _DIAG_STEP_CATEGORIES
    assert "Broadcast Storm" in _STORM_STEP_CATEGORIES
    assert "Rogue Network Bridge" in _STP_STEP_CATEGORIES


# ---------------------------------------------------------------------------
# DiagnosisPage — verify_step rendering
# ---------------------------------------------------------------------------

@dataclass
class _MockFinding:
    severity: str = "HIGH"
    headline: str = "Test Finding"
    remediation: str = "Restart your router."
    category: str = "Local Network / Router Unreachable"
    detail: str = ""
    verify_step: str = "After restarting, run What is Wrong again to confirm."


@pytest.fixture
def diag_page(qt_app):
    from ui.pages.diagnosis_page import DiagnosisPage
    page = DiagnosisPage()
    yield page
    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already destroyed — safe to skip
    app = QApplication.instance()
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()


def test_diagnosis_page_imports():
    from ui.pages.diagnosis_page import DiagnosisPage
    assert DiagnosisPage is not None


def test_make_finding_card_with_verify_step(diag_page):
    finding = _MockFinding()
    card = diag_page._make_finding_card(finding, hero=False)
    btn_texts = [w.text() for w in card.findChildren(QPushButton)]
    assert any("Verify" in t for t in btn_texts), (
        f"Expected a Verify button; found: {btn_texts}"
    )


def test_make_finding_card_verify_step_text_shown(diag_page):
    finding = _MockFinding(verify_step="After fixing: check the log.")
    card = diag_page._make_finding_card(finding, hero=False)
    label_texts = [w.text() for w in card.findChildren(QLabel)]
    assert any("After fixing" in t for t in label_texts), (
        f"Expected verify_step text; found: {label_texts}"
    )


def test_make_finding_card_no_verify_step_no_button(diag_page):
    finding = _MockFinding(verify_step="")
    card = diag_page._make_finding_card(finding, hero=False)
    btn_texts = [w.text() for w in card.findChildren(QPushButton)]
    assert not any("Verify" in t for t in btn_texts), (
        f"Unexpected Verify button when verify_step empty; found: {btn_texts}"
    )


def test_verify_workers_list_initialised(diag_page):
    assert hasattr(diag_page, "_verify_workers")
    assert diag_page._verify_workers == []

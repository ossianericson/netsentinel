"""
Tests for workers/service_diagnostics_worker.py (Sprint 4).

RULE-T2: worker start/stop lifecycle test.
"""
from __future__ import annotations

# ── Import guard ──────────────────────────────────────────────────────────────

def test_import_worker():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    assert ServiceDiagnosticsWorker is not None


def test_worker_attributes():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    w = ServiceDiagnosticsWorker(service_id="netflix")
    assert w._service_id == "netflix"
    assert w._traceroute is False
    w.deleteLater()


def test_worker_set_service():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    w = ServiceDiagnosticsWorker()
    w.set_service("steam", traceroute=True)
    assert w._service_id == "steam"
    assert w._traceroute is True
    w.deleteLater()


def test_worker_signals_exist():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    w = ServiceDiagnosticsWorker(service_id="netflix")
    assert hasattr(w, "result_ready")
    assert hasattr(w, "error")
    assert hasattr(w, "progress")
    w.deleteLater()


def test_worker_stop_flag():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    w = ServiceDiagnosticsWorker(service_id="netflix")
    assert w._stop_requested is False
    w.stop()
    assert w._stop_requested is True
    w.deleteLater()


def test_worker_no_service_emits_error(qt_app):
    """Worker with no service_id emits error immediately and doesn't crash."""
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker

    errors = []
    w = ServiceDiagnosticsWorker(service_id=None)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(3000)
    qt_app.processEvents()
    assert finished, "Worker did not finish within 3 s"
    assert not w.isRunning()
    assert len(errors) == 1
    assert "No service" in errors[0]
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


# ── Lifecycle test (mocked network) ──────────────────────────────────────────

def test_worker_lifecycle_with_mock(qt_app, monkeypatch):
    """Worker start → result_ready → stop without touching the network."""
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    from modules.service_diagnostics import ServiceDiagnosticResult

    fake_result = ServiceDiagnosticResult(
        service_id="netflix",
        service_name="Netflix",
        failure_layer="none",
        summary="All good.",
        confidence=90,
    )

    def _mock_run(self_engine, service_id, *, traceroute=False):
        return fake_result

    monkeypatch.setattr(
        "modules.service_diagnostics.DiagnosticEngine.run", _mock_run
    )

    results = []
    errors = []

    w = ServiceDiagnosticsWorker(service_id="netflix")
    w.result_ready.connect(results.append)
    w.error.connect(errors.append)
    w.start()
    finished = w.wait(5000)
    qt_app.processEvents()

    assert finished, "Worker did not finish within 5 s"
    assert not w.isRunning()
    assert len(errors) == 0, f"Unexpected error: {errors}"
    assert len(results) == 1
    assert results[0].service_id == "netflix"
    assert results[0].failure_layer == "none"

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


# ── Page import test ──────────────────────────────────────────────────────────

def test_import_page():
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
    assert ServiceDiagnosticsPage is not None


def test_page_instantiation(qt_app):
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage

    page = ServiceDiagnosticsPage(store=None)
    assert page is not None
    assert hasattr(page, "_service_combo")
    assert hasattr(page, "_run_btn")
    assert hasattr(page, "_stack")
    # Initial state: empty state shown
    assert page._stack.currentIndex() == 0

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


def test_page_service_picker_populated(qt_app):
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
    from modules.service_diagnostics import SERVICE_CATALOG

    page = ServiceDiagnosticsPage(store=None)
    count = page._service_combo.count()
    assert count == len(SERVICE_CATALOG), (
        f"Expected {len(SERVICE_CATALOG)} services in picker, got {count}"
    )

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()

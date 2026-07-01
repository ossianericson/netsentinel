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


def test_worker_custom_host_attribute():
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    w = ServiceDiagnosticsWorker(custom_host="github.com")
    assert w._custom_host == "github.com"
    assert w._service_id is None
    w.deleteLater()


def test_worker_custom_host_uses_run_custom(qt_app, monkeypatch):
    """Worker with custom_host must call DiagnosticEngine.run_custom(), not run()."""
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker
    from modules.service_diagnostics import ServiceDiagnosticResult

    fake_result = ServiceDiagnosticResult(
        service_id="custom:github.com",
        service_name="github.com",
        failure_layer="filtered",
        summary="Filtered.",
        confidence=75,
    )
    calls = []

    def _mock_run_custom(self_engine, host, *, port=443, traceroute=False):
        calls.append(host)
        return fake_result

    monkeypatch.setattr(
        "modules.service_diagnostics.DiagnosticEngine.run_custom", _mock_run_custom
    )

    results = []
    w = ServiceDiagnosticsWorker(custom_host="github.com")
    w.result_ready.connect(results.append)
    w.start()
    finished = w.wait(5000)
    qt_app.processEvents()

    assert finished, "Worker did not finish within 5 s"
    assert calls == ["github.com"]
    assert len(results) == 1
    assert results[0].service_name == "github.com"

    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


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
    # +1 for the "Custom host..." entry (data=None) that lets users probe an
    # arbitrary hostname (e.g. github.com) not in the catalog.
    assert count == len(SERVICE_CATALOG) + 1, (
        f"Expected {len(SERVICE_CATALOG) + 1} picker entries, got {count}"
    )

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


def test_page_custom_host_field_toggles_with_selection(qt_app):
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage

    page = ServiceDiagnosticsPage(store=None)
    page.show()
    custom_idx = next(
        i for i in range(page._service_combo.count())
        if page._service_combo.itemData(i) is None
    )
    page._service_combo.setCurrentIndex(custom_idx)
    assert page._custom_host_edit.isVisible()

    page._service_combo.setCurrentIndex(0 if custom_idx != 0 else 1)
    assert not page._custom_host_edit.isVisible()

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()


def test_page_run_with_custom_host_starts_worker(qt_app, monkeypatch):
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
    from workers.service_diagnostics_worker import ServiceDiagnosticsWorker

    started = {}

    def _fake_start(self):
        started["custom_host"] = self._custom_host
        started["service_id"] = self._service_id

    monkeypatch.setattr(ServiceDiagnosticsWorker, "start", _fake_start)

    page = ServiceDiagnosticsPage(store=None)
    custom_idx = next(
        i for i in range(page._service_combo.count())
        if page._service_combo.itemData(i) is None
    )
    page._service_combo.setCurrentIndex(custom_idx)
    page._custom_host_edit.setText("github.com")
    page._on_run_clicked()

    assert started.get("custom_host") == "github.com"
    assert started.get("service_id") is None

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # already cleaned up
    qt_app.processEvents()

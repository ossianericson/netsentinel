"""S1 "Stop the lies" — a failed run must never leave a page reporting success.

Behavioural counterparts to the static ratchets in
``tests/test_error_surfacing_ratchet.py``. Each test here pins one finding from
``docs/internal/error-surfacing-audit-2026-09-15.md`` that the S0 verification
matrix reproduced live:

  * F1c-SVC — ``ServiceDiagnosticsPage._on_error`` emitted ``scan_complete``,
    which the dashboard maps to ``"fresh"``: a failed diagnosis turned the
    flyout dot green.
  * F1c-SPD — ``SpeedTestPage._on_test_error`` returned before recording
    anything while the page was hidden, so the registry kept the last success
    and no history row was written.
  * F1c-DNS / F1c-CVE — the DNS Zone Map and CVE Tracker pages had no failure
    signal at all, so a failed scan kept the previous verdict on screen.

These assert on the page's *contract* (which signal fires), not on the dot
colour, so they do not need a full Dashboard (RULE-TP4-DASH). The label→state
mapping itself is covered by
``test_error_surfacing_ratchet.py::test_no_new_scan_labels_without_error_path``.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from modules.service_diagnostics import ServiceDiagnosticResult  # noqa: E402
from ui.pages.cve_page import CvePage  # noqa: E402
from ui.pages.dns_zone_page import DnsZonePage  # noqa: E402
from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage  # noqa: E402
from ui.pages.speed_test_page import SpeedTestPage  # noqa: E402

_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_pages(qt_app):
    """RULE-WIN4: deleteLater() + pump, never plain refcount GC.

    Without the pump these pages' C++ objects are destroyed synchronously when
    the last Python reference drops, which corrupts the Qt event loop on
    Windows and kills the pytest process with STATUS_STACK_BUFFER_OVERRUN.
    """
    yield
    from PyQt6.QtCore import QCoreApplication, QEvent
    from PyQt6.QtWidgets import QApplication

    for page in _pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed — nothing left to schedule
    _pages.clear()
    app = QApplication.instance()
    if app:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        for _ in range(3):
            app.processEvents()


def _page(widget):
    """Register a page for RULE-WIN4 teardown and return it."""
    _pages.append(widget)
    return widget


@pytest.fixture
def speed_page(monkeypatch):
    """SpeedTestPage built the way tests/test_speed_test_page.py builds it.

    ``showEvent()`` spawns a real ``FetchServersWorker`` QThread that outlives
    teardown (RULE-WIN6); left unpatched it takes the pytest process down with
    STATUS_STACK_BUFFER_OVERRUN rather than failing a test.
    """
    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    return _page(SpeedTestPage(store=MagicMock()))


def _record(signal) -> list:
    """Collect every emission of ``signal`` into a list."""
    seen: list = []
    signal.connect(lambda *args: seen.append(args))
    return seen


# ── F1c-SVC — Service Diagnostics ────────────────────────────────────────────

def test_service_diagnostics_error_does_not_emit_scan_complete():
    """A failed diagnosis must not travel the success signal.

    ``scan_complete`` is mapped to ``"fresh"`` by the dashboard, so emitting it
    from ``_on_error`` turned the Service Diagnostics dot green on failure.
    """
    page = _page(ServiceDiagnosticsPage(store=None, parent=None))
    completed = _record(page.scan_complete)
    failed = _record(page.scan_failed)

    page._on_error("DNS resolution failed for example.com")

    assert completed == [], "a failed diagnosis still emitted scan_complete"
    assert failed == [("DNS resolution failed for example.com",)]


def test_service_diagnostics_success_still_emits_scan_complete():
    """The success path must keep working — this is the state the fix protects."""
    page = _page(ServiceDiagnosticsPage(store=None, parent=None))
    failed = _record(page.scan_failed)
    completed = _record(page.scan_complete)

    page._on_result(ServiceDiagnosticResult(service_id="dns", service_name="DNS"))

    assert completed == [()]
    assert failed == []


# ── F1c-SPD — Speed Test ─────────────────────────────────────────────────────

def test_speed_test_error_is_recorded_while_page_is_hidden(speed_page):
    """A scheduled/background speed test fails while the page is not on screen.

    The page returned early on ``not isVisible()``, so nothing reached the
    registry or the history table and the last success stayed on the dot.
    """
    page = speed_page
    assert not page.isVisible(), "precondition: the page must be hidden"
    failed = _record(page.test_failed)

    page._on_test_error("No servers could be reached")

    assert failed == [("No servers could be reached",)], (
        "a speed test that failed off-screen reported nothing"
    )


def test_speed_test_error_writes_a_history_row_while_hidden(speed_page):
    """The failure is also shown in the page's own history, not just signalled."""
    before = speed_page._hist_table.rowCount()
    speed_page._on_test_error("Connection reset by peer")
    assert speed_page._hist_table.rowCount() == before + 1


# ── F1c-DNS / F1c-CVE — pages with no failure signal at all ──────────────────

def test_dns_zone_error_emits_scan_failed():
    page = _page(DnsZonePage(parent=None))
    completed = _record(page.scan_complete)
    failed = _record(page.scan_failed)

    page._on_error("AXFR refused by 192.0.2.1")

    assert completed == [], "a failed zone transfer still emitted scan_complete"
    assert failed == [("AXFR refused by 192.0.2.1",)]


def test_cve_refresh_failure_emits_refresh_failed():
    """A locked/corrupt SQLite file must not leave the last count on the dot."""
    store = MagicMock()
    store.list_cve_lifecycles.return_value = []
    page = _page(CvePage(store, parent=None))
    refreshed = _record(page.data_refreshed)
    failed = _record(page.refresh_failed)

    store.list_cve_lifecycles.side_effect = RuntimeError("database is locked")
    page._refresh()

    assert refreshed == [], "a failed refresh still reported a fresh CVE count"
    assert len(failed) == 1 and "database is locked" in failed[0][0]

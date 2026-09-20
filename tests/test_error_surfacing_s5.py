"""S5 — worker errors reach the user as what/why/next, never as the raw worker string (RULE-A2).

Behavioural counterparts (RULE-T7) to ratchet (a) in ``tests/test_error_surfacing_ratchet.py``,
which only sees how a raw value is bound. These drive the real error slots — the five pages
that already carried what + next, the SNMP trap page, one error-signal lambda through its real
start method — and the SMB Stop path, where a user's Stop used to arrive as an error.

Every raw sample is non-English OS text: the message must not depend on it, and the raw text
must still reach the app log (D4) so it is not lost.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

RAW = ("[WinError 10048] Endast en användning av varje socketadress "
       "(protokoll/nätverksadress/port) är normalt tillåten")

_widgets: list = []


@pytest.fixture(autouse=True)
def _cleanup(qt_app):
    """RULE-WIN4: deleteLater() + pump, never plain refcount GC."""
    yield
    for w in _widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed
    _widgets.clear()
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _keep(widget):
    _widgets.append(widget)
    return widget


def _worker_error_records(caplog, key: str) -> list:
    return [r for r in caplog.records if r.name == f"netsentinel.worker_error.{key}"]


def _assert_translated(label: QLabel, spec, caplog) -> None:
    from ui.error_display import worker_error_text

    assert label.text() == worker_error_text(spec)
    assert "10048" not in label.text() and "socketadress" not in label.text()
    records = _worker_error_records(caplog, spec.key)
    assert len(records) == 1 and RAW in records[0].getMessage(), "the raw text was lost"


# ── The listener pages: the strip's own wording (S4.4b seeds these) ──────────────

def test_syslog_page_error_uses_the_condition_text(caplog):
    from modules.app_health_catalogue import SYSLOG_RECEIVER
    from ui.pages.syslog_page import SyslogPage

    page = _keep(SyslogPage())
    with caplog.at_level(logging.WARNING):
        page.on_error(RAW)

    _assert_translated(page._status_lbl, SYSLOG_RECEIVER, caplog)
    assert page._status_lbl.wordWrap(), "the condition text is too long for a non-wrapping row"


def test_snmp_trap_page_error_uses_the_condition_text(caplog):
    from modules.app_health_catalogue import SNMP_TRAP_RECEIVER
    from ui.pages.snmp_trap_page import SnmpTrapPage

    page = _keep(SnmpTrapPage())
    with caplog.at_level(logging.WARNING):
        page.on_error(RAW)

    _assert_translated(page._status_lbl, SNMP_TRAP_RECEIVER, caplog)
    assert page._status_lbl.wordWrap()


# ── The three pages that already said what + next ───────────────────────────────

def test_dhcp_lease_page_error_is_translated(caplog):
    from ui import worker_error_catalogue as WE
    from ui.pages.dhcp_lease_page import DhcpLeasePage

    class _NoScan(DhcpLeasePage):
        def _run_scan(self) -> None:
            pass  # no DhcpLeaseWorker QThread — the error slot is what is under test

    page = _keep(_NoScan())
    with caplog.at_level(logging.WARNING):
        page._on_error(RAW)

    _assert_translated(page._status_lbl, WE.DHCP_LEASES, caplog)


def test_dns_zone_page_error_is_translated_and_still_reports_failure(caplog):
    from ui import worker_error_catalogue as WE
    from ui.pages.dns_zone_page import DnsZonePage

    page = _keep(DnsZonePage(parent=None))
    failed: list = []
    page.scan_failed.connect(failed.append)
    with caplog.at_level(logging.WARNING):
        page._on_error(RAW)

    _assert_translated(page._status_lbl, WE.DNS_ZONE, caplog)
    assert failed == [RAW], "S1.2's registry signal must keep the raw detail"


def test_geolite_download_error_is_translated(caplog, tmp_path):
    from modules.metric_store import MetricStore
    from ui import worker_error_catalogue as WE
    from ui.pages.geo_map_page import GeoMapPage

    store = MetricStore(db_path=tmp_path / "test.db")
    try:
        page = _keep(GeoMapPage(store=store))
        with caplog.at_level(logging.WARNING):
            page._on_dl_error(RAW)
        _assert_translated(page._dl_status, WE.GEOLITE_DOWNLOAD, caplog)
    finally:
        store.close()


# ── One error-signal lambda, driven through its real start method ────────────────

class _FakeSignal:
    def __init__(self):
        self._slots: list = []

    def connect(self, slot, *_conn_type):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


class _FakeSnapshotWorker:
    last = None

    def __init__(self, include_listen=False, parent=None):
        self.snapshot_ready = _FakeSignal()
        self.error = _FakeSignal()
        _FakeSnapshotWorker.last = self

    def start(self):
        pass  # test double — no QThread

    def isRunning(self):  # noqa: N802 - Qt's name
        return False


def test_connections_refresh_error_lambda_is_translated(caplog, monkeypatch):
    from ui import worker_error_catalogue as WE
    from ui.pages.connections_page import ConnectionsPage
    from workers import process_worker

    monkeypatch.setattr(process_worker, "ConnectionSnapshotWorker", _FakeSnapshotWorker)

    class _Host:
        pass

    host = _Host()
    host._worker = None
    host._status_lbl = _keep(QLabel())
    host._chk_listen = MagicMock(**{"isChecked.return_value": False})
    host._on_snapshot = MagicMock()

    ConnectionsPage._refresh(host)
    with caplog.at_level(logging.WARNING):
        _FakeSnapshotWorker.last.error.emit(RAW)

    _assert_translated(host._status_lbl, WE.CONNECTIONS, caplog)


# ── SMB: a Stop is not a failure ────────────────────────────────────────────────

def _smb_worker(monkeypatch, result):
    from modules import smb_enumerator
    from workers import scan_worker

    monkeypatch.setattr(smb_enumerator, "enumerate_smb", lambda *a, **k: result)
    worker = scan_worker.SMBEnumWorker(host="192.0.2.10", username="admin", password="x")
    _widgets.append(worker)
    return worker


def test_smb_stop_between_tiers_is_reported_as_stopped_not_as_an_error(monkeypatch):
    from modules import smb_enumerator

    worker = _smb_worker(
        monkeypatch, smb_enumerator.SMBEnumResult(host="192.0.2.10", error="Cancelled", tier=1),
    )
    errors: list = []
    stopped: list = []
    worker.error.connect(errors.append)
    worker.stopped.connect(lambda: stopped.append(True))

    worker.stop()
    worker.run()  # synchronously: the run body is under test, not the thread

    assert errors == [], "the user's Stop still arrived as an error"
    assert stopped == [True]


def test_smb_error_without_a_stop_is_still_an_error(monkeypatch):
    from modules import smb_enumerator

    worker = _smb_worker(
        monkeypatch, smb_enumerator.SMBEnumResult(host="192.0.2.10", error="STATUS_ACCESS_DENIED", tier=2),
    )
    errors: list = []
    stopped: list = []
    worker.error.connect(errors.append)
    worker.stopped.connect(lambda: stopped.append(True))

    worker.run()

    assert errors == ["STATUS_ACCESS_DENIED"] and stopped == []


class _FakeSmbWorker:
    last = None

    def __init__(self, **_kwargs):
        self.result = _FakeSignal()
        self.status = _FakeSignal()
        self.error = _FakeSignal()
        self.stopped = _FakeSignal()
        _FakeSmbWorker.last = self

    def start(self):
        pass  # test double — no QThread

    def isRunning(self):  # noqa: N802 - Qt's name
        return False


def _recon_host(registry: dict):
    """The attributes _ReconTabsMixin._start_smb_enum reads, with a real status label."""
    import functools

    from ui.tabs_recon import _ReconTabsMixin

    class _Host:
        pass

    host = _Host()
    host._scan_registry = registry
    host.states: list = []

    def _set_state(label, state, ts=None, error=None, verdict=None):
        host.states.append((label, state, ts, error, verdict))
        registry[label] = {"state": state, "ts": ts, "error": error, "verdict": verdict}

    host._nav_set_scan_state = _set_state
    host._smb_host = MagicMock(**{"text.return_value": "192.0.2.10"})
    host._smb_user = MagicMock(**{"text.return_value": "admin"})
    host._smb_pass = MagicMock(**{"text.return_value": "x"})
    host._smb_domain = MagicMock(**{"text.return_value": ""})
    host._smb_worker = None
    host._recon_smb_shares_table = MagicMock()
    host._recon_smb_users_table = MagicMock()
    host._smb_verdict = MagicMock()
    host._smb_status = _keep(QLabel())
    host._on_smb_result = MagicMock()
    host._on_smb_stopped = functools.partial(_ReconTabsMixin._on_smb_stopped, host)
    return host


def test_smb_page_restores_the_last_completed_run_on_stop(monkeypatch):
    from ui.nav.labels import NavLabel as L
    from ui.tabs_recon import _ReconTabsMixin
    from workers import scan_worker

    monkeypatch.setattr(scan_worker, "SMBEnumWorker", _FakeSmbWorker)
    previous ={"state": "fresh", "ts": 1_700_000_000.0, "error": None, "verdict": "2 shares"}
    host = _recon_host({L.WINDOWS_SHARES_SMB: dict(previous)})

    _ReconTabsMixin._start_smb_enum(host)
    _FakeSmbWorker.last.stopped.emit()

    assert host.states[-1] == (L.WINDOWS_SHARES_SMB, "fresh", 1_700_000_000.0, None, "2 shares")
    assert host._smb_status.text() == "SMB enumeration stopped."


def test_smb_page_stop_on_a_first_run_goes_back_to_never(monkeypatch):
    from ui.nav.labels import NavLabel as L
    from ui.tabs_recon import _ReconTabsMixin
    from workers import scan_worker

    monkeypatch.setattr(scan_worker, "SMBEnumWorker", _FakeSmbWorker)
    host = _recon_host({})

    _ReconTabsMixin._start_smb_enum(host)
    _FakeSmbWorker.last.stopped.emit()

    assert host.states[-1][:2] == (L.WINDOWS_SHARES_SMB, "never")


def test_smb_page_error_lambda_is_translated(caplog, monkeypatch):
    from ui import worker_error_catalogue as WE
    from ui.nav.labels import NavLabel as L
    from ui.tabs_recon import _ReconTabsMixin
    from workers import scan_worker

    monkeypatch.setattr(scan_worker, "SMBEnumWorker", _FakeSmbWorker)
    host = _recon_host({})

    _ReconTabsMixin._start_smb_enum(host)
    with caplog.at_level(logging.WARNING):
        _FakeSmbWorker.last.error.emit(RAW)

    _assert_translated(host._smb_status, WE.WINDOWS_SHARES, caplog)
    assert host.states[-1] == (L.WINDOWS_SHARES_SMB, "error", None, RAW, None), (
        "the registry keeps the raw detail for its tooltip"
    )

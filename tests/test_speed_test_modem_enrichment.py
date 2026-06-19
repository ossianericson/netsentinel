"""
tests/test_speed_test_modem_enrichment.py

TDD tests for Phase 1: speed test modem enrichment from any plugin source.

Contract:
- SpeedTestResult.modem_signal holds the pre-test modem snapshot (any source)
- SpeedTestWorker(modem_snapshot=...) uses the snapshot when no ZTE creds given
- SpeedTestWorker with ZTE creds still attempts a live fetch first (ZTE path unchanged)
- SpeedTestPage._run_test() reads hw_state.modem_signal as fallback snapshot
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication


# RULE-WIN4: track all QThread workers; autouse fixture deletes via deleteLater()
_created_workers: list = []


@pytest.fixture(autouse=True)
def _cleanup_workers():
    yield
    app = QApplication.instance()
    for w in _created_workers:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # non-fatal — already deleted
    if app:
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal — best-effort cleanup
        for _ in range(3):
            app.processEvents()
    _created_workers.clear()


# ── SpeedTestResult field ─────────────────────────────────────────────────────

def test_speed_test_result_has_modem_signal_field():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=0, upload_mbps=0, ping_ms=0,
        server_name="", server_city="", server_country="", backend="",
    )
    assert hasattr(r, "modem_signal")
    assert r.modem_signal is None


def test_speed_test_result_no_zte_signal_field():
    from modules.speed_tester import SpeedTestResult
    r = SpeedTestResult(
        download_mbps=0, upload_mbps=0, ping_ms=0,
        server_name="", server_city="", server_country="", backend="",
    )
    assert not hasattr(r, "zte_signal")


# ── SpeedTestWorker snapshot param ────────────────────────────────────────────

def test_worker_stores_modem_snapshot():
    from workers.speed_test_worker import SpeedTestWorker
    snapshot = {"network_type": "LTE", "signal_bars": 3}
    w = SpeedTestWorker(modem_snapshot=snapshot)
    _created_workers.append(w)
    assert w._modem_snapshot == snapshot


def test_worker_snapshot_none_by_default():
    from workers.speed_test_worker import SpeedTestWorker
    w = SpeedTestWorker()
    _created_workers.append(w)
    assert w._modem_snapshot is None


def test_worker_uses_snapshot_when_no_zte_creds(monkeypatch):
    from workers.speed_test_worker import SpeedTestWorker
    from modules.speed_tester import SpeedTestResult

    fake_result = SpeedTestResult(
        download_mbps=100, upload_mbps=50, ping_ms=10,
        server_name="test", server_city="", server_country="", backend="test",
    )
    monkeypatch.setattr("modules.speed_tester.run_test", lambda **kw: fake_result)

    snapshot = {"network_type": "NR5G", "signal_bars": 4}
    w = SpeedTestWorker(modem_snapshot=snapshot)
    _created_workers.append(w)
    emitted: list = []
    w.result_ready.connect(lambda r: emitted.append(r))
    w.run()

    assert len(emitted) == 1
    assert emitted[0].modem_signal == snapshot


def test_worker_no_snapshot_no_zte_gives_none(monkeypatch):
    from workers.speed_test_worker import SpeedTestWorker
    from modules.speed_tester import SpeedTestResult

    fake_result = SpeedTestResult(
        download_mbps=100, upload_mbps=50, ping_ms=10,
        server_name="test", server_city="", server_country="", backend="test",
    )
    monkeypatch.setattr("modules.speed_tester.run_test", lambda **kw: fake_result)

    w = SpeedTestWorker()
    _created_workers.append(w)
    emitted: list = []
    w.result_ready.connect(lambda r: emitted.append(r))
    w.run()

    assert emitted[0].modem_signal is None

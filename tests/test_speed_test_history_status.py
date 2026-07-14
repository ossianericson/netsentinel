"""
Regression test for F-79 (claims-audit): Speed Test History's "Status" column
hardcoded a green "OK" for every row loaded from the database, regardless of the
real backend/failure outcome -- unlike freshly-added live-session rows, which show
the real backend name (or "Error") in the same column. The speed_test table has no
backend/error column, so failures aren't even persisted; the DB-loaded rows were
dressing up "we don't actually know" as a confident, Ookla-style green "OK".

Fix: DB-loaded history rows now show a neutral "Recorded" label instead of
asserting "OK".
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.metric_store_schema import SpeedTestPoint
from ui.pages.speed_test_page import SpeedTestPage


def _history_point(ts: float) -> SpeedTestPoint:
    return SpeedTestPoint(
        ts=int(ts), download_mbps=100.0, upload_mbps=20.0, ping_ms=10.0,
        server_name="test", server_city="", server_country="",
    )


@pytest.fixture
def page(monkeypatch):
    from PyQt6.QtWidgets import QApplication

    monkeypatch.setattr(SpeedTestPage, "_fetch_servers", lambda self: None)
    store = MagicMock()
    store.query_speed_test_history.return_value = [_history_point(1_700_000_000.0)]
    p = SpeedTestPage(store=store)
    p.show()
    app = QApplication.instance()
    if app:
        app.processEvents()
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # non-fatal -- widget may have already been destroyed
    if app:
        for _ in range(3):
            app.processEvents()


def test_history_row_does_not_claim_ok(page):
    """DB-loaded rows must not assert a status they have no data to back up."""
    page._hist_table.setRowCount(0)
    page._load_history_from_db()
    assert page._hist_table.rowCount() == 1
    status_col = page._hist_table.columnCount() - 1
    status_text = page._hist_table.item(0, status_col).text()
    assert status_text != "OK"
    assert status_text == "Recorded"

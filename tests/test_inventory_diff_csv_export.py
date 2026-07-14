"""
Regression test for F-63: Inventory Changes claimed CSV export of the
scan-compare diff table, but _cmp_table had no export control at all --
the page's only Export button exported a different table (the event log).
"""
from __future__ import annotations

import csv

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTableWidgetItem
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.metric_store import MetricStore
from ui.pages.inventory_page import InventoryPage

_created_pages: list = []


@pytest.fixture(autouse=True)
def _cleanup_pages():
    yield
    app = QApplication.instance()
    for page in _created_pages:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()
    _created_pages.clear()


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_page(store) -> InventoryPage:
    page = InventoryPage(store=store)
    _created_pages.append(page)
    return page


def test_export_diff_csv_writes_cmp_table_rows(store, tmp_path, monkeypatch):
    page = _make_page(store)

    # Populate the diff table the same shape _start_compare_mode() builds:
    # col 0 = status dot, cols 1-5 = Status/IP-Host/MAC/Vendor/First Seen.
    page._cmp_table.setRowCount(0)
    page._cmp_table.insertRow(0)
    for col, text in enumerate(
        ["NEW", "kitchen-echo", "aa:bb:cc:dd:ee:ff", "Amazon", "2026-07-01 10:00"],
        start=1,
    ):
        page._cmp_table.setItem(0, col, QTableWidgetItem(text))

    out_path = tmp_path / "diff.csv"
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: (str(out_path), ""),
    )

    page._export_diff_csv()

    assert out_path.exists()
    with open(out_path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Status", "IP / Host", "MAC", "Vendor", "First Seen"]
    assert rows[1] == ["NEW", "kitchen-echo", "aa:bb:cc:dd:ee:ff", "Amazon", "2026-07-01 10:00"]


def test_export_diff_csv_noop_when_dialog_cancelled(store, tmp_path, monkeypatch):
    page = _make_page(store)
    page._cmp_table.setRowCount(0)
    page._cmp_table.insertRow(0)

    monkeypatch.setattr(
        "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **kw: ("", ""),
    )
    page._export_diff_csv()  # must not raise

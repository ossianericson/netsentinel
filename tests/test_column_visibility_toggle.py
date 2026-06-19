"""Tests for ui.widgets.column_visibility_toggle (Sprint 7, S7-2)."""
import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QTableWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")

_COLS = ["●", "Segment", "IP Address", "Label", "Hostname", "MAC Address", "Manufacturer", "Type", "Risk"]
_QUICK = [0, 3, 4, 7]


def _fresh(key: str):
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove(f"columns/{key}")
    return qs


def _cleanup(*widgets):
    app = QApplication.instance()
    for w in widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # already destroyed — safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def table():
    QApplication.instance()
    t = QTableWidget(0, len(_COLS))
    t.setHorizontalHeaderLabels(_COLS)
    yield t
    _cleanup(t)


class TestColumnVisibilityToggle:
    def setup_method(self):    _fresh("test_table")
    def teardown_method(self): _fresh("test_table")

    def test_import(self):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle  # noqa: F401

    def test_defaults_to_full_all_columns_visible(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        toggle = ColumnVisibilityToggle("test_table", table, _QUICK)
        for col in range(table.columnCount()):
            assert table.isColumnHidden(col) is False
        _cleanup(toggle)

    def test_quick_mode_hides_non_quick_columns(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        toggle = ColumnVisibilityToggle("test_table", table, _QUICK)
        toggle._btn_quick.click()
        for col in range(table.columnCount()):
            assert table.isColumnHidden(col) is (col not in _QUICK)
        _cleanup(toggle)

    def test_full_mode_shows_all_columns_after_quick(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        toggle = ColumnVisibilityToggle("test_table", table, _QUICK)
        toggle._btn_quick.click()
        toggle._btn_full.click()
        for col in range(table.columnCount()):
            assert table.isColumnHidden(col) is False
        _cleanup(toggle)

    def test_mode_persists_to_qsettings(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        toggle = ColumnVisibilityToggle("test_table", table, _QUICK)
        toggle._btn_quick.click()
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("columns/test_table", "") == "quick"
        _cleanup(toggle)

    def test_new_toggle_restores_persisted_quick_mode(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        toggle1 = ColumnVisibilityToggle("test_table", table, _QUICK)
        toggle1._btn_quick.click()
        _cleanup(toggle1)

        toggle2 = ColumnVisibilityToggle("test_table", table, _QUICK)
        for col in range(table.columnCount()):
            assert table.isColumnHidden(col) is (col not in _QUICK)
        _cleanup(toggle2)

    def test_independent_tables_track_separately(self, table):
        from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
        _fresh("other_table")
        toggle_a = ColumnVisibilityToggle("test_table", table, _QUICK)
        toggle_a._btn_quick.click()

        t2 = QTableWidget(0, len(_COLS))
        t2.setHorizontalHeaderLabels(_COLS)
        toggle_b = ColumnVisibilityToggle("other_table", t2, _QUICK)
        for col in range(t2.columnCount()):
            assert t2.isColumnHidden(col) is False

        _cleanup(toggle_a, toggle_b, t2)
        _fresh("other_table")

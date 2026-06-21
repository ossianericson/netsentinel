"""Tests for ui/widgets/inventory_dialogs.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_store(tmp_path):
    from modules.metric_store import MetricStore
    return MetricStore(db_path=tmp_path / "test.db")


# ── Import test ───────────────────────────────────────────────────────────────

def test_import():
    from ui.widgets.inventory_dialogs import (  # noqa: F401
        _DeviceLabelDialog, _TypeOverrideDialog,
        _ScanCompareDialog, _SegmentEditorDialog,
    )


# ── _ScanCompareDialog ────────────────────────────────────────────────────────

@pytest.fixture
def scan_compare_dialog():
    from ui.widgets.inventory_dialogs import _ScanCompareDialog
    sessions = [(1000, "Scan 2024-01-01 10:00"), (2000, "Scan 2024-01-02 10:00")]
    d = _ScanCompareDialog(sessions=sessions)
    yield d
    try:
        d.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_scan_compare_dialog_instantiation(scan_compare_dialog):
    assert scan_compare_dialog is not None


def test_scan_compare_dialog_result_timestamps_before_accept(scan_compare_dialog):
    """Before accept, result_timestamps should return (0, 0)."""
    ts_a, ts_b = scan_compare_dialog.result_timestamps()
    assert ts_a == 0
    assert ts_b == 0


# ── _SegmentEditorDialog ──────────────────────────────────────────────────────

@pytest.fixture
def segment_editor_dialog():
    from ui.widgets.inventory_dialogs import _SegmentEditorDialog
    d = _SegmentEditorDialog(segment=None)
    yield d
    try:
        d.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_segment_editor_dialog_instantiation(segment_editor_dialog):
    assert segment_editor_dialog is not None


def test_segment_editor_result_has_required_keys(segment_editor_dialog):
    """result_segment() should always return a dict with name/cidr/color/description."""
    result = segment_editor_dialog.result_segment()
    assert "name" in result
    assert "cidr" in result
    assert "color" in result
    assert "description" in result


def test_segment_editor_default_name(segment_editor_dialog):
    """An empty name field should default to 'Unnamed Segment'."""
    segment_editor_dialog._name_edit.clear()
    result = segment_editor_dialog.result_segment()
    assert result["name"] == "Unnamed Segment"

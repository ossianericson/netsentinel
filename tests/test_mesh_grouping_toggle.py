"""
tests/test_mesh_grouping_toggle.py

TDD tests for the _RouterDetailPanel view-mode toggle (flat vs grouped-by-node).

Contract:
- Panel has a toggle button (_toggle_btn) that switches between flat and grouped views
- Default view: flat QTableWidget (current behaviour unchanged)
- Grouped view: QTreeWidget where each node is a top-level item, clients are children
- Clients with no unit field fall back to a "Router" group
- Toggling back restores flat view with the same data
- Works for all plugins: Deco (many nodes), FritzBox (no nodes/single group), etc.
"""

from __future__ import annotations

import sys

import pytest

try:
    from PyQt6.QtWidgets import (
        QApplication, QPushButton, QStackedWidget, QTableWidget, QTreeWidget,
    )
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

from ui.pages.hardware_integration_page import _RouterDetailPanel


def _clients(n: int, unit: str = "Main") -> list:
    return [
        {"hostname": f"device{i}", "ip": f"10.0.0.{i}",
         "mac": f"aa:bb:cc:dd:ee:{i:02x}", "band": "5G", "unit": unit}
        for i in range(n)
    ]


def _status(nodes: list | None = None, n: int = 0) -> dict:
    nodes = nodes or []
    return {"connected_clients": n, "mesh_nodes": len(nodes),
            "extra": {"nodes": nodes}}


@pytest.fixture
def panel():
    p = _RouterDetailPanel()
    yield p
    p.deleteLater()
    _app.processEvents()


# ── Structure ─────────────────────────────────────────────────────────────────

def test_toggle_button_exists(panel):
    assert hasattr(panel, "_toggle_btn")
    assert isinstance(panel._toggle_btn, QPushButton)


def test_client_stack_exists(panel):
    assert hasattr(panel, "_client_stack")
    assert isinstance(panel._client_stack, QStackedWidget)


def test_tree_widget_exists(panel):
    assert hasattr(panel, "_tree_widget")
    assert isinstance(panel._tree_widget, QTreeWidget)


def test_initial_view_is_flat(panel):
    assert panel._view_mode == "flat"


def test_flat_table_on_stack_page_zero(panel):
    assert panel._client_stack.indexOf(panel._client_table) == 0


def test_tree_on_stack_page_one(panel):
    assert panel._client_stack.indexOf(panel._tree_widget) == 1


# ── Toggle behaviour ──────────────────────────────────────────────────────────

def test_toggle_switches_to_grouped(panel):
    panel._toggle_btn.click()
    assert panel._view_mode == "grouped"


def test_toggle_back_to_flat(panel):
    panel._toggle_btn.click()
    panel._toggle_btn.click()
    assert panel._view_mode == "flat"


def test_stack_shows_tree_when_grouped(panel):
    panel._toggle_btn.click()
    assert panel._client_stack.currentWidget() is panel._tree_widget


def test_stack_shows_table_when_flat(panel):
    panel._toggle_btn.click()
    panel._toggle_btn.click()
    assert panel._client_stack.currentWidget() is panel._client_table


# ── Grouped view data ─────────────────────────────────────────────────────────

def test_grouped_total_client_count_matches(panel):
    nodes = [{"name": "Main", "role": "master", "mac": "aa:00:00:00:00:01"}]
    panel.update(_status(nodes, 5), _clients(5))
    panel._toggle_btn.click()
    tree = panel._tree_widget
    total = sum(
        tree.topLevelItem(i).childCount()
        for i in range(tree.topLevelItemCount())
    )
    assert total == 5


def test_clients_grouped_under_correct_node(panel):
    clients = [
        {"hostname": "a", "ip": "10.0.0.1", "mac": "aa:00:00:00:00:01",
         "band": "5G", "unit": "Main"},
        {"hostname": "b", "ip": "10.0.0.2", "mac": "aa:00:00:00:00:02",
         "band": "5G", "unit": "Satellite"},
        {"hostname": "c", "ip": "10.0.0.3", "mac": "aa:00:00:00:00:03",
         "band": "5G", "unit": "Satellite"},
    ]
    nodes = [
        {"name": "Main",      "role": "master", "mac": "aa:00:00:00:00:aa"},
        {"name": "Satellite", "role": "slave",  "mac": "aa:00:00:00:00:bb"},
    ]
    panel.update(_status(nodes, 3), clients)
    panel._toggle_btn.click()
    tree = panel._tree_widget
    sat_item = next(
        (tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
         if "Satellite" in tree.topLevelItem(i).text(0)),
        None,
    )
    assert sat_item is not None
    assert sat_item.childCount() == 2


def test_clients_with_no_unit_grouped_under_fallback(panel):
    clients = [
        {"hostname": "x", "ip": "10.0.0.1",
         "mac": "aa:00:00:00:00:01", "band": "5G", "unit": ""},
    ]
    panel.update(_status([], 1), clients)
    panel._toggle_btn.click()
    assert panel._tree_widget.topLevelItemCount() >= 1


def test_single_ap_plugin_all_clients_under_one_group(panel):
    """FritzBox / Netgear style: no nodes, unit field absent or empty."""
    clients = [
        {"hostname": f"h{i}", "ip": f"10.0.0.{i}", "mac": f"aa:bb:cc:dd:ee:{i:02x}",
         "band": "Wired"}
        for i in range(4)
    ]
    panel.update(_status([], 4), clients)
    panel._toggle_btn.click()
    tree = panel._tree_widget
    total = sum(
        tree.topLevelItem(i).childCount()
        for i in range(tree.topLevelItemCount())
    )
    assert total == 4


def test_flat_view_still_correct_after_toggle_cycle(panel):
    nodes = [{"name": "Main", "role": "master", "mac": "aa:00:00:00:00:01"}]
    panel.update(_status(nodes, 3), _clients(3))
    panel._toggle_btn.click()   # grouped
    panel._toggle_btn.click()   # back to flat
    assert panel._client_table.rowCount() == 3

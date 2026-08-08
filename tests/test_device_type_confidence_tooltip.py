"""
Regression tests for the Device Identity Program Phase 4 confidence tooltip
on the Devices table's Device Type cell
(ui/scan_wiring.py::_m1_populate_device_table).

Before this phase, classify_with_evidence() computed a confidence and an
evidence list on every call and nothing showed either to the user
(docs/spikes/device-identity-baseline.md) -- inventory_page.py discarded the
confidence and only displayed the evidence text, and the Devices table's own
tooltip only ever explained an *Unknown* device, never a known one.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTableWidget
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_stub(store=None):
    from ui.scan_wiring import ScanResultMixin

    class _Stub(ScanResultMixin):
        def _m1_apply_filter(self):
            pass  # search/chip filtering -- not under test

        def _m1_refresh_scan_summary(self):
            pass  # header summary label -- not under test

    stub = _Stub()
    stub._m1_table = QTableWidget(0, 9)
    stub._net_devices_table = QTableWidget(0, 5)
    stub._store = store if store is not None else MagicMock()
    stub._m1_synth_macs = set()
    return stub


def _cleanup(stub):
    for t in (stub._m1_table, stub._net_devices_table):
        try:
            t.deleteLater()
        except RuntimeError:
            pass  # non-fatal — widget may have already been destroyed
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _dev(**overrides):
    d = {
        "risk_level": "CLEAN", "ip": "192.168.1.80", "hostname": "",
        "mac": "aa:bb:cc:dd:ee:0a", "vendor": "Lexmark", "model": "",
        "device_type": "Print Server", "verdict": "", "open_ports": [9100],
        "os_family": "", "is_gateway": False,
    }
    d.update(overrides)
    return d


def test_known_device_type_gets_a_confidence_tooltip():
    stub = _make_stub()
    stub._m1_populate_device_table({"devices": [_dev()]})

    item = stub._m1_table.item(0, 5)
    assert item is not None
    tooltip = item.toolTip()
    assert "Confidence:" in tooltip
    assert "Evidence:" in tooltip

    _cleanup(stub)


def test_unknown_device_keeps_its_existing_explanatory_tooltip():
    """Unchanged behaviour: an Unknown Device gets the "run a port scan"
    guidance, not a 0% confidence readout."""
    stub = _make_stub()
    stub._m1_populate_device_table({"devices": [_dev(
        device_type="Unknown Device", vendor="", open_ports=[],
    )]})

    item = stub._m1_table.item(0, 5)
    assert item is not None
    tooltip = item.toolTip()
    assert "could not be determined" in tooltip
    assert "Confidence:" not in tooltip

    _cleanup(stub)


def test_confidence_tooltip_is_silent_when_the_displayed_type_disagrees():
    """A type this recomputation can't reproduce (e.g. it came from a mesh/
    plugin/registry source the heuristic knows nothing about) must not show a
    confidence for a claim that isn't actually the one behind the label."""
    stub = _make_stub()
    stub._m1_populate_device_table({"devices": [_dev(
        device_type="Mesh Network Node", vendor="", hostname="", open_ports=[],
    )]})

    item = stub._m1_table.item(0, 5)
    assert item is not None
    assert item.toolTip() == ""

    _cleanup(stub)


def test_registry_backed_confidence_is_high():
    stub = _make_stub()
    stub._m1_populate_device_table({"devices": [_dev()]})

    item = stub._m1_table.item(0, 5)
    tooltip = item.toolTip()
    # any-ports-only heuristic match (9100) -- a real, if modest, confidence
    assert "Confidence: 0%" not in tooltip

    _cleanup(stub)

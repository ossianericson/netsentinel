"""
tests/test_hardware_hub_tabs.py

TDD tests for the QTabWidget-based Hardware Hub page.

Tab contract:
  index 0  "Hardware"       — always visible, HubCards + add button
  index 1  "Modem"          — hidden until modem data arrives
  index 2  "Mesh & Router"  — hidden until router data arrives
  index 3  "Suggested (N)"  — hidden until hw_detect matches found

All tests create a fresh HardwareIntegrationPage on the offscreen platform.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTabWidget
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])

# Patch keyring + QSettings so the page can construct without credentials
with (
    patch("keyring.get_password", return_value=None),
    patch("workers.plugin_polling_worker.PluginPollingWorker", MagicMock()),
):
    from ui.pages.hardware_integration_page import HardwareIntegrationPage


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._load_paths", lambda: []
    )
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._load_last_result",
        lambda _: None,
    )
    p = HardwareIntegrationPage()
    yield p
    p.deleteLater()
    _app.processEvents()


# ── Tab 0: Hardware always present ────────────────────────────────────────────

def test_tabs_widget_exists(page):
    assert isinstance(page._tabs, QTabWidget)


def test_hardware_tab_always_present(page):
    assert page._tabs.count() >= 4


def test_hardware_tab_index_zero(page):
    assert page._tabs.tabText(0) == "Hardware"


def test_hardware_tab_always_visible(page):
    assert page._tabs.isTabVisible(0)


# ── Tab 1: Modem — hidden initially ──────────────────────────────────────────

def test_modem_tab_exists(page):
    assert hasattr(page, "_modem_tab_idx")


def test_modem_tab_hidden_initially(page):
    assert not page._tabs.isTabVisible(page._modem_tab_idx)


def test_modem_tab_title_contains_modem(page):
    assert "Modem" in page._tabs.tabText(page._modem_tab_idx)


# ── Tab 2: Mesh & Router — hidden initially ───────────────────────────────────

def test_mesh_tab_exists(page):
    assert hasattr(page, "_mesh_tab_idx")


def test_mesh_tab_hidden_initially(page):
    assert not page._tabs.isTabVisible(page._mesh_tab_idx)


# ── Tab 3: Suggested — hidden initially ──────────────────────────────────────

def test_suggested_tab_exists(page):
    assert hasattr(page, "_suggested_tab_idx")


def test_suggested_tab_hidden_initially(page):
    assert not page._tabs.isTabVisible(page._suggested_tab_idx)


# ── Modem tab appears and updates on data ─────────────────────────────────────

def test_modem_tab_appears_on_data(page):
    page.on_modem_card_data({"network_type": "NR5G", "signal_bars": 4})
    assert page._tabs.isTabVisible(page._modem_tab_idx)


def test_modem_tab_title_shows_5g(page):
    page.on_modem_card_data({"network_type": "NR5G"})
    assert "5G" in page._tabs.tabText(page._modem_tab_idx)


def test_modem_tab_title_shows_lte(page):
    page.on_modem_card_data({"network_type": "LTE"})
    assert "LTE" in page._tabs.tabText(page._modem_tab_idx)


def test_modem_tab_title_fallback_when_no_network_type(page):
    page.on_modem_card_data({})
    # Must still show tab without crashing; title contains "Modem" at minimum
    assert "Modem" in page._tabs.tabText(page._modem_tab_idx)


def test_modem_tab_no_duplicate_on_second_call(page):
    count = page._tabs.count()
    page.on_modem_card_data({"network_type": "LTE"})
    page.on_modem_card_data({"network_type": "NR5G"})
    assert page._tabs.count() == count


# ── Mesh tab appears and updates on data ──────────────────────────────────────

def test_mesh_tab_appears_on_data(page):
    page.on_mesh_card_data([], [])
    assert page._tabs.isTabVisible(page._mesh_tab_idx)


def _ns_clients(n: int):
    """Return n SimpleNamespace objects that look like MeshClient."""
    from types import SimpleNamespace
    return [
        SimpleNamespace(ip=f"10.0.0.{i}", mac=f"aa:bb:cc:dd:ee:0{i}",
                        name=f"device{i}", band="5G", unit_name="Main")
        for i in range(n)
    ]


def test_mesh_tab_shows_client_count(page):
    page.on_mesh_card_data([], _ns_clients(5))
    assert "5" in page._tabs.tabText(page._mesh_tab_idx)


def test_mesh_tab_no_duplicate_on_second_call(page):
    count = page._tabs.count()
    page.on_mesh_card_data([], [])
    page.on_mesh_card_data([], _ns_clients(1))
    assert page._tabs.count() == count


# ── Suggested tab appears on detection ───────────────────────────────────────

_FRITZBOX_MATCH = {
    "plugin": {"id": "fritzbox", "name": "AVM FRITZ!Box",
               "file": "plugins/fritzbox_plugin.py", "manufacturer": "AVM"},
    "confidence": 0.85,
    "signals": ["192.168.178.1"],
}


def test_suggested_tab_appears_on_detection(page, monkeypatch):
    # Patch at source so the local import inside on_hardware_detected sees it
    monkeypatch.setattr("modules.hw_detect.already_installed", lambda _: False)
    page.on_hardware_detected([_FRITZBOX_MATCH])
    assert page._tabs.isTabVisible(page._suggested_tab_idx)


def test_suggested_tab_hidden_when_no_visible_matches(page, monkeypatch):
    monkeypatch.setattr("modules.hw_detect.already_installed", lambda _: True)
    page.on_hardware_detected([_FRITZBOX_MATCH])
    assert not page._tabs.isTabVisible(page._suggested_tab_idx)


def test_suggested_tab_count_badge(page, monkeypatch):
    monkeypatch.setattr("modules.hw_detect.already_installed", lambda _: False)
    matches = [
        {"plugin": {"id": f"p{i}", "name": f"Device {i}", "file": "f.py",
                    "manufacturer": "X"},
         "confidence": 0.9, "signals": []}
        for i in range(3)
    ]
    page.on_hardware_detected(matches)
    assert "3" in page._tabs.tabText(page._suggested_tab_idx)


# ── hw_state wired ────────────────────────────────────────────────────────────

def test_modem_data_updates_hw_state(page):
    from modules.network_infrastructure import hw_state
    page.on_modem_card_data({"network_type": "NR5G", "signal_bars": 3})
    assert hw_state.modem_signal is not None
    assert hw_state.modem_signal.get("network_type") == "NR5G"


def test_mesh_data_updates_hw_state(page):
    from modules.network_infrastructure import hw_state
    page.on_mesh_card_data([], _ns_clients(1), provider="Deco")
    assert hw_state.router_hw_name != "" or hw_state.router_source != ""

"""
tests/test_network_infrastructure.py

Unit tests for modules/network_infrastructure.py — the shared hardware
state singleton used by speed test, log hub, hardware hub tabs, and topology.

All tests operate on fresh NetworkInfrastructureState instances so the
module-level singleton is never mutated between test runs.
"""

from __future__ import annotations

import pytest
from modules.network_infrastructure import NetworkInfrastructureState


@pytest.fixture
def state() -> NetworkInfrastructureState:
    return NetworkInfrastructureState()


# ── Initial state ─────────────────────────────────────────────────────────────

def test_initial_modem_signal_none(state):
    assert state.modem_signal is None


def test_initial_router_clients_empty(state):
    assert state.router_clients == []


def test_initial_wan_ip_none(state):
    assert state.wan_ip is None


# ── Modem updates ─────────────────────────────────────────────────────────────

def test_update_modem_stores_signal(state):
    sig = {"network_type": "NR5G", "signal_bars": 4}
    state.update_modem(sig, source="zte", hw_name="ZTE MC889")
    assert state.modem_signal == sig


def test_update_modem_stores_source(state):
    state.update_modem({}, source="/home/.netsentinel/plugins/zte_plugin.py")
    assert "zte_plugin.py" in state.modem_source


def test_update_modem_stores_hw_name(state):
    state.update_modem({}, source="zte", hw_name="ZTE MC889")
    assert state.modem_hw_name == "ZTE MC889"


def test_update_modem_extracts_wan_ip(state):
    state.update_modem({"wan_ip": "1.2.3.4"}, source="zte")
    assert state.wan_ip == "1.2.3.4"


def test_update_modem_missing_wan_ip_preserves_existing(state):
    state.wan_ip = "9.9.9.9"
    state.update_modem({"network_type": "LTE"}, source="zte")
    assert state.wan_ip == "9.9.9.9"


def test_update_modem_hw_name_defaults_to_source(state):
    state.update_modem({}, source="my_plugin_path")
    assert state.modem_hw_name == "my_plugin_path"


# ── Modem clear ──────────────────────────────────────────────────────────────

def test_clear_modem_resets_signal(state):
    state.update_modem({"network_type": "LTE"}, source="zte")
    state.clear_modem()
    assert state.modem_signal is None


def test_clear_modem_resets_source(state):
    state.update_modem({}, source="zte")
    state.clear_modem()
    assert state.modem_source == ""


def test_clear_modem_does_not_clear_wan_ip(state):
    state.update_modem({"wan_ip": "1.2.3.4"}, source="zte")
    state.clear_modem()
    # wan_ip may still be known from last state — don't wipe it on disconnect
    assert state.wan_ip == "1.2.3.4"


# ── Router updates ────────────────────────────────────────────────────────────

def test_update_router_stores_clients(state):
    clients = [{"ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "phone"}]
    state.update_router(clients, [], source="deco", hw_name="TP-Link Deco")
    assert state.router_clients == clients


def test_update_router_stores_nodes(state):
    nodes = [{"name": "Main", "role": "master", "mac": "11:22:33:44:55:66"}]
    state.update_router([], nodes, source="deco")
    assert state.router_nodes == nodes


def test_update_router_stores_hw_name(state):
    state.update_router([], [], source="path", hw_name="UniFi Dream Machine")
    assert state.router_hw_name == "UniFi Dream Machine"


def test_update_router_hw_name_defaults_to_source(state):
    state.update_router([], [], source="fritzbox_plugin.py")
    assert state.router_hw_name == "fritzbox_plugin.py"


# ── Router clear ──────────────────────────────────────────────────────────────

def test_clear_router_resets_clients(state):
    state.update_router([{"ip": "x"}], [], source="deco")
    state.clear_router()
    assert state.router_clients == []


def test_clear_router_resets_nodes(state):
    state.update_router([], [{"name": "n"}], source="deco")
    state.clear_router()
    assert state.router_nodes == []


# ── Multiple updates ──────────────────────────────────────────────────────────

def test_second_modem_update_overwrites_first(state):
    state.update_modem({"network_type": "LTE"}, source="zte")
    state.update_modem({"network_type": "NR5G"}, source="zte")
    assert state.modem_signal["network_type"] == "NR5G"


def test_router_update_after_modem_does_not_clear_modem(state):
    state.update_modem({"network_type": "LTE"}, source="zte")
    state.update_router([], [], source="deco")
    assert state.modem_signal is not None


def test_modem_update_after_router_does_not_clear_router(state):
    state.update_router([{"ip": "x"}], [], source="deco")
    state.update_modem({}, source="zte")
    assert state.router_clients != []

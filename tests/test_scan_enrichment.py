"""Regression tests for ui/scan_enrichment.py gateway-hostname-guard fixes.

Fix 4 — filter gateway MAC from plugin enrichment dict
Fix 2 — gateway IP guard in plugin enrichment loop (no hostname overwrite)
Fix 3 — IP-keyed hostname sync skips gateway DeviceInfo
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_table(rows: list[tuple[str, str, str]]) -> QTableWidget:
    """Return a QTableWidget with columns [ip, hostname, mac, -, -, type, node, band]."""
    t = QTableWidget(len(rows), 8)
    for r, (ip, name, mac) in enumerate(rows):
        if ip:
            t.setItem(r, 0, QTableWidgetItem(ip))
        if name:
            t.setItem(r, 1, QTableWidgetItem(name))
        if mac:
            t.setItem(r, 2, QTableWidgetItem(mac))
    return t


def _make_stub(table, m1_result, net_info, plugin_enrichments=None):
    """Return a minimal ScanEnrichmentMixin instance wired to a real QTableWidget."""
    from ui.scan_enrichment import ScanEnrichmentMixin

    class _Stub(ScanEnrichmentMixin):
        def _update_m4_deco_chips(self):
            pass  # WiFi page chips — not under test

    stub = _Stub()
    stub._m1_table = table
    stub._m1_result = m1_result
    stub._net_info = net_info
    stub._mesh_enrichment = {}
    stub._plugin_enrichments = plugin_enrichments or {}
    stub._plugin_nodes = {}
    stub._m1_group_by_node = False
    stub._plugin_hardware_name = "TestRouter"
    return stub


def _cleanup(table):
    try:
        table.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may have already been destroyed
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ---------------------------------------------------------------------------
# Fix 4 — plugin client list must not include the gateway's own MAC
# ---------------------------------------------------------------------------

def test_plugin_enrichment_excludes_gateway_mac(monkeypatch):
    """Gateway's own MAC must never appear in _plugin_enrichments as a client entry."""
    from modules.deco_client import _norm_mac
    from ui.scan_enrichment import ScanEnrichmentMixin

    monkeypatch.setattr(
        "modules.network_infrastructure.hw_state.update_router",
        lambda *a, **kw: None,
    )

    GW_MAC = "aa:bb:cc:dd:ee:01"
    CLIENT_MAC = "aa:bb:cc:dd:ee:02"

    class _Stub(ScanEnrichmentMixin):
        def __init__(self):
            self._net_info = {"gateway": "192.168.1.1", "gateway_mac": GW_MAC}
            self._plugin_enrichments = {}
            self._plugin_nodes = {}
            self._plugin_hardware_name = ""
            self._mesh_enrichment = {}
            self._m1_result = None

        def _apply_mesh_enrichment(self):
            pass  # Qt-dependent; not under test here

        def _on_modem_signal(self, data):
            pass  # not under test

        def _refresh_hardware_badge(self):
            pass  # badge widget — not under test

    stub = _Stub()
    stub._on_hardware_plugin_result({
        "info": {"type": "router", "name": "TestRouter"},
        "status": {},
        "clients": [
            {"mac": GW_MAC,     "hostname": "Router itself", "ip": "192.168.1.1"},
            {"mac": CLIENT_MAC, "hostname": "Laptop",        "ip": "192.168.1.100"},
        ],
        "_path": "test_router",
    })

    enrichment = stub._plugin_enrichments["test_router"]
    assert _norm_mac(GW_MAC) not in enrichment, \
        "Gateway MAC must be excluded from the enrichment dict"
    assert _norm_mac(CLIENT_MAC) in enrichment, \
        "Regular client MAC must be present in the enrichment dict"


def test_plugin_enrichment_no_net_info_keeps_all_clients(monkeypatch):
    """When _net_info is None the filter is skipped; all clients are retained."""
    from modules.deco_client import _norm_mac
    from ui.scan_enrichment import ScanEnrichmentMixin

    monkeypatch.setattr(
        "modules.network_infrastructure.hw_state.update_router",
        lambda *a, **kw: None,
    )

    MAC_A = "11:22:33:44:55:01"
    MAC_B = "11:22:33:44:55:02"

    class _Stub(ScanEnrichmentMixin):
        def __init__(self):
            self._net_info = None
            self._plugin_enrichments = {}
            self._plugin_nodes = {}
            self._plugin_hardware_name = ""
            self._mesh_enrichment = {}
            self._m1_result = None

        def _apply_mesh_enrichment(self):
            pass

        def _on_modem_signal(self, data):
            pass

        def _refresh_hardware_badge(self):
            pass  # badge widget — not under test

    stub = _Stub()
    stub._on_hardware_plugin_result({
        "info": {"type": "router", "name": "R"},
        "status": {},
        "clients": [
            {"mac": MAC_A, "hostname": "DeviceA", "ip": "192.168.1.2"},
            {"mac": MAC_B, "hostname": "DeviceB", "ip": "192.168.1.3"},
        ],
        "_path": "router2",
    })

    enrichment = stub._plugin_enrichments["router2"]
    assert _norm_mac(MAC_A) in enrichment
    assert _norm_mac(MAC_B) in enrichment


# ---------------------------------------------------------------------------
# Fix 2 — plugin hostname write is skipped for the gateway table row
# ---------------------------------------------------------------------------

def test_gateway_hostname_not_overwritten_by_plugin():
    """Fix 2: a plugin entry matching the gateway IP must not change the gateway's
    hostname cell in the Devices table."""
    from modules.deco_client import _norm_mac
    from modules.rogue_device import DeviceInfo

    GW_IP = "192.168.1.1"
    GW_MAC = "aa:bb:cc:dd:ee:01"
    GW_HOSTNAME = "MyRouter"
    PLUGIN_HOSTNAME = "PlayStation 4"  # wrong hostname supplied by plugin

    table = _make_table([
        (GW_IP,          GW_HOSTNAME,    GW_MAC),
        ("192.168.1.100", "Laptop",      "aa:bb:cc:dd:ee:02"),
    ])

    d_gw = DeviceInfo(ip=GW_IP, mac=GW_MAC, hostname=GW_HOSTNAME)
    plugin_enrichments = {
        "router": {
            _norm_mac(GW_MAC): {
                "mac": GW_MAC, "hostname": PLUGIN_HOSTNAME,
                "ip": GW_IP, "band": "5 GHz", "unit": "Main",
            },
        },
    }

    stub = _make_stub(
        table,
        m1_result={"devices": [d_gw]},
        net_info={"gateway": GW_IP, "gateway_mac": GW_MAC},
        plugin_enrichments=plugin_enrichments,
    )
    stub._apply_mesh_enrichment()

    cell = table.item(0, 1)
    in_table = cell.text() if cell else ""
    assert in_table != PLUGIN_HOSTNAME, \
        "Gateway row hostname must not be overwritten by plugin client data"
    assert in_table == GW_HOSTNAME, \
        "Gateway row hostname must remain unchanged after enrichment"

    _cleanup(table)


def test_non_gateway_hostname_updated_by_plugin():
    """Fix 2 must not block hostname updates for non-gateway rows."""
    from modules.deco_client import _norm_mac
    from modules.rogue_device import DeviceInfo

    GW_IP = "192.168.1.1"
    CLIENT_IP = "192.168.1.50"
    CLIENT_MAC = "bb:cc:dd:ee:ff:01"

    table = _make_table([
        (GW_IP,      "Router",   "aa:bb:cc:dd:ee:01"),
        (CLIENT_IP,  "",          CLIENT_MAC),  # no hostname yet
    ])

    d_client = DeviceInfo(ip=CLIENT_IP, mac=CLIENT_MAC, hostname="")
    plugin_enrichments = {
        "router": {
            _norm_mac(CLIENT_MAC): {
                "mac": CLIENT_MAC, "hostname": "SmartTV",
                "ip": CLIENT_IP, "band": "2.4 GHz", "unit": "Satellite",
            },
        },
    }

    stub = _make_stub(
        table,
        m1_result={"devices": [d_client]},
        net_info={"gateway": GW_IP, "gateway_mac": "aa:bb:cc:dd:ee:01"},
        plugin_enrichments=plugin_enrichments,
    )
    stub._apply_mesh_enrichment()

    cell = table.item(1, 1)
    in_table = cell.text() if cell else ""
    assert in_table == "SmartTV", \
        "Non-gateway row hostname must be updated from plugin data"

    _cleanup(table)


# ---------------------------------------------------------------------------
# Fix 3 — IP-keyed hostname sync skips gateway DeviceInfo
# ---------------------------------------------------------------------------

def test_ip_keyed_sync_skips_gateway_deviceinfo():
    """Fix 3: table-cell sync must not overwrite gateway DeviceInfo.hostname."""
    from modules.rogue_device import DeviceInfo

    GW_IP = "192.168.1.1"
    GW_HOSTNAME = "OriginalRouterHostname"

    # Simulate a table where the gateway cell was (wrongly) set to a different name
    table = _make_table([
        (GW_IP,          "WrongNameInTable",   "aa:bb:cc:dd:ee:01"),
        ("192.168.1.50", "LaptopEnriched",      "cc:dd:ee:ff:00:11"),
    ])
    d_gw     = DeviceInfo(ip=GW_IP,         mac="aa:bb:cc:dd:ee:01",  hostname=GW_HOSTNAME)
    d_laptop = DeviceInfo(ip="192.168.1.50", mac="cc:dd:ee:ff:00:11", hostname="")

    stub = _make_stub(
        table,
        m1_result={"devices": [d_gw, d_laptop]},
        net_info={"gateway": GW_IP, "gateway_mac": "aa:bb:cc:dd:ee:01"},
    )
    stub._apply_mesh_enrichment()

    assert d_gw.hostname == GW_HOSTNAME, \
        "Gateway DeviceInfo.hostname must not be overwritten by table-cell sync"
    assert d_laptop.hostname == "LaptopEnriched", \
        "Non-gateway DeviceInfo.hostname must be updated from the table cell"

    _cleanup(table)


def test_shared_mac_sync_skips_gateway_updates_client():
    """Fix 3: when two DeviceInfo objects share the same MAC (proxy-ARP scenario),
    the IP-keyed sync must guard the gateway and still update the non-gateway device."""
    from modules.rogue_device import DeviceInfo

    GW_IP      = "192.168.1.1"
    CLIENT_IP  = "192.168.1.71"
    SHARED_MAC = "aa:bb:cc:dd:ee:01"  # proxy-ARP: both IPs report the gateway MAC

    table = _make_table([
        (GW_IP,     "RouterHostname", SHARED_MAC),
        (CLIENT_IP, "PS4-Enriched",   SHARED_MAC),
    ])
    d_gw     = DeviceInfo(ip=GW_IP,     mac=SHARED_MAC, hostname="RouterHostname")
    d_client = DeviceInfo(ip=CLIENT_IP, mac=SHARED_MAC, hostname="")

    stub = _make_stub(
        table,
        m1_result={"devices": [d_gw, d_client]},
        net_info={"gateway": GW_IP, "gateway_mac": SHARED_MAC},
    )
    stub._apply_mesh_enrichment()

    assert d_gw.hostname == "RouterHostname", \
        "Gateway DeviceInfo.hostname must not be overwritten even when MAC is shared"
    assert d_client.hostname == "PS4-Enriched", \
        "Non-gateway DeviceInfo.hostname must be updated from its table cell by IP"

    _cleanup(table)


def test_ip_keyed_sync_no_gateway_info_updates_all():
    """When _net_info has no gateway, the sync loop updates all DeviceInfo objects."""
    from modules.rogue_device import DeviceInfo

    table = _make_table([
        ("10.0.0.1",  "DeviceA", "aa:00:00:00:00:01"),
        ("10.0.0.2",  "DeviceB", "aa:00:00:00:00:02"),
    ])
    d_a = DeviceInfo(ip="10.0.0.1", mac="aa:00:00:00:00:01", hostname="")
    d_b = DeviceInfo(ip="10.0.0.2", mac="aa:00:00:00:00:02", hostname="")

    stub = _make_stub(
        table,
        m1_result={"devices": [d_a, d_b]},
        net_info={},  # no gateway key
    )
    stub._apply_mesh_enrichment()

    assert d_a.hostname == "DeviceA"
    assert d_b.hostname == "DeviceB"

    _cleanup(table)

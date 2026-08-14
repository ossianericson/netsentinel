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
    from modules.device_classification import ClaimTracker
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
    stub._classification_claims = ClaimTracker()
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


def test_plugin_enrichment_handles_unresolved_gateway_mac(monkeypatch):
    """RULE-NET1 regression: get_network_info() legitimately sets gateway_mac to
    None when ARP resolution hasn't happened yet (VPN, flushed cache, fresh
    boot) -- _net_info is present but _net_info["gateway_mac"] is None, not
    absent. This crashed a live wild-chaos monkey run (2026-07-21):
    AttributeError: 'NoneType' object has no attribute 'replace' inside
    _norm_mac(self._net_info.get("gateway_mac", "")) at scan_enrichment.py:168,
    3 seconds before the process died with STATUS_STACK_BUFFER_OVERRUN.
    """
    from modules.deco_client import _norm_mac
    from ui.scan_enrichment import ScanEnrichmentMixin

    monkeypatch.setattr(
        "modules.network_infrastructure.hw_state.update_router",
        lambda *a, **kw: None,
    )

    CLIENT_MAC = "11:22:33:44:55:03"

    class _Stub(ScanEnrichmentMixin):
        def __init__(self):
            self._net_info = {"gateway": "192.168.1.1", "gateway_mac": None}
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
            {"mac": CLIENT_MAC, "hostname": "DeviceC", "ip": "192.168.1.4"},
        ],
        "_path": "router3",
    })

    enrichment = stub._plugin_enrichments["router3"]
    assert _norm_mac(CLIENT_MAC) in enrichment


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


# ---------------------------------------------------------------------------
# Bug #2 — _mesh_enrichment must use normalised (lowercase) MAC keys
# ---------------------------------------------------------------------------

class TestMeshMacNormalization:
    """_mesh_enrichment must store normalised lowercase MAC keys.

    Bug: _on_mesh_result builds the dict as {c.mac: c for c in clients}.
    If c.mac is uppercase (raw Deco API MAC), the lookup in _apply_mesh_enrichment
    calls _norm_mac() on the scan-table MAC (→ lowercase) and never finds a match.
    Result: any_matched stays False → Node and Band columns remain hidden.

    Fix: normalise key at construction time:
        {_norm_mac(c.mac): c for c in clients}
    """

    def test_on_mesh_result_stores_normalised_mac_key(self):
        """After _on_mesh_result, _mesh_enrichment must have a lowercase MAC key.

        Fails before fix: {c.mac: c for c in clients} stores "AA:BB:CC:DD:EE:FF".
        Passes after fix: {_norm_mac(c.mac): c for c in clients} stores "aa:bb:cc:dd:ee:ff".
        """
        from unittest.mock import MagicMock
        from modules.deco_client import MeshClient
        from ui.scan_enrichment import ScanEnrichmentMixin

        class _S(ScanEnrichmentMixin):
            def _update_m4_deco_chips(self):
                pass  # not under test

        raw_mac = "AA:BB:CC:DD:EE:FF"
        client = MeshClient(
            name="device", mac=raw_mac, ip="192.168.1.10",
            unit_mac="aa:bb:cc:00:11:22", unit_name="Main", band="2.4G",
        )

        stub = _S()
        stub._m1_result = {}
        stub._m1_table = QTableWidget(0, 8)
        stub._mesh_enrichment = {}
        stub._plugin_enrichments = {}
        stub._plugin_nodes = {}
        stub._m1_group_by_node = False
        stub._m1_status = MagicMock()  # setText() called by _on_mesh_result
        stub._store = None
        stub._last_mesh_log_ts = 0

        stub._on_mesh_result({"clients": [client], "provider": "deco", "units": []})

        assert raw_mac not in stub._mesh_enrichment, (
            "_mesh_enrichment must not use raw uppercase MAC as key; "
            "this causes a lookup miss in _apply_mesh_enrichment"
        )
        assert raw_mac.lower() in stub._mesh_enrichment, (
            f"_mesh_enrichment must use normalised lowercase key '{raw_mac.lower()}' "
            f"after _on_mesh_result; got keys: {list(stub._mesh_enrichment.keys())}"
        )

        stub._m1_table.deleteLater()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()

    def test_node_band_populated_when_mesh_mac_is_uppercase(self):
        """Node (col 6) and Band (col 7) must be populated for an uppercase MeshClient MAC.

        Simulates a MeshClient with an uppercase MAC (as returned by a Deco router
        before normalisation) and verifies that the Devices table row gets the Node and
        Band cells filled in after _on_mesh_result + _apply_mesh_enrichment.

        Fails before fix: {c.mac: c} stores "AA:BB:CC:DD:EE:FF" but the lookup
        _norm_mac(scan_mac) = "aa:bb:cc:dd:ee:ff" → miss → col 6 empty.
        Passes after fix: key is normalised → lookup hits → col 6 = "Living Room".
        """
        from unittest.mock import MagicMock
        from modules.deco_client import MeshClient

        scan_mac = "AA:BB:CC:DD:EE:FF"
        table = _make_table([("192.168.1.10", "phone", scan_mac)])

        client = MeshClient(
            name="iPhone", mac=scan_mac, ip="192.168.1.10",
            unit_mac="aa:bb:cc:00:11:22", unit_name="Living Room", band="5G",
        )
        m1_result = {"devices": [
            {"mac": scan_mac, "ip": "192.168.1.10", "hostname": "",
             "vendor": "Apple Inc.", "risk_level": "CLEAN", "device_type": "Smartphone"},
        ]}
        stub = _make_stub(table, m1_result, {})
        stub._m1_status = MagicMock()
        stub._store = None
        stub._last_mesh_log_ts = 0

        stub._on_mesh_result({"clients": [client], "provider": "deco", "units": []})

        node_item = table.item(0, 6)
        node_text = node_item.text() if node_item else ""
        assert node_text == "Living Room", (
            f"Col 6 (Node) must be 'Living Room' after enrichment with uppercase MeshClient MAC; "
            f"got '{node_text}' — indicates _mesh_enrichment key='{scan_mac}' (raw) "
            f"does not match _norm_mac(scan_mac)='aa:bb:cc:dd:ee:ff' (lookup)"
        )

        band_item = table.item(0, 7)
        band_text = band_item.text() if band_item else ""
        assert band_text == "5G", (
            f"Col 7 (Band) must be '5G'; got '{band_text}'"
        )

        _cleanup(table)


# ---------------------------------------------------------------------------
# Synthesized mesh/plugin-only rows — OUI vendor lookup + display-only count
# ---------------------------------------------------------------------------

class TestSynthesizedRowEnrichment:
    """A device behind proxy-ARP is deliberately skipped by rogue_device.scan()
    (its real MAC is unknowable from ARP — the router answers on its behalf), so
    the mesh/hardware plugin is the ONLY source of that MAC. The synthesized row
    built for it used to hardcode Vendor="" and "Wireless Client", discarding a
    perfectly good MAC that the offline OUI registry can resolve — which is why
    the Devices page showed an empty Vendor column on every plugin-supplied row.

    The row count shown in the header / TOTAL NODES tile is computed from the raw
    ARP result before these rows exist, so it must be adjusted by the synthesized
    count — deliberately WITHOUT writing them into _m1_result["devices"], which is
    ARP-truth consumed by ~40 downstream call sites (ping targets, port-scan target
    lists, exports).
    """

    # Real registry OUIs — see modules/mac_registry.py
    PI_MAC = "b8:27:eb:11:22:33"      # -> Raspberry Pi / Single Board Computer
    # 98:5f:d3 is Microsoft's real Xbox Series X/S OUI. This fixture used to say
    # d8:3a:dd, which IEEE assigns to Raspberry Pi Trading Ltd — the registry
    # carried it inside its _XBOX block, so the test asserted the bug rather
    # than the behaviour, and passed green while a Pi rendered as an Xbox.
    XBOX_MAC = "98:5f:d3:00:00:01"    # -> Microsoft / Games Console
    UNKNOWN_MAC = "ac:63:be:00:00:01"  # -> not in the registry

    def _stub_with_kpi(self, table, m1_result, plugin_enrichments=None):
        stub = _make_stub(
            table,
            m1_result=m1_result,
            net_info={"gateway": "192.168.1.1", "gateway_mac": "aa:bb:cc:dd:ee:01"},
            plugin_enrichments=plugin_enrichments,
        )
        stub._kpi_calls = []
        stub._status_text = []

        class _Status:
            def __init__(self, sink):
                self._sink = sink

            def setText(self, txt):
                self._sink.append(txt)

        stub._m1_status = _Status(stub._status_text)

        def _fake_kpi(data, extra_count=0):
            stub._kpi_calls.append((len(data.get("devices", [])), extra_count))

        stub._update_kpi_tiles = _fake_kpi
        return stub

    def _row_for_mac(self, table, mac):
        from modules.deco_client import _norm_mac
        for r in range(table.rowCount()):
            item = table.item(r, 2)
            if item and _norm_mac(item.text()) == _norm_mac(mac):
                return r
        return None

    def test_plugin_only_row_gets_vendor_and_device_type_from_oui(self):
        """The reported bug: every plugin-supplied row showed a blank Vendor cell."""
        from modules.deco_client import _norm_mac

        table = _make_table([])
        plugin_enrichments = {
            "router": {
                _norm_mac(self.PI_MAC): {
                    "mac": self.PI_MAC, "hostname": "pi-hole",
                    "ip": "192.168.1.77", "band": "Wired", "unit": "Main",
                },
            },
        }
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0},
                                   plugin_enrichments)
        stub._apply_mesh_enrichment()

        row = self._row_for_mac(table, self.PI_MAC)
        assert row is not None, "plugin-only client was not synthesized into the table"

        vendor = table.item(row, 3)
        assert vendor is not None and vendor.text() == "Raspberry Pi", (
            "Vendor cell must be filled from the offline OUI registry, got "
            f"{vendor.text() if vendor else None!r}"
        )
        dtype = table.item(row, 5)
        assert dtype is not None and dtype.text() == "Single Board Computer", (
            "Device Type must come from the OUI registry, not the hardcoded "
            f"'Wireless Client' fallback; got {dtype.text() if dtype else None!r}"
        )

    def test_unknown_oui_keeps_wireless_client_fallback(self):
        """An OUI the registry doesn't know must degrade to today's behaviour."""
        from modules.deco_client import _norm_mac

        table = _make_table([])
        plugin_enrichments = {
            "router": {
                _norm_mac(self.UNKNOWN_MAC): {
                    "mac": self.UNKNOWN_MAC, "hostname": "mystery-box",
                    "ip": "192.168.1.88", "band": "5 GHz", "unit": "Satellite",
                },
            },
        }
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0},
                                   plugin_enrichments)
        stub._apply_mesh_enrichment()

        row = self._row_for_mac(table, self.UNKNOWN_MAC)
        assert row is not None
        vendor = table.item(row, 3)
        assert (vendor.text() if vendor else "") == ""
        dtype = table.item(row, 5)
        assert dtype is not None and dtype.text() == "Wireless Client"

    def test_mesh_only_row_gets_vendor_from_oui(self):
        """Same fix must apply to the native mesh synthesis block, not just plugins."""
        from modules.deco_client import MeshClient, _norm_mac

        table = _make_table([])
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0})
        stub._mesh_enrichment = {
            _norm_mac(self.XBOX_MAC): MeshClient(
                name="Xbox", mac=self.XBOX_MAC, ip="192.168.1.60",
                unit_mac="aa:bb:cc:dd:ee:01", unit_name="Living Room", band="5G",
            ),
        }
        stub._apply_mesh_enrichment()

        row = self._row_for_mac(table, self.XBOX_MAC)
        assert row is not None, "mesh-only client was not synthesized into the table"
        vendor = table.item(row, 3)
        assert vendor is not None and vendor.text() == "Microsoft"
        dtype = table.item(row, 5)
        assert dtype is not None and dtype.text() == "Games Console"

    def test_synthesized_rows_counted_without_polluting_m1_result(self):
        """TOTAL NODES / header must include synthesized rows, but _m1_result must
        stay ARP-truth — a synthesized IP can be the literal '—' placeholder, which
        would be fed to the availability worker as a ping target if appended."""
        from modules.deco_client import _norm_mac

        table = _make_table([])
        m1_result = {"devices": [], "total_count": 0, "high_risk_count": 0}
        plugin_enrichments = {
            "router": {
                _norm_mac(self.PI_MAC): {
                    "mac": self.PI_MAC, "hostname": "pi-hole",
                    "ip": "192.168.1.77", "band": "Wired", "unit": "Main",
                },
                _norm_mac(self.XBOX_MAC): {
                    "mac": self.XBOX_MAC, "hostname": "Xbox",
                    "ip": "192.168.1.60", "band": "5 GHz", "unit": "Main",
                },
            },
        }
        stub = self._stub_with_kpi(table, m1_result, plugin_enrichments)
        stub._apply_mesh_enrichment()

        assert table.rowCount() == 2
        assert m1_result["devices"] == [], (
            "_m1_result['devices'] must stay ARP-truth — synthesized rows must not "
            "leak into the list consumed by ping targets / exports / port scans"
        )
        assert m1_result["total_count"] == 0, "_m1_result must not be mutated"
        assert stub._kpi_calls, "_update_kpi_tiles was never called after synthesis"
        assert stub._kpi_calls[-1][1] == 2, (
            f"KPI tile must be told about 2 synthesized rows, got {stub._kpi_calls[-1]}"
        )
        assert any("2 devices" in t for t in stub._status_text), (
            f"header must report the 2 visible devices, got {stub._status_text!r}"
        )

    def test_repeat_enrichment_does_not_double_count(self):
        """_apply_mesh_enrichment runs on every plugin poll — the count must be
        idempotent, not grow by one row-set per call."""
        from modules.deco_client import _norm_mac

        table = _make_table([])
        plugin_enrichments = {
            "router": {
                _norm_mac(self.PI_MAC): {
                    "mac": self.PI_MAC, "hostname": "pi-hole",
                    "ip": "192.168.1.77", "band": "Wired", "unit": "Main",
                },
            },
        }
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0},
                                   plugin_enrichments)
        stub._apply_mesh_enrichment()
        stub._apply_mesh_enrichment()
        stub._apply_mesh_enrichment()

        assert table.rowCount() == 1, "row was synthesized more than once"
        assert stub._kpi_calls[-1][1] == 1, (
            f"synthesized count must stay 1 across repeat calls, got {stub._kpi_calls}"
        )


# ---------------------------------------------------------------------------
# Bug #3 — blank cells after second scan when sort indicator is active
# ---------------------------------------------------------------------------

class TestM1TableSortingRegression:
    """Regression for Bug #3: blank cells in Discovered Devices after re-scan.

    Root cause: setSortingEnabled(True) with an active sort indicator causes each
    setItem() to immediately re-sort the newly inserted row to its sorted position.
    _add_row uses a static `row` index (saved before insertRow), so items for
    columns after the sort column land in whatever row happened to be at that index
    after the re-sort — i.e., the WRONG row — leaving the intended row blank.

    Fix: scan_wiring._on_m1_result calls setSortingEnabled(False) before
    setRowCount(0) + _add_row loop, then setSortingEnabled(True) after all rows
    are inserted.  The sortByColumn() call at the end applies the persisted sort
    order cleanly to fully-populated rows.
    """

    def test_all_columns_populated_when_sort_active_before_rescan(self):
        """All 9 columns must have the correct value after inserting rows with the
        fix (sorting disabled during insertion, active sort indicator present)."""
        from PyQt6.QtCore import Qt

        from ui.tabs_helpers import _add_row

        t = QTableWidget(0, 9)
        t.setHorizontalHeaderLabels(
            ["IP", "Hostname", "MAC", "Vendor", "Risk", "Type", "Node", "Band", "Verdict"]
        )
        t.setSortingEnabled(True)

        # First scan: populate two rows and apply a sort (sets the sort indicator)
        t.setSortingEnabled(False)
        t.setRowCount(0)
        _add_row(t, ["192.168.1.200", "host-z", "bb:bb:bb:bb:bb:bb",
                     "Vendor Z", "CLEAN", "Laptop", "", "", "safe"], "CLEAN")
        _add_row(t, ["192.168.1.100", "host-a", "aa:aa:aa:aa:aa:aa",
                     "Vendor A", "LOW", "Phone", "", "", "ok"], "LOW")
        t.setSortingEnabled(True)
        t.sortByColumn(0, Qt.SortOrder.AscendingOrder)  # sets active sort indicator

        # Second scan: disable sorting BEFORE clear+insert (the fix in scan_wiring.py)
        t.setSortingEnabled(False)
        t.setRowCount(0)
        row_data = [
            "192.168.1.55", "my-host", "cc:cc:cc:cc:cc:cc",
            "Apple Inc.", "CLEAN", "iPhone", "", "", "ok",
        ]
        _add_row(t, row_data, "CLEAN")
        t.setSortingEnabled(True)
        t.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        assert t.rowCount() == 1, "Row was not inserted"
        for col, expected in enumerate(row_data):
            item = t.item(0, col)
            assert item is not None, (
                f"Col {col} is None — row was displaced by active sort during insert "
                f"(sorting must be disabled before setRowCount(0) + _add_row)"
            )
            assert item.text() == str(expected), (
                f"Col {col}: expected '{expected}', got '{item.text()}'"
            )

        t.deleteLater()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


# ---------------------------------------------------------------------------
# Phase 2b — Full Device Discovery persists response_ms via MetricStore.record_rtt
# ---------------------------------------------------------------------------

def test_on_discovery_result_persists_positive_rtt(monkeypatch):
    """_on_discovery_result must call store.record_rtt(ip, response_ms) for reachable devices."""
    from unittest.mock import MagicMock
    from ui.scan_enrichment import ScanEnrichmentMixin
    from modules.combined_discovery import DiscoveredDevice, DiscoveryResult

    class _Stub(ScanEnrichmentMixin):
        pass

    stub = _Stub()
    stub._recon_disc_table = QTableWidget(0, 5)
    stub._disc_status = MagicMock()
    stub._nav_set_scan_state = MagicMock()
    stub._store = MagicMock()

    res = DiscoveryResult(devices=[
        DiscoveredDevice(ip="192.168.1.30", response_ms=15.0, discovery_methods=["icmp-ping"]),
        DiscoveredDevice(ip="192.168.1.31", response_ms=0.0, discovery_methods=["arp-sweep"]),
    ])

    stub._on_discovery_result(res)

    stub._store.record_rtt.assert_called_once_with("192.168.1.30", 15.0)
    _cleanup(stub._recon_disc_table)


def test_on_cred_result_not_testable_sets_not_testable_state_and_excludes_from_cred_access():
    """Sprint 5b (D): a connection-refused Login Test must set 'not_testable'
    (not 'fresh'), and must NOT be added to _cred_access_hosts — the previous
    'not res.error' check treated any error-free result as a confirmed working
    login, which a not_testable result (empty .error by design) would have
    wrongly satisfied."""
    from unittest.mock import MagicMock
    from ui.scan_enrichment import ScanEnrichmentMixin
    from modules.credentialed_scan import CredScanResult

    class _Stub(ScanEnrichmentMixin):
        pass

    stub = _Stub()
    stub._cred_verdict = MagicMock()
    stub._cred_status = MagicMock()
    stub._nav_set_scan_state = MagicMock()
    stub._cred_access_hosts: set = set()
    stub._recon_cred_info_table = QTableWidget(0, 2)
    stub._recon_cred_sessions_table = QTableWidget(0, 1)
    stub._recon_cred_sw_table = QTableWidget(0, 3)
    stub._recon_cred_svc_table = QTableWidget(0, 3)
    stub._recon_cred_user_table = QTableWidget(0, 4)

    res = CredScanResult(
        host="10.0.0.9",
        not_testable=True, not_testable_reason="Could not establish an SSH connection",
    )
    stub._on_cred_result(res)

    from ui.nav.labels import NavLabel as L
    assert stub._nav_set_scan_state.call_args.args == (L.LOGIN_TEST, "not_testable")
    assert "10.0.0.9" not in stub._cred_access_hosts

    # Live-walk regression: the verdict banner's color previously only
    # checked risk_flags (RED if any, else GREEN) -- a not_testable result
    # has zero flags by definition, so it rendered in a falsely-reassuring
    # GREEN ("Could not test..." text in a success-colored banner). Must use
    # VIOLET, matching the Device Risk Score not_testable convention.
    from ui import styles as _s
    style_arg = stub._cred_verdict.setStyleSheet.call_args.args[0]
    assert _s.VIOLET in style_arg
    assert _s.GREEN not in style_arg

    for t in (stub._recon_cred_info_table, stub._recon_cred_sessions_table,
              stub._recon_cred_sw_table, stub._recon_cred_svc_table, stub._recon_cred_user_table):
        _cleanup(t)


def test_on_discovery_result_not_testable_sets_not_testable_state():
    """Sprint 5b (E): zero devices from every discovery method must set
    'not_testable' (not 'fresh'), mirroring the other 5b/5a scan handlers."""
    from unittest.mock import MagicMock
    from ui.scan_enrichment import ScanEnrichmentMixin
    from modules.combined_discovery import DiscoveryResult

    class _Stub(ScanEnrichmentMixin):
        pass

    stub = _Stub()
    stub._recon_disc_table = QTableWidget(0, 5)
    stub._disc_status = MagicMock()
    stub._nav_set_scan_state = MagicMock()
    stub._store = None

    res = DiscoveryResult(
        devices=[], cidr="192.168.1.0/24",
        not_testable=True, not_testable_reason="No devices found by any method",
    )
    stub._on_discovery_result(res)

    from ui.nav.labels import NavLabel as L
    stub._nav_set_scan_state.assert_called_once_with(
        L.FULL_DEVICE_DISCOVERY, "not_testable",
        ts=stub._nav_set_scan_state.call_args.kwargs["ts"],
        error="No devices found by any method",
    )
    _cleanup(stub._recon_disc_table)


# ---------------------------------------------------------------------------
# Phase 4 C2 — the mesh snapshot write must not be gated on Monitor logging
#
# `mesh_signal_log` was 0 rows in every real database because the only
# record_mesh_snapshot() call sat inside `if logging/mesh_enabled`, an opt-in
# the user never turned on. MESH_DEGRADED history and acceptance criterion 6
# ("mesh_signal_log is non-empty after a mesh poll") both depend on the write
# happening on every poll. The toggle keeps gating the live log-hub entry.
# ---------------------------------------------------------------------------

class _FakeUnit:
    """Stand-in for a mesh node as returned by the Deco/plugin providers."""

    def __init__(self, name="Node", online=True, rssi=None):
        self.name = name
        self.online = online
        self.rssi = rssi


def _make_mesh_stub(monkeypatch, units, store=None, log_hub=None):
    """Return a stub wired for _on_mesh_result plus the recorded snapshot calls."""
    from unittest.mock import MagicMock
    from ui.scan_enrichment import ScanEnrichmentMixin

    class _S(ScanEnrichmentMixin):
        def _update_m4_deco_chips(self):
            pass  # WiFi page chips — not under test

    calls: list = []
    monkeypatch.setattr(
        "ui.scan_enrichment.record_mesh_snapshot",
        lambda store, **kw: calls.append(kw),
    )

    stub = _S()
    stub._m1_result = {}
    stub._m1_table = QTableWidget(0, 8)
    stub._mesh_enrichment = {}
    stub._plugin_enrichments = {}
    stub._plugin_nodes = {}
    stub._m1_group_by_node = False
    stub._m1_status = MagicMock()
    stub._store = store if store is not None else MagicMock()
    stub._last_mesh_log_ts = 0.0
    stub._alert_engine = None            # alert path covered by test_alert_engine_v6_sprint1
    if log_hub is not None:
        stub._log_hub_page = log_hub
    stub._units = units
    return stub, calls


def _mesh_data(units):
    return {"clients": [], "provider": "deco", "units": units}


def test_mesh_snapshot_written_when_monitor_logging_is_off(monkeypatch):
    """With logging/mesh_enabled unset (the default), the snapshot must still land.

    Fails before fix: record_mesh_snapshot() is inside the toggle's branch, so
    calls == [] and mesh_signal_log stays empty forever.
    """
    from unittest.mock import MagicMock

    log_hub = MagicMock()
    units = [_FakeUnit("Main", online=True, rssi=-50), _FakeUnit("Attic", online=False)]
    stub, calls = _make_mesh_stub(monkeypatch, units, log_hub=log_hub)

    stub._on_mesh_result(_mesh_data(units))

    assert len(calls) == 1, (
        "record_mesh_snapshot() must be called on every mesh poll regardless of "
        f"the logging/mesh_enabled toggle; got {len(calls)} call(s)"
    )
    assert calls[0]["unit_count"] == 2
    assert calls[0]["online_count"] == 1
    assert calls[0]["worst_unit"] == "Main"
    assert calls[0]["worst_rssi"] == -50

    log_hub.add_mesh_entry.assert_not_called()   # the toggle still gates the live entry

    _cleanup(stub._m1_table)


def test_mesh_live_log_entry_still_gated_on_the_toggle(monkeypatch):
    """logging/mesh_enabled ON must still drive add_mesh_entry — and the snapshot."""
    from unittest.mock import MagicMock
    from PyQt6.QtCore import QSettings

    QSettings().setValue("logging/mesh_enabled", True)
    log_hub = MagicMock()
    units = [_FakeUnit("Main", online=True, rssi=-45)]
    stub, calls = _make_mesh_stub(monkeypatch, units, log_hub=log_hub)

    stub._on_mesh_result(_mesh_data(units))

    log_hub.add_mesh_entry.assert_called_once()
    assert len(calls) == 1

    _cleanup(stub._m1_table)


def test_mesh_snapshot_throttle_survives_the_hoist(monkeypatch):
    """A second poll inside the interval must not write a second row."""
    units = [_FakeUnit("Main", online=True, rssi=-45)]
    stub, calls = _make_mesh_stub(monkeypatch, units)

    stub._on_mesh_result(_mesh_data(units))
    stub._on_mesh_result(_mesh_data(units))

    assert len(calls) == 1, (
        "the 5-minute _last_mesh_log_ts throttle must still apply after the "
        f"write is hoisted out of the logging branch; got {len(calls)} writes"
    )

    _cleanup(stub._m1_table)


def test_mesh_snapshot_skipped_when_no_units_reported(monkeypatch):
    """A provider that returns no units says nothing about mesh health — no row."""
    stub, calls = _make_mesh_stub(monkeypatch, [])

    stub._on_mesh_result(_mesh_data([]))

    assert calls == [], "a poll with zero units must not write a placeholder row"

    _cleanup(stub._m1_table)


# ---------------------------------------------------------------------------
# Phase 4 C2 follow-up — the snapshot must be written from the path the real
# Deco plugin actually takes.
#
# _on_mesh_result() carries both evaluate_mesh_checks() and
# record_mesh_snapshot(), but nothing in production calls it — no .connect(),
# no worker, no dynamic dispatch; only tests. A real Deco poll lands in
# _on_hardware_plugin_result(), whose router/mesh branch enriched the Devices
# table inline and never wrote a snapshot. So mesh_signal_log stayed empty
# regardless of C2's toggle hoist, and acceptance criterion 6 was unreachable.
# ---------------------------------------------------------------------------


def _make_plugin_mesh_stub(monkeypatch, store=None):
    """Stub wired for _on_hardware_plugin_result plus recorded snapshot calls."""
    from unittest.mock import MagicMock
    from ui.scan_enrichment import ScanEnrichmentMixin

    class _S(ScanEnrichmentMixin):
        def _update_m4_deco_chips(self):
            pass  # WiFi page chips — not under test

        def _refresh_hardware_badge(self):
            pass  # lives on _MonitorStateMixin — not under test

        def _on_modem_signal(self, data):
            pass  # modem page routing — not under test

    calls: list = []
    monkeypatch.setattr(
        "ui.scan_enrichment.record_mesh_snapshot",
        lambda store, **kw: calls.append(kw),
    )
    monkeypatch.setattr(
        "modules.network_infrastructure.hw_state.update_router",
        lambda *a, **kw: None,
    )

    stub = _S()
    stub._m1_result = {}
    stub._m1_table = QTableWidget(0, 8)
    stub._mesh_enrichment = {}
    stub._plugin_enrichments = {}
    stub._plugin_nodes = {}
    stub._m1_group_by_node = False
    stub._m1_status = MagicMock()
    stub._net_info = {}
    stub._store = store if store is not None else MagicMock()
    stub._last_mesh_log_ts = 0.0
    stub._alert_engine = None  # alert path covered by test_alert_engine_v6_sprint1
    return stub, calls


# Shaped exactly like plugins/deco_plugin.py::get_status() — note the nodes
# carry no per-node online flag or RSSI, and HARDWARE_TYPE is "router".
_DECO_NODES = [
    {"name": "Main",  "mac": "aa:bb:cc:dd:ee:01", "ip": "192.168.68.1", "role": "master"},
    {"name": "Attic", "mac": "aa:bb:cc:dd:ee:02", "ip": "192.168.68.2", "role": "slave"},
]


def _deco_plugin_data(nodes, hw_type="router"):
    return {
        "info":    {"name": "TP-Link Deco XE75", "type": hw_type, "ip": "192.168.68.1"},
        "status":  {"extra": {"nodes": nodes}} if nodes else {"extra": {}},
        "clients": [],
        "_instance_id": "a9d9e01ef03b2e9f",
        "_path":        "deco_plugin.py",
    }


def test_mesh_snapshot_written_from_the_real_plugin_poll_path(monkeypatch):
    """A real Deco poll must write one mesh_signal_log row.

    Fails before fix: the router/mesh branch of _on_hardware_plugin_result
    enriches the Devices table and returns without ever calling
    record_mesh_snapshot(), so calls == [] and mesh_signal_log stays empty no
    matter how often the mesh is polled.
    """
    stub, calls = _make_plugin_mesh_stub(monkeypatch)

    stub._on_hardware_plugin_result(_deco_plugin_data(_DECO_NODES))

    assert len(calls) == 1, (
        "a mesh/router plugin poll reporting nodes must write exactly one "
        f"mesh_signal_log row; got {len(calls)}"
    )
    assert calls[0]["unit_count"] == 2
    # Plugin node dicts carry no per-node online flag, so every reported node
    # counts as online. Recorded truthfully rather than inferred.
    assert calls[0]["online_count"] == 2

    _cleanup(stub._m1_table)


def test_plugin_mesh_snapshot_respects_the_throttle(monkeypatch):
    """A second poll inside the interval must not write a second row."""
    stub, calls = _make_plugin_mesh_stub(monkeypatch)

    stub._on_hardware_plugin_result(_deco_plugin_data(_DECO_NODES))
    stub._on_hardware_plugin_result(_deco_plugin_data(_DECO_NODES))

    assert len(calls) == 1, (
        f"the _last_mesh_log_ts throttle must apply here too; got {len(calls)} writes"
    )

    _cleanup(stub._m1_table)


def test_router_reporting_no_nodes_writes_no_mesh_snapshot(monkeypatch):
    """A plain single-AP router says nothing about mesh health — no row.

    The branch synthesizes a placeholder node for topology when a router
    returns clients but no nodes; that synthetic entry must not reach
    mesh_signal_log as if it were a real mesh reading.
    """
    stub, calls = _make_plugin_mesh_stub(monkeypatch)

    stub._on_hardware_plugin_result(_deco_plugin_data([]))

    assert calls == [], "a router with no reported nodes must not write a row"

    _cleanup(stub._m1_table)


def test_modem_plugin_writes_no_mesh_snapshot(monkeypatch):
    """Modem plugins return early — they have no mesh to report on."""
    stub, calls = _make_plugin_mesh_stub(monkeypatch)

    stub._on_hardware_plugin_result(_deco_plugin_data(_DECO_NODES, hw_type="modem"))

    assert calls == [], "a modem poll must never write a mesh_signal_log row"

    _cleanup(stub._m1_table)


# ---------------------------------------------------------------------------
# Device Identity Program Phase 3 — hostname-sync re-classify pass routes
# through the arbiter (ui/scan_enrichment.py::_apply_mesh_enrichment, writer 2
# in the program plan's root-cause table)
# ---------------------------------------------------------------------------

def test_hostname_sync_reclassify_routes_through_arbiter_and_records_a_claim(monkeypatch):
    """A device still 'Unknown Device' whose hostname the sync step just
    filled in from the table gets a claim submitted to the tracker (so a
    later passive/DHCP claim correctly corroborates or conflicts against it)
    and an audit event, instead of an unconditional in-memory overwrite."""
    from unittest.mock import MagicMock

    ip, mac = "192.168.1.60", "aa:bb:cc:dd:ee:06"
    table = _make_table([(ip, "printer1", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    dev.vendor = "Lexmark"
    dev.hostname = ""
    dev.open_ports = [9100]
    dev.os_family = ""

    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    store = MagicMock()
    store.get_classification_override.return_value = None
    stub._store = store

    stub._apply_mesh_enrichment()

    assert dev.hostname == "printer1"  # sanity: the hostname sync step ran first
    assert dev.device_type != "Unknown Device"
    assert stub._classification_claims.claim_count(mac) == 1
    store.record_device_change_event.assert_called_once()
    call_args = store.record_device_change_event.call_args.args
    assert call_args[0] == mac
    assert call_args[1] == "class_changed"
    assert call_args[2] == "Unknown Device"
    assert call_args[3] == dev.device_type

    # Device Identity Program Phase 4: the arbitrated result must also reach
    # known_device immediately, not live only on the in-memory DeviceInfo.
    # Routed through modules.scan_persistence.upsert_known_device() (ARCH
    # RULE 1 — the UI layer never writes to MetricStore directly), which
    # calls store.upsert_known_device(mac, **kwargs) with mac positional.
    store.upsert_known_device.assert_called_once()
    upsert_args, upsert_kwargs = store.upsert_known_device.call_args
    assert upsert_args[0] == mac
    assert upsert_kwargs["device_type"] == dev.device_type
    assert upsert_kwargs["confidence"] > 0.0

    _cleanup(table)


def test_hostname_sync_reclassify_skips_an_already_classified_device():
    """Unchanged from the pre-arbiter behaviour: a device with a real type
    already is left alone by this pass."""
    ip, mac = "192.168.1.61", "aa:bb:cc:dd:ee:07"
    table = _make_table([(ip, "somehost", mac)])
    dev = _DevObj(ip, mac, device_type="Games Console")
    dev.vendor = ""
    dev.hostname = ""
    dev.open_ports = []
    dev.os_family = ""

    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    stub._apply_mesh_enrichment()

    assert dev.device_type == "Games Console"
    assert stub._classification_claims.claim_count(mac) == 0

    _cleanup(table)


# ---------------------------------------------------------------------------
# Device Identity Program Phase 2 — _on_passive_observation() matched by MAC
# ---------------------------------------------------------------------------

class _DevObj:
    """A minimal object-shaped device — mirrors modules.rogue_device.DeviceInfo
    closely enough to exercise the non-dict branch of _on_passive_observation."""

    def __init__(self, ip, mac, device_type=""):
        self.ip = ip
        self.mac = mac
        self.device_type = device_type
        self.discovery_methods = []


def _make_passive_obs(ip, mac="", device_hint="IP Camera", confidence="high", protocol="mdns"):
    from modules.passive_observer import PassiveObservation
    return PassiveObservation(
        ip=ip, mac=mac, protocol=protocol, service_type="_test._tcp",
        device_hint=device_hint, confidence=confidence,
    )


def test_passive_observation_matches_by_mac_not_ip_collision():
    """Two devices share one IP (the exact confound the baseline measured on
    7 addresses) — the observation must upgrade only the device whose own MAC
    matches obs.mac, never the other device merely because it shares the IP."""
    SHARED_IP = "192.168.1.50"
    TARGET_MAC = "aa:bb:cc:dd:ee:01"
    OTHER_MAC = "aa:bb:cc:dd:ee:02"

    table = _make_table([
        (SHARED_IP, "", OTHER_MAC),
        (SHARED_IP, "", TARGET_MAC),
    ])
    target = _DevObj(SHARED_IP, TARGET_MAC, device_type="Unknown Device")
    other = _DevObj(SHARED_IP, OTHER_MAC, device_type="Unknown Device")
    # `other` deliberately listed FIRST: matching by IP alone (the old
    # behaviour) would hit it before ever reaching `target`, upgrading the
    # wrong device. MAC-based matching must find `target` regardless of order.
    stub = _make_stub(table, {"devices": [other, target]}, net_info=None)

    obs = _make_passive_obs(SHARED_IP, mac=TARGET_MAC)
    stub._on_passive_observation(obs)

    assert target.device_type == "IP Camera"
    assert other.device_type == "Unknown Device", (
        "matching by IP alone would have upgraded whichever device the loop "
        "reached first, regardless of which one the observation was about"
    )

    _cleanup(table)


def test_passive_observation_falls_back_to_ip_when_mac_unresolved():
    """PassiveObservation.mac is '' until the ARP cache lookup resolves it —
    that must still match by IP, not silently drop the observation."""
    ip = "192.168.1.51"
    mac = "aa:bb:cc:dd:ee:03"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    obs = _make_passive_obs(ip, mac="")
    stub._on_passive_observation(obs)

    assert dev.device_type == "IP Camera"
    _cleanup(table)


def test_passive_observation_is_dropped_when_ip_ownership_is_ambiguous():
    """An IP claimed by more than one device in the list identifies nobody.

    Measured on the reference network: 7 addresses carry several MACs, and the
    live ARP cache disagreed with known_device.ip on 10 of the 15 comparable
    addresses -- DHCP had rotated the pool one slot, so every "first row holding
    this IP" answer was a different device than the one that sent the packet.
    Same principle v2.2.5 applied to label_for_host(): naming the wrong device
    is worse than naming none.
    """
    SHARED_IP = "192.168.1.60"
    table = _make_table([
        (SHARED_IP, "", "aa:bb:cc:dd:ee:10"),
        (SHARED_IP, "", "aa:bb:cc:dd:ee:11"),
    ])
    first = _DevObj(SHARED_IP, "aa:bb:cc:dd:ee:10", device_type="Games Console")
    second = _DevObj(SHARED_IP, "aa:bb:cc:dd:ee:11", device_type="Smart TV")
    stub = _make_stub(table, {"devices": [first, second]}, net_info=None)

    obs = _make_passive_obs(SHARED_IP, mac="")   # ARP could not resolve it
    stub._on_passive_observation(obs)

    assert first.device_type == "Games Console", (
        "the observation was attributed to whichever row the loop reached "
        "first, which on a rotated DHCP pool is a different device entirely"
    )
    assert second.device_type == "Smart TV"

    _cleanup(table)


def test_passive_observation_is_not_attributed_to_an_offline_row():
    """`_merge_scan_with_persistent()`/`_restore_cached_scan()` append offline
    devices carrying their LAST-KNOWN IP. That address has since been leased to
    somebody else, so a live observation from it is never about the offline row
    -- this is how an LG webOS TV that was powered off became a Router / Gateway
    and then a Smart Speaker on the reference network."""
    ip = "192.168.1.61"
    table = _make_table([(ip, "LGwebOSTV-EAg4-1", "aa:bb:cc:dd:ee:12")])
    offline = {
        "ip": ip,
        "mac": "aa:bb:cc:dd:ee:12",
        "hostname": "LGwebOSTV-EAg4-1",
        "device_type": "Smart TV",
        "display_state": "stale",
    }
    stub = _make_stub(table, {"devices": [offline]}, net_info=None)

    obs = _make_passive_obs(ip, mac="", device_hint="Router / Gateway")
    stub._on_passive_observation(obs)

    assert offline["device_type"] == "Smart TV", (
        "a stale row's IP is a last-known value, not a claim on the address now"
    )

    _cleanup(table)


def test_passive_observation_still_matches_a_single_live_owner_by_ip():
    """The two guards above must not close the ordinary case: one online device,
    unambiguously holding the address, with no MAC resolved."""
    ip = "192.168.1.62"
    mac = "aa:bb:cc:dd:ee:13"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    stub._on_passive_observation(_make_passive_obs(ip, mac=""))

    assert dev.device_type == "IP Camera"
    _cleanup(table)


def test_passive_observation_with_a_resolved_mac_ignores_stale_ip_rows():
    """With the ARP-resolved MAC present, an observation reaches its real sender
    even when a stale row still claims the source IP."""
    ip = "192.168.1.63"
    sender_mac = "aa:bb:cc:dd:ee:14"
    stale_mac = "aa:bb:cc:dd:ee:15"
    table = _make_table([(ip, "", stale_mac), ("192.168.1.64", "", sender_mac)])
    stale = _DevObj(ip, stale_mac, device_type="Smart TV")
    sender = _DevObj("192.168.1.64", sender_mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [stale, sender]}, net_info=None)

    # obs.ip is the address the stale row still claims; obs.mac is the truth.
    obs = _make_passive_obs(ip, mac=sender_mac)
    stub._on_passive_observation(obs)

    assert sender.device_type == "IP Camera"
    assert stale.device_type == "Smart TV"
    _cleanup(table)


def test_dhcp_fingerprint_pass_rejects_multicast_mac():
    """The DHCP VCI fingerprint pass is already keyed by the device's own MAC
    (never IP) -- the Phase 2 gap here is only the non-device check, added
    alongside the passive-observation fix for the same reason."""
    from modules.dhcp_fingerprint import DhcpFingerprint, clear_cache, update_cache

    ip = "239.255.255.250"
    mcast_mac = "01:00:5e:7f:ff:fa"
    table = _make_table([(ip, "", mcast_mac)])
    dev = _DevObj(ip, mcast_mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    clear_cache()
    update_cache({mcast_mac: DhcpFingerprint(
        device_hint="IP Camera", confidence="high", evidence="VCI: test",
    )})
    try:
        stub._apply_dhcp_fingerprints()
    finally:
        clear_cache()

    assert dev.device_type == "Unknown Device"
    _cleanup(table)


def test_dhcp_fingerprint_pass_persists_the_arbitrated_result():
    """Device Identity Program Phase 4: same persistence requirement as the
    passive-observation writer, for the DHCP VCI fingerprint writer."""
    from unittest.mock import MagicMock
    from modules.dhcp_fingerprint import DhcpFingerprint, clear_cache, update_cache

    ip, mac = "192.168.1.55", "aa:bb:cc:dd:ee:09"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    store = MagicMock()
    store.get_classification_override.return_value = None
    stub._store = store

    clear_cache()
    update_cache({mac: DhcpFingerprint(
        device_hint="Windows PC", confidence="high", evidence="VCI: MSFT 5.0",
    )})
    try:
        stub._apply_dhcp_fingerprints()
    finally:
        clear_cache()

    assert dev.device_type == "Windows PC"
    store.upsert_known_device.assert_called_once()
    args, kwargs = store.upsert_known_device.call_args
    assert args[0] == mac
    assert kwargs["device_type"] == "Windows PC"
    assert kwargs["confidence"] > 0.0

    _cleanup(table)


def test_dhcp_fingerprint_pass_still_upgrades_a_real_device():
    """Sanity check for the identity gate added above: a normal device must
    still be upgraded exactly as before."""
    from modules.dhcp_fingerprint import DhcpFingerprint, clear_cache, update_cache

    ip = "192.168.1.52"
    mac = "aa:bb:cc:dd:ee:04"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    clear_cache()
    update_cache({mac: DhcpFingerprint(
        device_hint="IP Camera", confidence="high", evidence="VCI: test",
    )})
    try:
        stub._apply_dhcp_fingerprints()
    finally:
        clear_cache()

    assert dev.device_type == "IP Camera"
    _cleanup(table)


def test_passive_observation_does_not_flip_a_stronger_seeded_claim():
    """The Lexmark scenario from the baseline: a claim already on record for
    this device this scan (as the real scan-time classification would leave
    behind -- see ui/scan_wiring.py::_m1_seed_classification_claims) must not
    be knocked over by one weaker passive guess. This is the actual churn
    defect Phase 3 exists to close, exercised through the real
    _on_passive_observation() method rather than the arbiter in isolation."""
    from modules.device_classification import ClassificationClaim, ClaimTracker

    ip = "192.168.1.53"
    mac = "aa:bb:cc:dd:ee:05"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Print Server")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    stub._classification_claims = ClaimTracker()
    stub._classification_claims.add(mac, ClassificationClaim(
        device_type="Print Server", confidence=0.6, source="heuristic",
        evidence="vendor:lexmark, any-ports:[9100]",
    ))

    obs = _make_passive_obs(ip, mac=mac, device_hint="Streaming Stick", confidence="low")
    stub._on_passive_observation(obs)

    assert dev.device_type == "Print Server"
    _cleanup(table)


def test_passive_observation_persists_the_arbitrated_result():
    """Device Identity Program Phase 4: an upgrade must reach known_device
    immediately, not live only on the in-memory DeviceInfo until the next
    scan's classify_registry_first() call silently reverts it."""
    from unittest.mock import MagicMock

    ip, mac = "192.168.1.54", "aa:bb:cc:dd:ee:08"
    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    store = MagicMock()
    store.get_classification_override.return_value = None
    stub._store = store

    obs = _make_passive_obs(ip, mac=mac, device_hint="IP Camera", confidence="high")
    stub._on_passive_observation(obs)

    assert dev.device_type == "IP Camera"
    store.upsert_known_device.assert_called_once()
    args, kwargs = store.upsert_known_device.call_args
    assert args[0] == mac
    assert kwargs["device_type"] == "IP Camera"
    assert kwargs["confidence"] > 0.0

    _cleanup(table)


def test_passive_observation_rejects_multicast_mac():
    """An observation naming a multicast/group MAC is not a device at all
    (classify_identity() -> NOT_A_DEVICE) and must not classify anything,
    even if a scanned device happens to share its IP."""
    ip = "239.255.255.250"
    mcast_mac = "01:00:5e:7f:ff:fa"
    table = _make_table([(ip, "", mcast_mac)])
    dev = _DevObj(ip, mcast_mac, device_type="Unknown Device")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)

    obs = _make_passive_obs(ip, mac=mcast_mac)
    stub._on_passive_observation(obs)

    assert dev.device_type == "Unknown Device"
    _cleanup(table)


class TestSynthesizedRowVendorFromName(TestSynthesizedRowEnrichment):
    """A privacy-MAC mesh client has no OUI, but its mesh name identifies it.

    Live case: 6a:94:29:ec:8f:4d / "Chromecast-Audio-Vardagsrum" rendered with a
    blank Vendor cell. Its known_device.hostname is empty -- the name arrives
    from the Deco client list during mesh enrichment, long AFTER
    rogue_device._apply_resolution() has run -- so the vendor hint has to be
    applied here too, not only on the scan path.
    """

    CHROMECAST_MAC = "6a:94:29:ec:8f:4d"   # U/L bit set -> privacy MAC, no OUI

    def test_privacy_mac_mesh_row_gets_vendor_from_its_mesh_name(self):
        from modules.deco_client import MeshClient, _norm_mac

        table = _make_table([])
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0})
        stub._mesh_enrichment = {
            _norm_mac(self.CHROMECAST_MAC): MeshClient(
                name="Chromecast-Audio-Vardagsrum", mac=self.CHROMECAST_MAC,
                ip="192.168.68.51", unit_mac="aa:bb:cc:dd:ee:01",
                unit_name="Vardagsrum", band="5G",
            ),
        }
        stub._apply_mesh_enrichment()

        row = self._row_for_mac(table, self.CHROMECAST_MAC)
        assert row is not None, "mesh-only client was not synthesized into the table"
        vendor = table.item(row, 3)
        assert vendor is not None and vendor.text() == "Google", (
            "Vendor must fall back to the mesh name when the MAC carries no OUI; got "
            f"{vendor.text() if vendor else None!r}"
        )

    def test_oui_vendor_still_wins_over_the_mesh_name(self):
        """The name is weaker evidence and must only fill a genuine blank."""
        from modules.deco_client import MeshClient, _norm_mac

        table = _make_table([])
        stub = self._stub_with_kpi(table, {"devices": [], "total_count": 0})
        stub._mesh_enrichment = {
            _norm_mac(self.PI_MAC): MeshClient(
                name="chromecast-box", mac=self.PI_MAC, ip="192.168.68.67",
                unit_mac="aa:bb:cc:dd:ee:01", unit_name="Vardagsrum", band="Wired",
            ),
        }
        stub._apply_mesh_enrichment()

        row = self._row_for_mac(table, self.PI_MAC)
        vendor = table.item(row, 3)
        assert vendor is not None and vendor.text() == "Raspberry Pi"


# ---------------------------------------------------------------------------
# Capability announcements — recorded as capability, never as identity
# ---------------------------------------------------------------------------

def _make_capability_obs(ip, mac, service_type, capability, protocol="mdns"):
    """An observation shaped exactly as the parsers now produce for a
    media-capability service: a capability, and NO device_hint."""
    from modules.passive_observer import PassiveObservation
    return PassiveObservation(
        ip=ip, mac=mac, protocol=protocol, service_type=service_type,
        device_hint="", confidence="low", capability=capability,
    )


def test_capability_observation_is_persisted_and_leaves_identity_alone(tmp_path):
    """The Phase 1 wiring, end to end through the real handler.

    Before: this announcement rewrote device_type to "Streaming Stick" at a
    confidence no vendor/hostname evidence could outrank. After: the device
    keeps the identity it had and gains a true, additive capability.
    """
    from modules.metric_store import MetricStore

    ip, mac = "192.168.1.70", "aa:bb:cc:dd:ee:70"
    store = MetricStore(db_path=tmp_path / "cap.db")
    store.upsert_known_device(mac, ip=ip, device_type="Smart Speaker / Audio")

    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Smart Speaker / Audio")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    stub._store = store

    stub._on_passive_observation(
        _make_capability_obs(ip, mac, "_googlecast._tcp", "Cast target")
    )

    assert store.get_device_capabilities(mac) == ["Cast target"]
    assert dev.device_type == "Smart Speaker / Audio", (
        "a capability announcement must not restate what the device is"
    )

    _cleanup(table)
    store.close()


def test_capabilities_from_several_announcements_accumulate(tmp_path):
    """A device that casts AND does AirPlay keeps both, instead of alternating
    between two identities the way device_type did."""
    from modules.metric_store import MetricStore

    ip, mac = "192.168.1.71", "aa:bb:cc:dd:ee:71"
    store = MetricStore(db_path=tmp_path / "cap2.db")
    store.upsert_known_device(mac, ip=ip, device_type="Smart TV")

    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Smart TV")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    stub._store = store

    for service_type, capability in (
        ("_googlecast._tcp", "Cast target"),
        ("_airplay._tcp", "AirPlay video"),
        ("_raop._tcp", "AirPlay audio"),
    ):
        stub._on_passive_observation(
            _make_capability_obs(ip, mac, service_type, capability)
        )

    assert store.get_device_capabilities(mac) == [
        "AirPlay audio", "AirPlay video", "Cast target",
    ]
    assert dev.device_type == "Smart TV"

    _cleanup(table)
    store.close()


def test_capability_is_recorded_even_for_a_user_overridden_device(tmp_path):
    """An override pins what the device IS. What it can DO is still observable
    fact, and recording it cannot contradict the user's choice."""
    from modules.metric_store import MetricStore

    ip, mac = "192.168.1.72", "aa:bb:cc:dd:ee:72"
    store = MetricStore(db_path=tmp_path / "cap3.db")
    store.upsert_known_device(mac, ip=ip, device_type="Smart Speaker / Audio")
    store.set_classification_override(mac, "Smart Speaker / Audio")

    table = _make_table([(ip, "", mac)])
    dev = _DevObj(ip, mac, device_type="Smart Speaker / Audio")
    stub = _make_stub(table, {"devices": [dev]}, net_info=None)
    stub._store = store

    stub._on_passive_observation(
        _make_capability_obs(ip, mac, "_airplay._tcp", "AirPlay video")
    )

    assert store.get_device_capabilities(mac) == ["AirPlay video"]
    assert dev.device_type == "Smart Speaker / Audio"

    _cleanup(table)
    store.close()

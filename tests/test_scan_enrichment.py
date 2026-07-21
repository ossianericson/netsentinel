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

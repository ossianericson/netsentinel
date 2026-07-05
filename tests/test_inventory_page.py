"""
Tests for ui/pages/inventory_page.py — Sprint 5 device intelligence additions.

Covers:
  • S5-2: Room/Owner group pill bar appears once a device has an annotation
  • S5-3: Health summary top-line reflects device risk/offline state
  • S5-1: open_device_drawer() prefills the suggested label when none is saved
  • S5-6: device drawer timeline section renders without error
"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.device_tracker import save_annotations
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
        try:
            from PyQt6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        except Exception:
            pass  # non-fatal
        for _ in range(3):
            app.processEvents()
    _created_pages.clear()


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def _make_page(store=None) -> InventoryPage:
    page = InventoryPage(store=store)
    _created_pages.append(page)
    return page


def _dev(mac, ip, risk_level="CLEAN", display_state=""):
    return {
        "mac": mac, "ip": ip, "hostname": "", "vendor": "Apple",
        "device_type": "Laptop", "risk_level": risk_level,
        "confidence": 0.9, "is_gateway": False, "display_state": display_state,
        "last_seen_ts": 0,
    }


def test_constructs_without_store():
    page = _make_page(None)
    assert page is not None


def test_health_summary_all_healthy(store):
    page = _make_page(store)
    page.set_scan_devices([_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert not page._health_summary_lbl.isHidden()
    assert "healthy" in page._health_summary_lbl.text().lower()


def test_health_summary_flags_unusual_device(store):
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11", risk_level="HIGH"),
    ])
    assert "1 of your 2 devices" in page._health_summary_lbl.text()


def test_group_bar_hidden_with_no_annotations(store):
    page = _make_page(store)
    page.set_scan_devices([_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert page._group_bar_frame.isHidden()


def test_group_bar_shows_room_pills_once_annotated(store):
    save_annotations("aa:bb:cc:00:00:01", store, location="Living Room")
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    assert not page._group_bar_frame.isHidden()
    assert "Living Room" in page._group_pills
    assert "Unassigned" in page._group_pills


def test_toggle_group_hides_non_matching_rows(store):
    save_annotations("aa:bb:cc:00:00:01", store, location="Living Room")
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    page._toggle_group("Living Room")
    hidden_states = [page._snap_table.isRowHidden(r) for r in range(page._snap_table.rowCount())]
    assert hidden_states.count(True) == 1


def test_open_device_drawer_prefills_suggested_label(store):
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01", suggested_label="Sony Smart TV")
    assert page._device_drawer._ann_label.text() == "Sony Smart TV"


def test_open_device_drawer_keeps_existing_label(store):
    save_annotations("aa:bb:cc:00:00:01", store, user_label="My TV")
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01", suggested_label="Sony Smart TV")
    assert page._device_drawer._ann_label.text() == "My TV"


def test_drawer_timeline_renders_without_events(store):
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01")
    assert page._device_drawer._timeline_body.count() >= 1


def test_drawer_timeline_includes_join_event(store):
    store.record_device_event(ip="192.168.1.10", event_type="JOINED", mac="aa:bb:cc:00:00:01")
    page = _make_page(store)
    page.open_device_drawer("aa:bb:cc:00:00:01")
    texts = []
    for i in range(page._device_drawer._timeline_body.count()):
        w = page._device_drawer._timeline_body.itemAt(i).widget()
        if w:
            texts.append(w.text())
    assert any("JOINED" in t for t in texts)


# ── S9-3: unknown-device alert prompt ───────────────────────────────────────

def _unknown_dev(mac, ip):
    return {
        "mac": mac, "ip": ip, "hostname": "", "vendor": "",
        "device_type": "Unknown Device", "risk_level": "UNKNOWN",
        "confidence": 0.0, "is_gateway": False, "display_state": "",
        "last_seen_ts": 0,
    }


def test_unknown_device_prompt_shown_when_unknown_present(store, monkeypatch):
    monkeypatch.setattr(
        "ui.context_banners.should_show_banner", lambda key: True,
    )
    page = _make_page(store)
    page.set_scan_devices([
        _dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _unknown_dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    assert not page._unknown_device_prompt.isHidden()
    assert "1" in page._unknown_device_lbl.text()


def test_unknown_device_prompt_hidden_when_no_unknown(store, monkeypatch):
    monkeypatch.setattr(
        "ui.context_banners.should_show_banner", lambda key: True,
    )
    page = _make_page(store)
    page.set_scan_devices([_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert page._unknown_device_prompt.isHidden()


def test_unknown_device_prompt_respects_dismissal(store, monkeypatch):
    monkeypatch.setattr(
        "ui.context_banners.should_show_banner", lambda key: False,
    )
    page = _make_page(store)
    page.set_scan_devices([_unknown_dev("aa:bb:cc:00:00:02", "192.168.1.11")])
    assert page._unknown_device_prompt.isHidden()


def test_unknown_device_alert_click_emits_navigate_to(store, monkeypatch):
    monkeypatch.setattr(
        "ui.context_banners.should_show_banner", lambda key: True,
    )
    monkeypatch.setattr(
        "ui.context_banners.mark_banner_seen", lambda key: None,
    )
    page = _make_page(store)
    page.set_scan_devices([_unknown_dev("aa:bb:cc:00:00:02", "192.168.1.11")])
    received = []
    page.navigate_to.connect(received.append)
    page._on_unknown_device_alert_clicked()
    assert received == ["Custom Triggers"]
    assert page._unknown_device_prompt.isHidden()


# ── RULE-T7 behavioral tests: field population (Bug: blank table / only IPs) ──


def _rich_dev(mac, ip, hostname="laptop.local", vendor="Apple Inc.", device_type="Laptop"):
    """Device dict with all fields populated — catches regressions where fields go blank."""
    return {
        "mac": mac, "ip": ip,
        "hostname": hostname, "vendor": vendor,
        "device_type": device_type,
        "risk_level": "CLEAN", "confidence": 0.9,
        "is_gateway": False, "display_state": "",
        "last_seen_ts": 0,
    }


def test_set_scan_devices_row_count(store):
    """set_scan_devices with N devices must insert exactly N rows into _snap_table.

    Regression guard: if the loop body throws and exits early, rowCount() < N.
    """
    page = _make_page(store)
    page.set_scan_devices([
        _rich_dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _rich_dev("aa:bb:cc:00:00:02", "192.168.1.11"),
        _rich_dev("aa:bb:cc:00:00:03", "192.168.1.12"),
    ])
    assert page._snap_table.rowCount() == 3, (
        f"Expected 3 rows after set_scan_devices with 3 devices; "
        f"got {page._snap_table.rowCount()} — 'blank after scan' regression"
    )


def test_set_scan_devices_table_visible(store):
    """_snap_table must NOT be hidden after set_scan_devices with a non-empty device list.

    Uses isHidden() (widget's own hidden state) not isVisible() (requires parent to be shown).
    """
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert not page._snap_table.isHidden(), (
        "_snap_table is hidden after set_scan_devices with devices — "
        "causes 'completely blank Devices page after scan' bug"
    )


def test_set_scan_devices_switches_content_stack(store):
    """_content_stack must switch from empty-state page 0 to content page 1 on first data."""
    page = _make_page(store)
    assert page._content_stack.currentIndex() == 0, "Must start on page 0 (empty state)"
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    assert page._content_stack.currentIndex() == 1, (
        "_content_stack stuck on page 0 after devices arrive — "
        "the whole page appears blank; regression guard for content-stack switch"
    )


def test_set_scan_devices_vendor_column(store):
    """Vendor value from scan result must appear in the Manufacturer column (col 6).

    Bug: after restart, vendor column shows 'Unknown' or '—' instead of real vendor.
    """
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10", vendor="Apple Inc.")])
    cell = page._snap_table.item(0, 6)
    assert cell is not None, "Manufacturer cell (col 6) is None"
    assert cell.text() == "Apple Inc.", (
        f"Manufacturer column: expected 'Apple Inc.' but got '{cell.text()}' — "
        f"vendor field depopulation bug"
    )


def test_set_scan_devices_hostname_column(store):
    """Hostname value from scan result must appear in the Hostname column (col 4).

    Bug: after restart, hostname column shows '—' instead of resolved hostname.
    """
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10",
                                     hostname="my-laptop.local")])
    cell = page._snap_table.item(0, 4)
    assert cell is not None, "Hostname cell (col 4) is None"
    assert cell.text() == "my-laptop.local", (
        f"Hostname column: expected 'my-laptop.local' but got '{cell.text()}' — "
        f"hostname field depopulation bug"
    )


def test_set_scan_devices_type_column(store):
    """Device type from scan result must appear in the Type column (col 7).

    Bug: after restart, type column shows 'Unknown Device' instead of real type.
    The cell text includes a confidence indicator prefix (★●◑○) before the type name.
    """
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10",
                                     device_type="Smart TV")])
    cell = page._snap_table.item(0, 7)
    assert cell is not None, "Type cell (col 7) is None"
    assert "Smart TV" in cell.text(), (
        f"Type column: expected 'Smart TV' in cell but got '{cell.text()}' — "
        f"device_type field depopulation bug"
    )


def test_set_scan_devices_ip_column(store):
    """IP address must appear in the IP Address column (col 2)."""
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.42")])
    cell = page._snap_table.item(0, 2)
    assert cell is not None, "IP Address cell (col 2) is None"
    assert cell.text() == "192.168.1.42", (
        f"IP Address column: expected '192.168.1.42' but got '{cell.text()}'"
    )


def test_set_scan_devices_with_devinfo_objects(store):
    """set_scan_devices must correctly render DeviceInfo dataclass objects, not just dicts.

    Live scan results arrive as DeviceInfo objects; startup restore uses dicts.
    Both paths must populate vendor/hostname/type columns.
    """
    from modules.rogue_device import DeviceInfo
    dev = DeviceInfo(
        ip="192.168.1.50",
        mac="aa:bb:cc:00:00:05",
        vendor="Samsung Electronics",
        hostname="samsung-tv.local",
        risk_level="CLEAN",
        device_type="Smart TV",
        confidence=0.85,
        is_gateway=False,
    )
    page = _make_page(store)
    page.set_scan_devices([dev])
    assert page._snap_table.rowCount() == 1, (
        f"Expected 1 row for DeviceInfo object; got {page._snap_table.rowCount()}"
    )
    vendor_cell = page._snap_table.item(0, 6)
    assert vendor_cell is not None and vendor_cell.text() == "Samsung Electronics", (
        f"Vendor (col 6): expected 'Samsung Electronics', got "
        f"'{vendor_cell.text() if vendor_cell else None}'"
    )
    host_cell = page._snap_table.item(0, 4)
    assert host_cell is not None and host_cell.text() == "samsung-tv.local", (
        f"Hostname (col 4): expected 'samsung-tv.local', got "
        f"'{host_cell.text() if host_cell else None}'"
    )
    type_cell = page._snap_table.item(0, 7)
    assert type_cell is not None and "Smart TV" in type_cell.text(), (
        f"Type (col 7): expected 'Smart TV' in cell, got "
        f"'{type_cell.text() if type_cell else None}'"
    )


def test_startup_cache_restore_dict_populates_all_fields(store):
    """The startup-cache-restore dict format (as built by _restore_cached_scan) must
    populate vendor, hostname, and device_type columns — not just the IP column.

    Regression guard for 'after restart only IP addresses visible' bug.
    The dict shape here mirrors what _restore_cached_scan produces from KnownDevice objects.
    """
    startup_device = {
        "ip":            "192.168.1.100",
        "hostname":      "nas.home",
        "mac":           "aa:bb:cc:00:00:ff",
        "vendor":        "Synology Inc.",
        "risk_level":    "UNKNOWN",
        "device_type":   "NAS",
        "display_state": "cached",
        "last_seen_ts":  0,
        "confidence":    0.8,
        "is_gateway":    False,
        "verdict":       "",
        "inferred_role": None,
        "scan_count":    5,
        "ip_stability":  0.9,
        "is_pinned":     False,
    }
    page = _make_page(store)
    page.set_scan_devices([startup_device])
    assert page._snap_table.rowCount() == 1, "Startup device must produce 1 table row"

    ip_cell = page._snap_table.item(0, 2)
    assert ip_cell is not None and ip_cell.text() == "192.168.1.100", (
        f"IP col: expected '192.168.1.100', got '{ip_cell.text() if ip_cell else None}'"
    )
    host_cell = page._snap_table.item(0, 4)
    assert host_cell is not None and host_cell.text() == "nas.home", (
        f"Hostname col: expected 'nas.home', got "
        f"'{host_cell.text() if host_cell else None}' — "
        f"startup-restore hostname depopulation bug"
    )
    vendor_cell = page._snap_table.item(0, 6)
    assert vendor_cell is not None and vendor_cell.text() == "Synology Inc.", (
        f"Vendor col: expected 'Synology Inc.', got "
        f"'{vendor_cell.text() if vendor_cell else None}' — "
        f"startup-restore vendor depopulation bug"
    )
    type_cell = page._snap_table.item(0, 7)
    assert type_cell is not None and "NAS" in type_cell.text(), (
        f"Type col: expected 'NAS' in cell, got "
        f"'{type_cell.text() if type_cell else None}' — "
        f"startup-restore device_type depopulation bug"
    )


def test_set_scan_devices_empty_list_hides_table(store):
    """set_scan_devices([]) must keep _snap_table hidden and stay on page 0."""
    page = _make_page(store)
    page.set_scan_devices([])
    assert page._snap_table.isHidden(), "_snap_table must be hidden when devices=[]"
    assert page._content_stack.currentIndex() == 0, (
        "_content_stack must stay on empty-state page 0 when no devices supplied"
    )


def test_set_scan_devices_no_rows_hidden_by_default(store):
    """After set_scan_devices, no rows should be hidden unless the user set a filter.

    Regression guard: if _apply_segment_filter hides all rows due to stale
    _active_seg_ids, the page looks blank even though the table has rows.
    """
    page = _make_page(store)
    page.set_scan_devices([
        _rich_dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _rich_dev("aa:bb:cc:00:00:02", "192.168.1.11"),
    ])
    hidden_count = sum(
        1 for r in range(page._snap_table.rowCount())
        if page._snap_table.isRowHidden(r)
    )
    assert hidden_count == 0, (
        f"{hidden_count} of {page._snap_table.rowCount()} rows hidden after set_scan_devices "
        f"with no active filter — _apply_segment_filter is hiding rows unexpectedly, "
        f"causing 'blank page after scan' bug"
    )


def test_rescan_replaces_cached_data_with_live_data(store):
    """A second call to set_scan_devices must replace earlier data, not append.

    Regression guard: startup-restore populates table, then scan result replaces it.
    Table must end with exactly the live-scan row count, not cached+live combined.
    """
    page = _make_page(store)
    # Startup restore: 3 cached devices
    page.set_scan_devices([
        _rich_dev("aa:bb:cc:00:00:01", "192.168.1.10"),
        _rich_dev("aa:bb:cc:00:00:02", "192.168.1.11"),
        _rich_dev("aa:bb:cc:00:00:03", "192.168.1.12"),
    ])
    assert page._snap_table.rowCount() == 3
    # Scan result: 1 live device
    page.set_scan_devices([
        _rich_dev("aa:bb:cc:00:00:99", "192.168.1.99", vendor="Dell", device_type="Workstation"),
    ])
    assert page._snap_table.rowCount() == 1, (
        f"Expected 1 row after rescan; got {page._snap_table.rowCount()} — "
        f"table may be accumulating rows instead of replacing"
    )
    vendor_cell = page._snap_table.item(0, 6)
    assert vendor_cell is not None and vendor_cell.text() == "Dell", (
        f"After rescan vendor should be 'Dell', got "
        f"'{vendor_cell.text() if vendor_cell else None}'"
    )


# ── update_device_vendor — async OUI resolution snap_table update ─────────────

def test_update_device_vendor_updates_snap_table_cell(store):
    """update_device_vendor(mac, vendor) must update col 6 (Manufacturer) in _snap_table.

    This covers the async OUI lookup path: after a scan, _on_vendor_resolved fires and
    must call page.update_device_vendor(mac, vendor) so the Inventory page shows the
    resolved vendor without requiring a restart.

    Regression guard for Bug #1 ('only IPs after restart') — if resolved vendors are
    never propagated to _snap_table, the user sees 'Unknown' until they restart.
    """
    page = _make_page(store)
    mac = "aa:bb:cc:00:00:01"
    page.set_scan_devices([_rich_dev(mac, "192.168.1.10", vendor="Unknown")])

    # Confirm initial state: vendor shows "Unknown"
    initial_vendor = None
    for row in range(page._snap_table.rowCount()):
        mac_item = page._snap_table.item(row, 5)  # col 5 = MAC Address
        if mac_item and mac_item.text().lower().replace(":", "") == mac.replace(":", ""):
            v = page._snap_table.item(row, 6)  # col 6 = Manufacturer
            initial_vendor = v.text() if v else None
            break
    assert initial_vendor is not None, "Row must exist before calling update_device_vendor"
    assert initial_vendor in ("Unknown", "—", ""), (
        f"Expected initial vendor to be placeholder; got '{initial_vendor}'"
    )

    # Simulate async OUI lookup completing
    page.update_device_vendor(mac, "Apple Inc.")

    # Verify _snap_table was updated
    updated_vendor = None
    for row in range(page._snap_table.rowCount()):
        mac_item = page._snap_table.item(row, 5)
        if mac_item and mac_item.text().lower().replace(":", "") == mac.replace(":", ""):
            v = page._snap_table.item(row, 6)
            updated_vendor = v.text() if v else None
            break
    assert updated_vendor == "Apple Inc.", (
        f"Expected col 6 (Manufacturer) = 'Apple Inc.' after update_device_vendor; "
        f"got '{updated_vendor}' — update_device_vendor must update _snap_table"
    )


# ── Context menu — "Alert me if this device goes down" opt-in toggle ─────────

def test_context_menu_alert_toggle_calls_set_device_alert_opt_in(store, monkeypatch):
    """RULE-T7: right-click 'Alert me if this device goes down' must round-trip
    through MetricStore.set_device_alert_opt_in with the row's mac and the
    flipped opt-in value."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QMenu

    mac = "aa:bb:cc:00:00:42"
    store.upsert_known_device(mac, ip="192.168.1.42", hostname="phone")
    page = _make_page(store)
    page.set_scan_devices([_rich_dev(mac, "192.168.1.42", vendor="Apple", device_type="Phone")])

    monkeypatch.setattr(
        page._snap_table, "indexAt",
        lambda pos: page._snap_table.model().index(0, 0),
    )

    def fake_exec(self, *a, **kw):
        for act in self.actions():
            if act.text() == "Alert me if this device goes down":
                return act
        return None
    monkeypatch.setattr(QMenu, "exec", fake_exec)

    calls = []
    monkeypatch.setattr(
        store, "set_device_alert_opt_in",
        lambda m, v: calls.append((m, v)),
    )

    page._snap_table_context_menu(QPoint(0, 0))

    assert calls == [(mac, True)], (
        f"Expected set_device_alert_opt_in('{mac}', True); got {calls}"
    )


def test_update_device_vendor_only_updates_matching_mac(store):
    """update_device_vendor must only update the row for the specified MAC."""
    page = _make_page(store)
    page.set_scan_devices([
        _rich_dev("aa:bb:cc:00:00:01", "192.168.1.10", vendor="Unknown"),
        _rich_dev("aa:bb:cc:00:00:02", "192.168.1.11", vendor="Unknown"),
    ])

    page.update_device_vendor("aa:bb:cc:00:00:01", "Apple Inc.")

    def _vendor_for(mac_str):
        for row in range(page._snap_table.rowCount()):
            mac_item = page._snap_table.item(row, 5)
            if mac_item and mac_item.text().lower().replace(":", "") == mac_str.replace(":", ""):
                v = page._snap_table.item(row, 6)
                return v.text() if v else None
        return None

    assert _vendor_for("aa:bb:cc:00:00:01") == "Apple Inc.", (
        "Target MAC row must have updated vendor"
    )
    other = _vendor_for("aa:bb:cc:00:00:02")
    assert other != "Apple Inc.", (
        f"Non-target MAC row must NOT have been updated; got '{other}'"
    )


def test_update_device_vendor_noop_for_unknown_mac(store):
    """update_device_vendor for a MAC not in the table must not raise."""
    page = _make_page(store)
    page.set_scan_devices([_rich_dev("aa:bb:cc:00:00:01", "192.168.1.10")])
    # Should not raise — just a no-op
    page.update_device_vendor("ff:ff:ff:ff:ff:ff", "Some Vendor")

"""
Regression tests for vendor data persistence across the async OUI lookup pipeline.

Bug summary (v2.1.15):
  After app restart, the Devices/Inventory page shows only IP addresses —
  vendor, hostname, and device-type columns are empty or show placeholder text.

Root causes:
  1. _on_vendor_resolved (scan_wiring.py) updates DeviceInfo objects and _m1_table
     in memory but NEVER calls store.upsert_known_device() to persist the resolved
     vendor to MetricStore.  On restart, MetricStore returns vendor=NULL → shows
     "Unknown" in startup-restore path.

  2. DeviceTracker._normalise passes vendor="Unknown" (truthy) to upsert_known_device.
     SQL COALESCE("Unknown", "Apple Inc.") = "Unknown" — clobbers any previously
     stored resolved vendor on every subsequent scan.
     (Covered in test_device_tracker.py TestVendorPreservation)

These tests verify the fix: _on_vendor_resolved must persist the resolved vendor
to MetricStore via upsert_known_device(mac, vendor=vendor).
"""

import types
import pytest

try:
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")


@pytest.fixture
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "vendor_test.db")
    yield s
    s.close()


def _make_m1_table():
    """Minimal scan-results table (_m1_table) with the columns _on_vendor_resolved expects.

    _on_vendor_resolved reads col 2 = MAC, col 3 = Vendor from _m1_table.
    """
    t = QTableWidget(0, 8)
    return t


def _m1_result_with_device(mac, vendor="Unknown"):
    """Build a minimal _m1_result dict for one device."""
    return {
        "devices": [{
            "mac": mac, "ip": "192.168.1.10",
            "hostname": "", "vendor": vendor,
            "device_type": "Laptop", "risk_level": "CLEAN",
        }]
    }


def _call_on_vendor_resolved(store, mac, resolved_vendor, initial_vendor="Unknown"):
    """
    Call _on_vendor_resolved via direct class invocation, simulating what happens
    when the async OUI batch worker emits vendor_resolved(mac, vendor).

    Returns the namespace object so callers can inspect _m1_result state.
    """
    from ui.scan_wiring import ScanResultMixin
    m1_table = _make_m1_table()

    # Pre-populate _m1_table with a row (MAC in col 2, Vendor in col 3)
    m1_table.insertRow(0)
    m1_table.setItem(0, 2, QTableWidgetItem(mac))
    m1_table.setItem(0, 3, QTableWidgetItem(initial_vendor))

    obj = types.SimpleNamespace(
        _store=store,
        _m1_result=_m1_result_with_device(mac, vendor=initial_vendor),
        _m1_table=m1_table,
    )
    # Call the unbound method directly — works in Python 3
    ScanResultMixin._on_vendor_resolved(obj, mac, resolved_vendor)
    return obj


# ── Test: async OUI lookup persists to MetricStore ───────────────────────────

class TestOnVendorResolvedPersistence:
    """_on_vendor_resolved must persist the resolved vendor to MetricStore.

    Without persistence, the vendor is only in memory for the current session.
    After restart, _restore_cached_scan reads from MetricStore and shows 'Unknown'.
    """

    def test_vendor_resolved_persists_to_store(self, store):
        """_on_vendor_resolved must call upsert_known_device with the resolved vendor.

        This test FAILS before the fix because _on_vendor_resolved only updates
        _m1_result and _m1_table in memory; it never calls self._store.upsert_known_device.
        """
        mac = "aa:bb:cc:11:22:33"
        store.upsert_known_device(mac, ip="192.168.1.10", vendor=None)  # initially no vendor

        _call_on_vendor_resolved(store, mac, "Apple Inc.")

        kd = store.get_known_devices().get(mac)
        assert kd is not None, f"Device {mac} must exist in store"
        assert kd.vendor == "Apple Inc.", (
            f"Expected vendor='Apple Inc.' persisted after _on_vendor_resolved; "
            f"got '{kd.vendor}' — _on_vendor_resolved does not call upsert_known_device"
        )

    def test_vendor_resolved_does_not_persist_empty_string(self, store):
        """_on_vendor_resolved must be a no-op when vendor is empty/falsy."""
        mac = "aa:bb:cc:11:22:34"
        store.upsert_known_device(mac, ip="192.168.1.11", vendor=None)

        _call_on_vendor_resolved(store, mac, "")  # empty vendor — should not persist

        kd = store.get_known_devices().get(mac)
        # vendor should remain NULL (None) — not overwritten with ""
        assert kd is None or kd.vendor in (None, "", "Unknown"), (
            "Empty vendor string from _on_vendor_resolved must not overwrite stored value"
        )

    def test_vendor_resolved_overwrites_unknown_in_store(self, store):
        """Resolved vendor must overwrite 'Unknown' if the store has 'Unknown' stored."""
        mac = "aa:bb:cc:11:22:35"
        store.upsert_known_device(mac, ip="192.168.1.12", vendor="Unknown")

        _call_on_vendor_resolved(store, mac, "Dell Inc.", initial_vendor="Unknown")

        kd = store.get_known_devices().get(mac)
        assert kd is not None
        assert kd.vendor == "Dell Inc.", (
            f"Expected 'Dell Inc.' to overwrite stored 'Unknown'; got '{kd.vendor}'"
        )

    def test_vendor_resolved_updates_m1_result_in_memory(self, store):
        """_on_vendor_resolved must also update the DeviceInfo in _m1_result['devices']."""
        mac = "aa:bb:cc:11:22:36"
        store.upsert_known_device(mac, ip="192.168.1.13", vendor=None)

        obj = _call_on_vendor_resolved(store, mac, "Synology Inc.")

        devices = obj._m1_result.get("devices", [])
        assert len(devices) == 1
        d = devices[0]
        stored_vendor = d.get("vendor") if isinstance(d, dict) else getattr(d, "vendor", None)
        assert stored_vendor == "Synology Inc.", (
            f"Expected in-memory DeviceInfo vendor='Synology Inc.'; got '{stored_vendor}'"
        )

    def test_on_vendor_resolved_no_store_does_not_raise(self):
        """_on_vendor_resolved must not raise when self._store is None."""
        from ui.scan_wiring import ScanResultMixin
        mac = "aa:bb:cc:11:22:37"
        m1_table = _make_m1_table()
        m1_table.insertRow(0)
        m1_table.setItem(0, 2, QTableWidgetItem(mac))
        m1_table.setItem(0, 3, QTableWidgetItem("Unknown"))

        obj = types.SimpleNamespace(
            _store=None,  # no store
            _m1_result=_m1_result_with_device(mac),
            _m1_table=m1_table,
        )
        # Must not raise
        ScanResultMixin._on_vendor_resolved(obj, mac, "TP-Link")


# ── Integration: full round-trip after vendor resolution ─────────────────────

class TestVendorPersistenceRoundTrip:
    """End-to-end: vendor resolved → persisted → visible after simulated restart."""

    def test_resolved_vendor_survives_simulated_restart(self, store):
        """After _on_vendor_resolved persists the vendor, a simulated restart must show it.

        This mirrors the exact failure scenario:
        1. Scan runs, device found with vendor='Unknown' in MetricStore
        2. Async OUI lookup resolves vendor='Apple Inc.' → _on_vendor_resolved called
        3. App restarts → _restore_cached_scan reads MetricStore
        4. Expected: shows 'Apple Inc.'   Actual (before fix): shows 'Unknown'
        """
        mac = "aa:bb:cc:11:22:38"
        ip = "192.168.1.20"

        # Step 1: scan — device stored with no vendor
        store.upsert_known_device(mac, ip=ip, vendor=None)

        # Step 2: async OUI lookup resolves vendor
        _call_on_vendor_resolved(store, mac, "Apple Inc.")

        # Step 3: simulated restart — read MetricStore as _restore_cached_scan would
        known = store.get_known_devices()
        kd = known.get(mac)
        assert kd is not None, f"Device {mac} must exist in store after persistence"

        # Build the startup-restore dict (mirrors _restore_cached_scan lines 1207-1220)
        startup_vendor = kd.vendor or "Unknown"

        assert startup_vendor == "Apple Inc.", (
            f"After simulated restart, vendor should be 'Apple Inc.' "
            f"(from persisted OUI resolution); got '{startup_vendor}' — "
            "Bug #1: resolved vendor not persisted to MetricStore"
        )

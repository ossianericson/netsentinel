"""Tests for modules/device_admin.py — module-layer boundary for UI-driven
device / classification / Home-Automation edits (ARCH RULE 1, #21).

Each helper is a thin pass-through to a MetricStore write method. The forwarding
tests (MagicMock) prove correct dispatch; the real-store test proves the helper
signatures are compatible with the live MetricStore and actually persist.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_import():
    from modules import device_admin
    for fn in (
        "set_classification_override", "clear_classification_override",
        "set_device_alert_opt_in", "update_device_ha_info",
        "upsert_known_device", "record_ha_detected",
    ):
        assert callable(getattr(device_admin, fn)), fn


def test_set_classification_override_forwards():
    from modules.device_admin import set_classification_override
    store = MagicMock()
    set_classification_override(store, "aa:bb:cc:dd:ee:ff", "Printer")
    store.set_classification_override.assert_called_once_with("aa:bb:cc:dd:ee:ff", "Printer")


def test_clear_classification_override_forwards():
    from modules.device_admin import clear_classification_override
    store = MagicMock()
    clear_classification_override(store, "aa:bb:cc:dd:ee:ff")
    store.clear_classification_override.assert_called_once_with("aa:bb:cc:dd:ee:ff")


def test_set_device_alert_opt_in_forwards():
    from modules.device_admin import set_device_alert_opt_in
    store = MagicMock()
    set_device_alert_opt_in(store, "aa:bb", True)
    store.set_device_alert_opt_in.assert_called_once_with("aa:bb", True)


def test_update_device_ha_info_forwards_kwargs():
    from modules.device_admin import update_device_ha_info
    store = MagicMock()
    update_device_ha_info(store, "aa:bb", room="Office", is_pinned=True)
    store.update_device_ha_info.assert_called_once_with("aa:bb", room="Office", is_pinned=True)


def test_upsert_known_device_forwards():
    from modules.device_admin import upsert_known_device
    store = MagicMock()
    upsert_known_device(store, "aa:bb", vendor="Acme", device_type="Printer")
    store.upsert_known_device.assert_called_once_with("aa:bb", vendor="Acme", device_type="Printer")


def test_record_ha_detected_forwards():
    from modules.device_admin import record_ha_detected
    store = MagicMock()
    record_ha_detected(store, ip="192.168.1.5", ha_type="mqtt", mac="aa:bb", confidence="high")
    store.record_ha_detected.assert_called_once_with(
        ip="192.168.1.5", ha_type="mqtt", mac="aa:bb", confidence="high"
    )


# ── Real-store integration: helpers persist against a live MetricStore ─────────

@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


def test_helpers_persist_against_real_store(store):
    from modules import device_admin as da
    mac = "aa:bb:cc:dd:ee:ff"
    da.upsert_known_device(store, mac, vendor="Acme", device_type="Printer")
    da.update_device_ha_info(store, mac, room="Lab", custom_name="Front Printer")
    da.set_classification_override(store, mac, "Router")

    devices = store.get_known_devices()  # Dict[mac, KnownDevice]
    assert mac in devices
    assert devices[mac].room == "Lab"
    assert store.get_classification_override(mac) == "Router"

    da.clear_classification_override(store, mac)
    assert store.get_classification_override(mac) in (None, "")

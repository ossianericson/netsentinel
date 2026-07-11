"""
device_admin.py — module-layer boundary for UI-driven device edits (ARCH RULE 1).

The UI (Inventory, Home Automation, device dialogs) must never call MetricStore
write methods directly (item #21 — direct UI writes are how the device_ip_history
double-count bug happened). These thin pass-throughs keep the device write surface
in the module layer while leaving the actual SQL in MetricStore.

Pure module: no PyQt import, no direct DB writes — every helper forwards to a
MetricStore method. Callers import the functions by name and pass the store as the
first argument:

    from modules.device_admin import set_classification_override
    set_classification_override(store, mac, "Router")

Note: record_ip_observation is deliberately NOT wrapped here — its single-writer
rule (DeviceTracker.process_scan) must stay the only path (see metric_store.py).
"""
from __future__ import annotations

from typing import Any


def set_classification_override(store: Any, mac: str, device_type: str) -> None:
    """Pin a device's classification (wraps MetricStore.set_classification_override)."""
    store.set_classification_override(mac, device_type)


def clear_classification_override(store: Any, mac: str) -> None:
    """Remove a pinned classification (wraps MetricStore.clear_classification_override)."""
    store.clear_classification_override(mac)


def set_device_alert_opt_in(store: Any, mac: str, opt_in: bool) -> None:
    """Toggle per-device alert opt-in (wraps MetricStore.set_device_alert_opt_in)."""
    store.set_device_alert_opt_in(mac, opt_in)


def update_device_ha_info(store: Any, mac: str, **kwargs: Any) -> None:
    """Update Home-Automation metadata for a device (wraps update_device_ha_info)."""
    store.update_device_ha_info(mac, **kwargs)


def upsert_known_device(store: Any, mac: str, **kwargs: Any) -> None:
    """Insert/update a known_device row (wraps MetricStore.upsert_known_device)."""
    store.upsert_known_device(mac, **kwargs)


def record_ha_detected(store: Any, **kwargs: Any) -> None:
    """Record a Home-Automation signature detection (wraps record_ha_detected)."""
    store.record_ha_detected(**kwargs)

"""
scan_persistence.py — module-layer boundary for scan/background-driven writes
(ARCH RULE 1, item #21).

The Dashboard scan-glue mixins (scan_wiring, scan_enrichment, tabs, tabs_analysis,
dashboard) produce metrics during a scan and must not write MetricStore directly —
direct UI writes are how the device_ip_history double-count bug happened. These
thin pass-throughs keep the write surface in the module layer.

persist_alert() is the one non-trivial helper: it collapses the six identical
`record_alert_fired(a.rule_name, a.host, a.severity, a.message, ts=a.ts,
rule_type=a.rule_type)` call sites into a single object-taking function.

Pure module: no PyQt import, no direct DB writes. Callers import by name:

    from modules.scan_persistence import record_rtt, persist_alert
    record_rtt(store, ip, rtt_ms)
    persist_alert(store, alert)

Invariant: record_ip_observation is deliberately NOT wrapped — its single-writer
rule (DeviceTracker.process_scan) must remain the only path (see metric_store.py).
"""
from __future__ import annotations

from typing import Any


def record_rtt(store: Any, host: str, rtt_ms: float, **kwargs: Any) -> None:
    """Persist a round-trip-time sample (wraps MetricStore.record_rtt)."""
    store.record_rtt(host, rtt_ms, **kwargs)


def persist_alert(store: Any, alert: Any) -> int:
    """Persist a fired alert object (wraps MetricStore.record_alert_fired).

    Unpacks the AlertFired dataclass so callers pass the whole object instead of
    repeating its six fields at every site. Returns the new alert row id.
    """
    return store.record_alert_fired(
        alert.rule_name, alert.host, alert.severity, alert.message,
        ts=alert.ts, rule_type=alert.rule_type,
    )


def record_mesh_snapshot(store: Any, **kwargs: Any) -> None:
    """Persist a mesh signal snapshot (wraps MetricStore.record_mesh_snapshot)."""
    store.record_mesh_snapshot(**kwargs)


def record_modem_signal(store: Any, **kwargs: Any) -> None:
    """Persist a modem signal snapshot (wraps MetricStore.record_modem_signal)."""
    store.record_modem_signal(**kwargs)


def record_plugin_snapshot(store: Any, plugin_name: str, data: dict) -> None:
    """Persist a hardware-plugin snapshot (wraps MetricStore.record_plugin_snapshot)."""
    store.record_plugin_snapshot(plugin_name, data)


def record_app_traffic_sample(store: Any, **kwargs: Any) -> None:
    """Persist an app-traffic sample (wraps MetricStore.record_app_traffic_sample)."""
    store.record_app_traffic_sample(**kwargs)


def record_app_traffic_samples(store: Any, samples: list) -> None:
    """Persist a batch of app-traffic samples in one transaction
    (wraps MetricStore.record_app_traffic_samples, Phase B1)."""
    store.record_app_traffic_samples(samples)


def record_grade(store: Any, grade: str, score: float, verdict: str) -> None:
    """Persist an overall network grade (wraps MetricStore.record_grade)."""
    store.record_grade(grade, score, verdict)


def upsert_known_device(store: Any, mac: str, **kwargs: Any) -> None:
    """Insert/update a known_device row from a scan (wraps upsert_known_device)."""
    store.upsert_known_device(mac, **kwargs)


def record_speed_test(store: Any, **kwargs: Any) -> None:
    """Persist a speed-test result (wraps MetricStore.record_speed_test)."""
    store.record_speed_test(**kwargs)

"""Tests for modules/scan_persistence.py — module-layer boundary for
scan/background-driven MetricStore writes (ARCH RULE 1, #21).

These helpers are what the Dashboard scan-glue mixins (scan_wiring, scan_enrichment,
tabs, tabs_analysis, dashboard) call instead of touching MetricStore directly.
persist_alert() also collapses the six duplicated record_alert_fired(a.rule_name,
a.host, ...) call sites into one object-taking helper.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_import():
    from modules import scan_persistence
    for fn in (
        "record_rtt", "persist_alert", "record_mesh_snapshot", "record_modem_signal",
        "record_plugin_snapshot", "record_app_traffic_sample", "record_app_traffic_samples",
        "record_grade", "upsert_known_device", "record_speed_test",
    ):
        assert callable(getattr(scan_persistence, fn)), fn


def test_record_rtt_forwards():
    from modules.scan_persistence import record_rtt
    store = MagicMock()
    record_rtt(store, "192.168.1.10", 12.5)
    store.record_rtt.assert_called_once_with("192.168.1.10", 12.5)


def test_persist_alert_unpacks_object():
    from modules.scan_persistence import persist_alert
    store = MagicMock()
    store.record_alert_fired.return_value = 42
    alert = SimpleNamespace(
        rule_name="High RTT", host="10.0.0.1", severity="WARNING",
        message="rtt high", ts=1234, rule_type="RTT_THRESHOLD",
    )
    assert persist_alert(store, alert) == 42
    store.record_alert_fired.assert_called_once_with(
        "High RTT", "10.0.0.1", "WARNING", "rtt high",
        ts=1234, rule_type="RTT_THRESHOLD",
    )


def test_record_mesh_snapshot_forwards_kwargs():
    from modules.scan_persistence import record_mesh_snapshot
    store = MagicMock()
    record_mesh_snapshot(store, unit_count=3, online_count=2, worst_unit="node2", worst_rssi=-70)
    store.record_mesh_snapshot.assert_called_once_with(
        unit_count=3, online_count=2, worst_unit="node2", worst_rssi=-70
    )


def test_record_modem_signal_forwards_kwargs():
    from modules.scan_persistence import record_modem_signal
    store = MagicMock()
    record_modem_signal(store, network_type="5G", signal_bars=4)
    store.record_modem_signal.assert_called_once_with(network_type="5G", signal_bars=4)


def test_record_plugin_snapshot_forwards():
    from modules.scan_persistence import record_plugin_snapshot
    store = MagicMock()
    record_plugin_snapshot(store, "MyPlugin", {"k": "v"})
    store.record_plugin_snapshot.assert_called_once_with("MyPlugin", {"k": "v"})


def test_record_app_traffic_sample_forwards_kwargs():
    from modules.scan_persistence import record_app_traffic_sample
    store = MagicMock()
    record_app_traffic_sample(store, mac="aa:bb", label="L", category="C", app="A",
                              bytes_total=100, window_s=1.0)
    store.record_app_traffic_sample.assert_called_once_with(
        mac="aa:bb", label="L", category="C", app="A", bytes_total=100, window_s=1.0
    )


def test_record_app_traffic_samples_forwards():
    from modules.scan_persistence import record_app_traffic_samples
    store = MagicMock()
    samples = [{"mac": "aa:bb", "label": "L", "category": "C", "app": "A",
                "bytes_total": 100, "window_s": 1.0}]
    record_app_traffic_samples(store, samples)
    store.record_app_traffic_samples.assert_called_once_with(samples)


def test_record_grade_forwards():
    from modules.scan_persistence import record_grade
    store = MagicMock()
    record_grade(store, "A", 95.0, "healthy")
    store.record_grade.assert_called_once_with("A", 95.0, "healthy")


def test_upsert_known_device_forwards():
    from modules.scan_persistence import upsert_known_device
    store = MagicMock()
    upsert_known_device(store, "aa:bb", vendor="Acme")
    store.upsert_known_device.assert_called_once_with("aa:bb", vendor="Acme")


def test_record_speed_test_forwards_kwargs():
    from modules.scan_persistence import record_speed_test
    store = MagicMock()
    record_speed_test(store, download_mbps=100.0, upload_mbps=20.0, ping_ms=10.0)
    store.record_speed_test.assert_called_once_with(
        download_mbps=100.0, upload_mbps=20.0, ping_ms=10.0
    )


# ── Real-store integration ────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "sp.db")
    yield s
    s.close()


def test_persist_alert_against_real_store(store):
    from modules.alert_types import AlertFired
    from modules.scan_persistence import persist_alert
    a = AlertFired(rule_name="Grade Drop", rule_type="GRADE", host="lan",
                   message="grade fell", severity="WARNING", ts=int(time.time()))
    alert_id = persist_alert(store, a)
    assert isinstance(alert_id, int) and alert_id > 0
    recent = store.get_recent_alerts(hours=1)
    assert any(r["id"] == alert_id for r in recent)


def test_record_rtt_and_grade_against_real_store(store):
    from modules.scan_persistence import record_rtt, record_grade
    record_rtt(store, "192.168.1.1", 8.0)
    record_grade(store, "B", 82.0, "ok")
    # No exception + the grade row is retrievable
    assert store.query_last_grade() is not None

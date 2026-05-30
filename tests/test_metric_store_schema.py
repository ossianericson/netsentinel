"""Tests for modules/metric_store_schema.py — DDL, migrations, dataclasses."""
import sqlite3
import threading
import pytest

from modules.metric_store_schema import (
    _SCHEMA_VERSION, _DDL, _MIGRATIONS,
    apply_sqlite_schema,
    SpeedTestPoint, ServiceCheckPoint, RttPoint, DeviceStatePoint,
    DeviceEvent, CertCheckPoint, KnownDevice, HaDetectedPoint,
    ModemSignalPoint, MeshSignalPoint,
)


def _make_conn():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def test_schema_version_is_int():
    assert isinstance(_SCHEMA_VERSION, int)
    assert _SCHEMA_VERSION >= 8


def test_ddl_creates_core_tables():
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for expected in ("meta", "rtt_sample", "device_state", "device_event", "known_device",
                     "cert_check", "service_check", "speed_test", "cve_lifecycle",
                     "modem_signal_log", "mesh_signal_log", "plugin_log", "alert_fired"):
        assert expected in tables, f"Table '{expected}' not created"


def test_apply_schema_sets_version():
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    rows = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchall()
    assert rows
    assert int(rows[0][0]) == _SCHEMA_VERSION


def test_apply_schema_idempotent():
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    apply_sqlite_schema(conn, lock)  # second call must not raise


def test_migrations_list_is_nonempty():
    assert len(_MIGRATIONS) > 0
    assert all(isinstance(m, str) for m in _MIGRATIONS)


def test_rtt_point_dataclass():
    p = RttPoint(ts=1000, host="8.8.8.8", rtt_ms=14.2, loss_pct=0.0, jitter_ms=-1.0)
    assert p.ts == 1000
    assert p.host == "8.8.8.8"


def test_known_device_defaults():
    d = KnownDevice(
        mac="aa:bb:cc:dd:ee:ff",
        ip="192.168.1.1",
        hostname=None,
        vendor=None,
        device_type=None,
        first_seen=0,
        last_seen=0,
        is_authorized=True,
    )
    assert d.category == "unknown"
    assert d.is_pinned is False
    assert d.tags is None


def test_speed_test_point_optional_fields():
    p = SpeedTestPoint(
        ts=1000, download_mbps=100.0, upload_mbps=50.0, ping_ms=10.0,
        server_name=None, server_city=None, server_country=None,
    )
    assert p.nr5g_rsrp is None
    assert p.lte_band is None


def test_cert_check_point():
    c = CertCheckPoint(
        ts=1000, host="example.com", port=443,
        days_remaining=30, subject="CN=example.com",
        issuer="Let's Encrypt", not_after="2025-12-01",
        is_expired=False, is_self_signed=False, error=None,
    )
    assert c.host == "example.com"
    assert c.is_expired is False


def test_modem_signal_point():
    m = ModemSignalPoint(
        ts=1000, network_type="5G", signal_bars=4,
        cell_id="ABC", enb_id="123", mcc="234", mnc="30",
        wan_ip="1.2.3.4", nr5g_band="n78", nr5g_rsrp=-85.0,
        nr5g_sinr=15.0, nr5g_rsrq=-10.0, nr5g_pci=42, nr5g_arfcn=123456,
        lte_band="B3", lte_rsrp=-90.0, lte_snr=12.0, lte_rsrq=-11.0,
        lte_pci=100, lte_earfcn=1300,
    )
    assert m.network_type == "5G"
    assert m.nr5g_rsrp == -85.0

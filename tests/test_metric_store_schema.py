"""Tests for modules/metric_store_schema.py — DDL, migrations, dataclasses."""
import sqlite3
import threading

from modules.metric_store_schema import (
    _SCHEMA_VERSION, _MIGRATIONS,
    apply_sqlite_schema,
    SpeedTestPoint, RttPoint, CertCheckPoint, KnownDevice, ModemSignalPoint,
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
                     "modem_signal_log", "mesh_signal_log", "plugin_log", "alert_fired",
                     "daily_rollup"):
        assert expected in tables, f"Table '{expected}' not created"


def test_daily_rollup_table_has_expected_columns():
    """Stability Sprint 2 (G4): daily_rollup is the long-term trend survivor —
    raw rtt_sample rows die at 30 days, this table doesn't."""
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(daily_rollup)").fetchall()}
    assert cols == {"day", "metric", "host", "min", "avg", "max", "n"}


def test_daily_rollup_primary_key_prevents_duplicate_day_metric_host():
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    conn.execute(
        "INSERT INTO daily_rollup (day, metric, host, min, avg, max, n) "
        "VALUES ('2026-01-01', 'rtt_ms', 'host1', 1.0, 2.0, 3.0, 5)"
    )
    conn.commit()
    import sqlite3 as _sqlite3
    try:
        conn.execute(
            "INSERT INTO daily_rollup (day, metric, host, min, avg, max, n) "
            "VALUES ('2026-01-01', 'rtt_ms', 'host1', 9.0, 9.0, 9.0, 1)"
        )
        conn.commit()
        raised = False
    except _sqlite3.IntegrityError:
        raised = True
    assert raised


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


def test_schema_version_is_21():
    assert _SCHEMA_VERSION == 21


def test_known_device_has_hostname_resolved_at_column():
    """Part 2/L8: TTL hostname cache needs a per-device timestamp of the last
    ACTIVE name resolution (distinct from last_seen, which updates every scan
    regardless of whether resolution ran)."""
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(known_device)").fetchall()}
    assert "hostname_resolved_at" in cols


def test_migrated_from_v20_db_gains_hostname_resolved_at_column():
    """A DB with only the v20 known_device shape must gain the new nullable
    column (and report v21) the next time apply_sqlite_schema runs."""
    conn = _make_conn()
    lock = threading.Lock()
    conn.executescript(
        "CREATE TABLE known_device (mac TEXT PRIMARY KEY, last_seen INTEGER NOT NULL);"
    )
    conn.commit()
    apply_sqlite_schema(conn, lock)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(known_device)").fetchall()}
    assert "hostname_resolved_at" in cols
    rows = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchall()
    assert int(rows[0][0]) == 21


def test_known_device_hostname_resolved_at_defaults_to_none():
    kd = KnownDevice(
        mac="aa:bb:cc:dd:ee:ff", ip=None, hostname=None, vendor=None,
        device_type=None, first_seen=0, last_seen=0, is_authorized=True,
    )
    assert kd.hostname_resolved_at is None


def test_fresh_db_has_known_device_and_grade_result_indexes():
    """B3 (F6): known_device.last_seen and grade_result.ts get covering indexes
    so the existing ORDER BY queries (query_known_devices_summary,
    query_last_grade/query_previous_grade) don't do a full table scan+sort."""
    conn = _make_conn()
    lock = threading.Lock()
    apply_sqlite_schema(conn, lock)
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_known_device_last_seen" in indexes
    assert "idx_grade_result_ts" in indexes


def test_migrated_from_v19_db_gains_v20_indexes():
    """A DB that already has the v19 tables (no indexes on known_device/grade_result)
    must gain both indexes and report v20 the next time apply_sqlite_schema runs —
    the same idempotent executescript() that creates tables for a fresh DB also
    covers CREATE INDEX IF NOT EXISTS for an existing DB, no separate migration path."""
    conn = _make_conn()
    lock = threading.Lock()
    # Simulate a pre-v20 DB: tables exist, but no known_device/grade_result indexes.
    conn.executescript(
        """
        CREATE TABLE known_device (mac TEXT PRIMARY KEY, last_seen INTEGER NOT NULL);
        CREATE TABLE grade_result (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL);
        """
    )
    conn.commit()
    apply_sqlite_schema(conn, lock)
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_known_device_last_seen" in indexes
    assert "idx_grade_result_ts" in indexes
    rows = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchall()
    assert int(rows[0][0]) == _SCHEMA_VERSION


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

"""
MetricStore — persistent time-series database for NetSentinel.

Design:
  • Default backend: built-in sqlite3 (no extra dependencies).
  • Optional SQL backend: pass backend_url="postgresql://..." (requires SQLAlchemy).
  • WAL journal mode — safe for concurrent reads from multiple threads/processes.
  • Each calling thread gets its own sqlite3.Connection via threading.local().
  • All timestamps are stored as Unix integer seconds (UTC).
  • Auto-prune: records older than `retain_days` are deleted on open + on demand.

Schema, migrations, and dataclasses live in modules/metric_store_schema.py.
Read-only query methods live in modules/metric_store_queries.py (MetricStoreQueryMixin).

Usage:
    from modules.metric_store import MetricStore
    store = MetricStore()
    store.record_rtt("8.8.8.8", 14.2, 0.0)
    history = store.query_rtt_history("8.8.8.8", hours=24)
    store.close()

Architecture note (ARCH RULE 2):
  MetricStore is instantiated ONCE in app.py / svc.py and injected as a dependency.
  Never construct MetricStore inside a page widget or module.
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

# Re-export all schema symbols so `from modules.metric_store import SpeedTestPoint`
# continues to work for all existing callers.
from modules.metric_store_schema import (
    _SCHEMA_VERSION, _DDL,  # noqa: F401
    apply_sqlite_schema, apply_sqlalchemy_schema,
    CertCheckPoint, DeviceEvent, DeviceStatePoint, HaDetectedPoint,  # noqa: F401
    KnownDevice, MeshSignalPoint, ModemSignalPoint, RttPoint,  # noqa: F401
    ServiceCheckPoint, SpeedTestPoint,  # noqa: F401
)
from modules.metric_store_queries import MetricStoreQueryMixin, _default_db_path


class MetricStore(MetricStoreQueryMixin):
    """
    Thread-safe time-series store. Default backend is built-in sqlite3.

    Parameters
    ----------
    db_path : Path | str | None
        Explicit SQLite .db file path. Ignored when backend_url is set.
    retain_days : int
        Records older than this many days are pruned on open and on demand.
    backend_url : str | None
        SQLAlchemy URL for an external SQL database (requires: pip install sqlalchemy <driver>).
        When None (default), built-in sqlite3 is used.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        retain_days: int = 30,
        backend_url: Optional[str] = None,
    ):
        self._retain_days = retain_days
        self._backend_url = backend_url
        self._write_lock  = threading.Lock()

        if backend_url:
            self._backend   = "sqlalchemy"
            self._sa_engine = self._init_sqlalchemy(backend_url)
            self._local     = None
            self._db_path   = None
        else:
            self._backend   = "sqlite"
            self._db_path   = Path(db_path) if db_path else _default_db_path()
            self._local     = threading.local()
            self._sa_engine = None
            # S6-1: checkpoint WAL if it has grown large before opening
            self._checkpoint_wal_if_needed()

        self._init_schema()
        self.prune_old_data()

    # ── S6-1: WAL growth guard ────────────────────────────────────────────────

    def _checkpoint_wal_if_needed(self, threshold_bytes: int = 50 * 1024 * 1024) -> None:
        """Run PRAGMA wal_checkpoint(TRUNCATE) if the WAL file exceeds 50 MB."""
        if self._db_path is None:
            return
        wal_path = self._db_path.with_suffix(".db-wal")
        if not wal_path.exists():
            wal_path = Path(str(self._db_path) + "-wal")
        try:
            if wal_path.exists() and wal_path.stat().st_size > threshold_bytes:
                conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=10)
                conn.execute("PRAGMA busy_timeout = 5000")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
        except Exception:
            pass  # non-fatal

    # ── SQLAlchemy engine setup ───────────────────────────────────────────────

    def _init_sqlalchemy(self, url: str):
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:
            raise ImportError(
                "SQLAlchemy is required for external SQL backends. "
                "Run: pip install sqlalchemy"
            ) from exc
        return create_engine(url, pool_pre_ping=True, pool_size=5)

    # ── Connection management (sqlite backend) ────────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return (or create) a per-thread SQLite connection."""
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 5000;")  # S6-3: prevent OperationalError on contention
            self._local.conn = conn
        return self._local.conn

    def _sa_conn(self):
        return self._sa_engine.connect()

    def close(self):
        """Close the connection on the calling thread (sqlite backend only)."""
        if self._backend == "sqlite":
            conn = getattr(self._local, "conn", None)
            if conn:
                conn.close()
                self._local.conn = None

    # ── Schema init ───────────────────────────────────────────────────────────

    def _init_schema(self):
        if self._backend == "sqlalchemy":
            apply_sqlalchemy_schema(self._sa_engine)
        else:
            apply_sqlite_schema(self._conn, self._write_lock)

    # ── Write / read helpers ──────────────────────────────────────────────────

    def _execute_write(self, sql: str, params: tuple) -> None:
        if self._backend == "sqlalchemy":
            from sqlalchemy import text
            with self._write_lock:
                with self._sa_engine.begin() as conn:
                    conn.execute(text(sql), dict(enumerate(params)))
        else:
            with self._write_lock:
                self._conn.execute(sql, params)
                self._conn.commit()

    def _execute_read(self, sql: str, params: tuple = ()) -> list:
        if self._backend == "sqlalchemy":
            from sqlalchemy import text
            with self._sa_engine.connect() as conn:
                result = conn.execute(text(sql), dict(enumerate(params)))
                cols   = result.keys()
                return [dict(zip(cols, row)) for row in result.fetchall()]
        else:
            return self._conn.execute(sql, params).fetchall()

    # ── Write: RTT samples ────────────────────────────────────────────────────

    def record_rtt(
        self,
        host: str,
        rtt_ms: float,
        loss_pct: float = 0.0,
        jitter_ms: float = -1.0,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO rtt_sample(ts, host, rtt_ms, loss_pct, jitter_ms) "
            "VALUES(?, ?, ?, ?, ?)",
            (now, host, rtt_ms, loss_pct, jitter_ms),
        )

    # ── Write: device state snapshots ────────────────────────────────────────

    def record_device_state(
        self,
        ip: str,
        mac: Optional[str],
        hostname: Optional[str],
        state: str,
        rtt_ms: Optional[float] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO device_state(ts, ip, mac, hostname, state, rtt_ms) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (now, ip, mac, hostname, state.upper(), rtt_ms),
        )

    # ── Write: device events ──────────────────────────────────────────────────

    def record_device_event(
        self,
        ip: str,
        event_type: str,
        mac: Optional[str] = None,
        detail: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        _valid = {"JOINED", "LEFT", "UP", "DOWN", "DEGRADED", "RECOVERED"}
        if event_type.upper() not in _valid:
            raise ValueError(f"event_type must be one of {_valid}, got {event_type!r}")
        self._execute_write(
            "INSERT INTO device_event(ts, ip, mac, event_type, detail) "
            "VALUES(?, ?, ?, ?, ?)",
            (now, ip, mac, event_type.upper(), detail),
        )

    # ── Write: known device inventory ─────────────────────────────────────────

    def upsert_known_device(
        self,
        mac: str,
        ip: Optional[str] = None,
        hostname: Optional[str] = None,
        vendor: Optional[str] = None,
        device_type: Optional[str] = None,
        is_authorized: Optional[bool] = True,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        auth_val: Optional[int] = None if is_authorized is None else int(is_authorized)
        self._execute_write(
            """
            INSERT INTO known_device
                (mac, ip, hostname, vendor, device_type,
                 first_seen, last_seen, is_authorized)
            VALUES(?, ?, ?, ?, ?, ?, ?, COALESCE(?, 1))
            ON CONFLICT(mac) DO UPDATE SET
                ip           = excluded.ip,
                hostname     = COALESCE(excluded.hostname, hostname),
                vendor       = COALESCE(excluded.vendor,   vendor),
                device_type  = COALESCE(excluded.device_type, device_type),
                last_seen    = excluded.last_seen,
                is_authorized = CASE WHEN ? IS NULL THEN is_authorized
                                     ELSE ? END
            """,
            (mac, ip, hostname, vendor, device_type, now, now, auth_val,
             auth_val, auth_val),
        )

    def set_device_authorized(self, mac: str, authorized: bool) -> None:
        self._execute_write(
            "UPDATE known_device SET is_authorized = ? WHERE mac = ?",
            (int(authorized), mac),
        )

    # ── Write: TLS certificate checks ─────────────────────────────────────────

    def record_cert_check(
        self,
        host: str,
        port: int = 443,
        days_remaining: Optional[int] = None,
        subject: Optional[str] = None,
        issuer: Optional[str] = None,
        not_after: Optional[str] = None,
        is_expired: bool = False,
        is_self_signed: bool = False,
        error: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO cert_check "
            "(ts, host, port, days_remaining, subject, issuer, not_after, "
            " is_expired, is_self_signed, error) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, host, port, days_remaining, subject, issuer, not_after,
             int(is_expired), int(is_self_signed), error),
        )

    # ── Write: service / port heartbeat checks ────────────────────────────────

    def record_service_check(
        self,
        host: str,
        port: int,
        up: bool,
        rtt_ms: Optional[float] = None,
        label: Optional[str] = None,
        error: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO service_check(ts, host, port, label, up, rtt_ms, error) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (now, host, port, label, int(up), rtt_ms, error),
        )

    # ── Write: Home Automation ─────────────────────────────────────────────────

    def update_device_ha_info(
        self,
        mac: str,
        custom_name: Optional[str] = None,
        room: Optional[str] = None,
        category: Optional[str] = None,
        notes: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        tags: Optional[str] = None,
    ) -> None:
        sets, params = [], []
        if custom_name is not None:
            sets.append("custom_name = ?"); params.append(custom_name)
        if room is not None:
            sets.append("room = ?"); params.append(room)
        if category is not None:
            sets.append("category = ?"); params.append(category)
        if notes is not None:
            sets.append("notes = ?"); params.append(notes)
        if is_pinned is not None:
            sets.append("is_pinned = ?"); params.append(int(is_pinned))
        if tags is not None:
            sets.append("tags = ?"); params.append(tags)
        if not sets:
            return
        params.append(mac)
        self._execute_write(
            f"UPDATE known_device SET {', '.join(sets)} WHERE mac = ?",
            tuple(params),
        )

    def record_ha_detected(
        self,
        ip: str,
        ha_type: str,
        mac: Optional[str] = None,
        confidence: str = "medium",
        detail: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO ha_detected(ts, ip, mac, ha_type, confidence, detail) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (now, ip, mac, ha_type, confidence, detail),
        )

    # ── Write: speed test results ─────────────────────────────────────────────

    def record_speed_test(
        self,
        download_mbps: float,
        upload_mbps: float,
        ping_ms: float,
        server_name: Optional[str] = None,
        server_city: Optional[str] = None,
        server_country: Optional[str] = None,
        ts: Optional[int] = None,
        network_type: Optional[str] = None,
        signal_bars: Optional[int] = None,
        nr5g_rsrp: Optional[float] = None,
        nr5g_sinr: Optional[float] = None,
        nr5g_band: Optional[str] = None,
        lte_rsrp: Optional[float] = None,
        lte_band: Optional[str] = None,
        cell_id: Optional[str] = None,
        enb_id: Optional[str] = None,
        mcc: Optional[str] = None,
        mnc: Optional[str] = None,
        wan_ip: Optional[str] = None,
        nr5g_rsrq: Optional[float] = None,
        nr5g_pci: Optional[int] = None,
        nr5g_arfcn: Optional[int] = None,
        lte_snr: Optional[float] = None,
        lte_rsrq: Optional[float] = None,
        lte_pci: Optional[int] = None,
        lte_earfcn: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO speed_test "
            "(ts, download_mbps, upload_mbps, ping_ms, server_name, server_city, server_country,"
            " network_type, signal_bars, nr5g_rsrp, nr5g_sinr, nr5g_band, lte_rsrp, lte_band,"
            " cell_id, enb_id, mcc, mnc, wan_ip,"
            " nr5g_rsrq, nr5g_pci, nr5g_arfcn, lte_snr, lte_rsrq, lte_pci, lte_earfcn) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, download_mbps, upload_mbps, ping_ms, server_name, server_city, server_country,
             network_type, signal_bars, nr5g_rsrp, nr5g_sinr, nr5g_band, lte_rsrp, lte_band,
             cell_id, enb_id, mcc, mnc, wan_ip,
             nr5g_rsrq, nr5g_pci, nr5g_arfcn, lte_snr, lte_rsrq, lte_pci, lte_earfcn),
        )

    # ── Write: CVE lifecycle tracker ──────────────────────────────────────────

    def upsert_cve_lifecycle(
        self,
        cve_id: str,
        service: str,
        host: str,
        cvss_score: float,
        severity: str,
        description: str,
        state: str = "Open",
        owner: str = "",
        notes: str = "",
        ts: Optional[int] = None,
    ) -> int:
        now = ts or int(time.time())
        rows = self._execute_read(
            "SELECT id FROM cve_lifecycle WHERE cve_id=? AND host=? AND service=?",
            (cve_id, host, service),
        )
        if rows:
            row_id = rows[0]["id"]
            self._execute_write(
                "UPDATE cve_lifecycle SET cvss_score=?, severity=?, description=?, "
                "updated_ts=? WHERE id=?",
                (cvss_score, severity, description, now, row_id),
            )
            return row_id
        else:
            self._execute_write(
                "INSERT INTO cve_lifecycle "
                "(cve_id, service, host, state, owner, notes, cvss_score, severity, "
                "description, opened_ts, updated_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (cve_id, service, host, state, owner, notes,
                 cvss_score, severity, description, now, now),
            )
            rows2 = self._execute_read(
                "SELECT id FROM cve_lifecycle WHERE cve_id=? AND host=? AND service=?",
                (cve_id, host, service),
            )
            return rows2[0]["id"] if rows2 else -1

    def update_cve_state(
        self,
        row_id: int,
        state: str,
        owner: str = "",
        notes: str = "",
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "UPDATE cve_lifecycle SET state=?, owner=?, notes=?, updated_ts=? WHERE id=?",
            (state, owner, notes, now, row_id),
        )

    def delete_cve_lifecycle(self, row_id: int) -> None:
        self._execute_write("DELETE FROM cve_lifecycle WHERE id=?", (row_id,))

    # ── Write: Alert fired / acknowledgement tracker ───────────────────────────

    def record_alert_fired(
        self,
        rule_name: str,
        host: str,
        severity: str,
        message: str,
        ts: Optional[int] = None,
    ) -> int:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO alert_fired (ts, rule_name, host, severity, message) "
            "VALUES(?,?,?,?,?)",
            (now, rule_name, host, severity, message),
        )
        rows = self._execute_read(
            "SELECT id FROM alert_fired WHERE ts=? AND rule_name=? AND host=? ORDER BY id DESC LIMIT 1",
            (now, rule_name, host),
        )
        return rows[0]["id"] if rows else -1

    def acknowledge_alert(self, alert_id: int, acked_by: str = "user", ts: Optional[int] = None) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "UPDATE alert_fired SET acked_ts=?, acked_by=? WHERE id=?",
            (now, acked_by, alert_id),
        )

    def mark_alert_escalated(self, alert_id: int) -> None:
        self._execute_write(
            "UPDATE alert_fired SET escalated=1 WHERE id=?",
            (alert_id,),
        )

    # ── Write: modem / mesh signal logs ───────────────────────────────────────

    def record_modem_signal(
        self,
        ts: Optional[int] = None,
        network_type: Optional[str] = None,
        signal_bars: Optional[int] = None,
        cell_id: Optional[str] = None,
        enb_id: Optional[str] = None,
        mcc: Optional[str] = None,
        mnc: Optional[str] = None,
        wan_ip: Optional[str] = None,
        nr5g_band: Optional[str] = None,
        nr5g_rsrp: Optional[float] = None,
        nr5g_sinr: Optional[float] = None,
        nr5g_rsrq: Optional[float] = None,
        nr5g_pci: Optional[int] = None,
        nr5g_arfcn: Optional[int] = None,
        lte_band: Optional[str] = None,
        lte_rsrp: Optional[float] = None,
        lte_snr: Optional[float] = None,
        lte_rsrq: Optional[float] = None,
        lte_pci: Optional[int] = None,
        lte_earfcn: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO modem_signal_log "
            "(ts, network_type, signal_bars, cell_id, enb_id, mcc, mnc, wan_ip,"
            " nr5g_band, nr5g_rsrp, nr5g_sinr, nr5g_rsrq, nr5g_pci, nr5g_arfcn,"
            " lte_band, lte_rsrp, lte_snr, lte_rsrq, lte_pci, lte_earfcn) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, network_type, signal_bars, cell_id, enb_id, mcc, mnc, wan_ip,
             nr5g_band, nr5g_rsrp, nr5g_sinr, nr5g_rsrq, nr5g_pci, nr5g_arfcn,
             lte_band, lte_rsrp, lte_snr, lte_rsrq, lte_pci, lte_earfcn),
        )

    def record_mesh_snapshot(
        self,
        unit_count: int,
        online_count: int,
        worst_unit: Optional[str] = None,
        worst_rssi: Optional[float] = None,
        ts: Optional[int] = None,
    ) -> None:
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO mesh_signal_log (ts, unit_count, online_count, worst_unit, worst_rssi) "
            "VALUES(?, ?, ?, ?, ?)",
            (now, unit_count, online_count, worst_unit, worst_rssi),
        )

    def record_plugin_snapshot(self, plugin_name: str, data: dict) -> None:
        import json
        self._execute_write(
            "INSERT INTO plugin_log (ts, plugin_name, data) VALUES (?, ?, ?)",
            (int(time.time()), plugin_name, json.dumps(data, default=str)),
        )

    # ── Write: config snapshot CRUD ───────────────────────────────────────────

    def store_snapshot(self, ts: int, label: str, data_json: str) -> int:
        with self._write_lock:
            if self._backend == "sqlalchemy":
                from sqlalchemy import text
                with self._sa_engine.begin() as conn:
                    result = conn.execute(
                        text("INSERT INTO config_snapshot (ts, label, data_json) "
                             "VALUES (:ts, :label, :data)"),
                        {"ts": ts, "label": label, "data": data_json},
                    )
                    return result.lastrowid  # type: ignore[return-value]
            else:
                cur = self._conn.execute(
                    "INSERT INTO config_snapshot (ts, label, data_json) VALUES (?,?,?)",
                    (ts, label, data_json),
                )
                self._conn.commit()
                return cur.lastrowid  # type: ignore[return-value]

    def delete_snapshot(self, snapshot_id: int) -> None:
        self._execute_write(
            "DELETE FROM config_snapshot WHERE id = ?", (snapshot_id,)
        )

    # ── Write: grade result ───────────────────────────────────────────────────

    def record_grade(self, grade: str, score: float, verdict: str) -> None:
        import time as _time
        self._execute_write("DELETE FROM grade_result", ())
        self._execute_write(
            "INSERT INTO grade_result(ts, grade, score, verdict) VALUES(?, ?, ?, ?)",
            (int(_time.time()), grade, score, verdict),
        )


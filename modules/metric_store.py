"""
MetricStore — persistent time-series database for NetSentinel.

Stores:
  • RTT / packet-loss samples per host (table: rtt_sample)
  • Device availability state snapshots (table: device_state)
  • Device change events: JOINED / LEFT / UP / DOWN / RECOVERED (table: device_event)
  • Known-device inventory (table: known_device)

Design:
  • Default backend: built-in sqlite3 (no extra dependencies).
  • Optional SQL backend: pass backend_url="postgresql://..." (requires SQLAlchemy).
    The public API is identical regardless of backend — callers never touch sqlite3 directly.
  • WAL journal mode — safe for concurrent reads from multiple threads/processes.
  • Each calling thread gets its own sqlite3.Connection via threading.local().
  • All timestamps are stored as Unix integer seconds (UTC).
  • Auto-prune: records older than `retain_days` are deleted on open + on demand.

Usage:
    from modules.metric_store import MetricStore

    # Default (SQLite, auto-located):
    store = MetricStore()

    # Explicit SQLite path:
    store = MetricStore(db_path="/data/netsentinel.db")

    # External SQL database (requires: pip install sqlalchemy psycopg2):
    store = MetricStore(backend_url="postgresql://user:pass@localhost/netsentinel")

    store.record_rtt("8.8.8.8", 14.2, 0.0)
    store.record_device_state("192.168.1.1", "aa:bb:cc", "router", "UP", 1.2)
    history = store.query_rtt_history("8.8.8.8", hours=24)
    store.close()

Architecture note (ARCH RULE 2 + 7):
  MetricStore is instantiated ONCE in app.py / svc.py and injected as a dependency.
  Never construct MetricStore inside a page widget or module.
  All database access goes through this API — never call sqlite3 directly elsewhere.
"""

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Schema version — bump when adding columns ────────────────────────────────
_SCHEMA_VERSION = 7

# ── DDL ──────────────────────────────────────────────────────────────────────
_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Per-host RTT / packet-loss samples
CREATE TABLE IF NOT EXISTS rtt_sample (
    id        INTEGER PRIMARY KEY,
    ts        INTEGER NOT NULL,
    host      TEXT    NOT NULL,
    rtt_ms    REAL    NOT NULL,   -- -1.0 = unreachable
    loss_pct  REAL    NOT NULL DEFAULT 0.0,
    jitter_ms REAL    NOT NULL DEFAULT -1.0
);
CREATE INDEX IF NOT EXISTS idx_rtt_ts   ON rtt_sample(ts);
CREATE INDEX IF NOT EXISTS idx_rtt_host ON rtt_sample(host, ts);

-- Per-device availability snapshots
CREATE TABLE IF NOT EXISTS device_state (
    id       INTEGER PRIMARY KEY,
    ts       INTEGER NOT NULL,
    ip       TEXT    NOT NULL,
    mac      TEXT,
    hostname TEXT,
    state    TEXT    NOT NULL,   -- UP / DEGRADED / DOWN
    rtt_ms   REAL
);
CREATE INDEX IF NOT EXISTS idx_ds_ts ON device_state(ts);
CREATE INDEX IF NOT EXISTS idx_ds_ip ON device_state(ip, ts);

-- Device change events
CREATE TABLE IF NOT EXISTS device_event (
    id         INTEGER PRIMARY KEY,
    ts         INTEGER NOT NULL,
    ip         TEXT    NOT NULL,
    mac        TEXT,
    event_type TEXT    NOT NULL,  -- JOINED / LEFT / UP / DOWN / DEGRADED / RECOVERED
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_de_ts ON device_event(ts);

-- Known-device inventory (one row per MAC — upserted on every scan)
CREATE TABLE IF NOT EXISTS known_device (
    mac          TEXT    PRIMARY KEY,
    ip           TEXT,
    hostname     TEXT,
    vendor       TEXT,
    device_type  TEXT,
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    is_authorized INTEGER NOT NULL DEFAULT 1,
    -- Home Automation Hub fields (schema v6)
    custom_name  TEXT,
    room         TEXT,
    category     TEXT    NOT NULL DEFAULT 'unknown',
    notes        TEXT,
    is_pinned    INTEGER NOT NULL DEFAULT 0
);

-- Home Automation detected protocol signatures (schema v6)
CREATE TABLE IF NOT EXISTS ha_detected (
    id           INTEGER PRIMARY KEY,
    ts           INTEGER NOT NULL,
    ip           TEXT    NOT NULL,
    mac          TEXT,
    ha_type      TEXT    NOT NULL,  -- home_assistant | hue_bridge | mqtt_broker | sonos | etc.
    confidence   TEXT    NOT NULL DEFAULT 'medium',  -- high | medium | low
    detail       TEXT
);
CREATE INDEX IF NOT EXISTS idx_ha_ts  ON ha_detected(ts);
CREATE INDEX IF NOT EXISTS idx_ha_ip  ON ha_detected(ip);

-- TLS certificate check results
CREATE TABLE IF NOT EXISTS cert_check (
    id             INTEGER PRIMARY KEY,
    ts             INTEGER NOT NULL,
    host           TEXT    NOT NULL,
    port           INTEGER NOT NULL DEFAULT 443,
    days_remaining INTEGER,
    subject        TEXT,
    issuer         TEXT,
    not_after      TEXT,
    is_expired     INTEGER NOT NULL DEFAULT 0,
    is_self_signed INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
CREATE INDEX IF NOT EXISTS idx_cc_ts   ON cert_check(ts);
CREATE INDEX IF NOT EXISTS idx_cc_host ON cert_check(host, port, ts);

-- Service / port heartbeat check results
CREATE TABLE IF NOT EXISTS service_check (
    id      INTEGER PRIMARY KEY,
    ts      INTEGER NOT NULL,
    host    TEXT    NOT NULL,
    port    INTEGER NOT NULL,
    label   TEXT,
    up      INTEGER NOT NULL DEFAULT 0,   -- 1 = port responded
    rtt_ms  REAL,                         -- connect latency; NULL if unreachable
    error   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sc_ts   ON service_check(ts);
CREATE INDEX IF NOT EXISTS idx_sc_host ON service_check(host, port, ts);

-- Configuration baseline snapshots
CREATE TABLE IF NOT EXISTS config_snapshot (
    id         INTEGER PRIMARY KEY,
    ts         INTEGER NOT NULL,
    label      TEXT    NOT NULL DEFAULT '',
    data_json  TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_csnap_ts ON config_snapshot(ts);

-- Internet speed test results
CREATE TABLE IF NOT EXISTS speed_test (
    id              INTEGER PRIMARY KEY,
    ts              INTEGER NOT NULL,
    download_mbps   REAL    NOT NULL,
    upload_mbps     REAL    NOT NULL,
    ping_ms         REAL    NOT NULL,
    server_name     TEXT,
    server_city     TEXT,
    server_country  TEXT
);
CREATE INDEX IF NOT EXISTS idx_st_ts ON speed_test(ts);

-- CVE lifecycle tracker (schema v7)
-- Tracks the remediation state of discovered CVEs per host/service
CREATE TABLE IF NOT EXISTS cve_lifecycle (
    id          INTEGER PRIMARY KEY,
    cve_id      TEXT    NOT NULL,
    service     TEXT    NOT NULL DEFAULT '',
    host        TEXT    NOT NULL DEFAULT '',
    state       TEXT    NOT NULL DEFAULT 'Open',
    owner       TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    cvss_score  REAL    NOT NULL DEFAULT 0.0,
    severity    TEXT    NOT NULL DEFAULT '',
    description TEXT    NOT NULL DEFAULT '',
    opened_ts   INTEGER NOT NULL,
    updated_ts  INTEGER NOT NULL,
    UNIQUE(cve_id, host, service)
);
CREATE INDEX IF NOT EXISTS idx_cvl_state ON cve_lifecycle(state);
CREATE INDEX IF NOT EXISTS idx_cvl_cve   ON cve_lifecycle(cve_id);

-- Alert acknowledgement + escalation tracking (schema v7)
CREATE TABLE IF NOT EXISTS alert_fired (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,
    rule_name   TEXT    NOT NULL,
    host        TEXT    NOT NULL DEFAULT '',
    severity    TEXT    NOT NULL DEFAULT 'WARNING',
    message     TEXT    NOT NULL DEFAULT '',
    acked_ts    INTEGER,
    acked_by    TEXT,
    escalated   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_af_ts    ON alert_fired(ts);
CREATE INDEX IF NOT EXISTS idx_af_acked ON alert_fired(acked_ts);
"""


# ── Return types ─────────────────────────────────────────────────────────────

@dataclass
class SpeedTestPoint:
    ts:             int
    download_mbps:  float
    upload_mbps:    float
    ping_ms:        float
    server_name:    Optional[str]
    server_city:    Optional[str]
    server_country: Optional[str]


@dataclass
class ServiceCheckPoint:
    ts:     int
    host:   str
    port:   int
    label:  Optional[str]
    up:     bool
    rtt_ms: Optional[float]
    error:  Optional[str]


@dataclass
class RttPoint:
    ts: int           # Unix seconds
    host: str         # target hostname or IP
    rtt_ms: float     # -1.0 = unreachable
    loss_pct: float
    jitter_ms: float


@dataclass
class DeviceStatePoint:
    ts: int
    ip: str
    mac: Optional[str]
    hostname: Optional[str]
    state: str        # UP / DEGRADED / DOWN
    rtt_ms: Optional[float]


@dataclass
class DeviceEvent:
    ts: int
    ip: str
    mac: Optional[str]
    event_type: str
    detail: Optional[str]


@dataclass
class CertCheckPoint:
    ts:             int
    host:           str
    port:           int
    days_remaining: Optional[int]
    subject:        Optional[str]
    issuer:         Optional[str]
    not_after:      Optional[str]
    is_expired:     bool
    is_self_signed: bool
    error:          Optional[str]


@dataclass
class KnownDevice:
    mac: str
    ip: Optional[str]
    hostname: Optional[str]
    vendor: Optional[str]
    device_type: Optional[str]
    first_seen: int
    last_seen: int
    is_authorized: bool
    # Home Automation Hub fields (schema v6)
    custom_name: Optional[str] = None
    room: Optional[str] = None
    category: str = "unknown"
    notes: Optional[str] = None
    is_pinned: bool = False


@dataclass
class HaDetectedPoint:
    id: int
    ts: int
    ip: str
    mac: Optional[str]
    ha_type: str       # home_assistant | hue_bridge | mqtt_broker | sonos …
    confidence: str    # high | medium | low
    detail: Optional[str]


# ── MetricStore ───────────────────────────────────────────────────────────────

class MetricStore:
    """
    Thread-safe time-series store. Default backend is built-in sqlite3.

    Parameters
    ----------
    db_path : Path | str | None
        Explicit path to the SQLite .db file. Ignored when backend_url is set.
        If None, the file is created next to NetSentinel.ini (portable-first).
    retain_days : int
        Records older than this many days are pruned on open and on demand.
    backend_url : str | None
        SQLAlchemy connection URL for an external SQL database.
        Examples:
          "postgresql://user:pass@localhost/netsentinel"
          "mysql+pymysql://user:pass@localhost/netsentinel"
        When set, db_path is ignored and SQLAlchemy is used for all operations.
        Requires: pip install sqlalchemy <driver>
        When None (default), built-in sqlite3 is used — no extra dependencies.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        retain_days: int = 30,
        backend_url: Optional[str] = None,
    ):
        self._retain_days = retain_days
        self._backend_url = backend_url
        self._write_lock  = threading.Lock()   # within-process write serialisation

        if backend_url:
            self._backend = "sqlalchemy"
            self._sa_engine = self._init_sqlalchemy(backend_url)
            self._local     = None             # not used for SQLAlchemy path
        else:
            self._backend   = "sqlite"
            self._db_path   = Path(db_path) if db_path else self._default_path()
            self._local     = threading.local()
            self._sa_engine = None

        self._init_schema()
        self.prune_old_data()

    # ── SQLAlchemy engine setup ───────────────────────────────────────────────

    def _init_sqlalchemy(self, url: str):
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:
            raise ImportError(
                "SQLAlchemy is required for external SQL backends. "
                "Run: pip install sqlalchemy"
            ) from exc
        engine = create_engine(url, pool_pre_ping=True, pool_size=5)
        return engine

    # ── Connection management (sqlite backend) ───────────────────────────────

    @property
    def _conn(self) -> sqlite3.Connection:
        """Return (or create) a per-thread SQLite connection. sqlite backend only."""
        if not getattr(self._local, "conn", None):
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            self._local.conn = conn
        return self._local.conn

    def _sa_conn(self):
        """Return a SQLAlchemy connection context manager. sqlalchemy backend only."""
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
            self._init_schema_sqlalchemy()
        else:
            self._init_schema_sqlite()

    def _init_schema_sqlite(self):
        with self._write_lock:
            conn = self._conn
            conn.executescript(_DDL)
            # Schema v6 migration: add HA columns to existing known_device rows
            for col_def in [
                "ALTER TABLE known_device ADD COLUMN custom_name TEXT",
                "ALTER TABLE known_device ADD COLUMN room TEXT",
                "ALTER TABLE known_device ADD COLUMN category TEXT NOT NULL DEFAULT 'unknown'",
                "ALTER TABLE known_device ADD COLUMN notes TEXT",
                "ALTER TABLE known_device ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0",
            ]:
                try:
                    conn.execute(col_def)
                except sqlite3.OperationalError:
                    pass  # column already exists
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("schema_version", str(_SCHEMA_VERSION)),
            )
            conn.commit()

    def _init_schema_sqlalchemy(self):
        """Create tables via SQLAlchemy text DDL (strips PRAGMA for non-SQLite)."""
        from sqlalchemy import text
        # Remove SQLite-specific PRAGMAs before sending to other engines
        sa_ddl = "\n".join(
            line for line in _DDL.splitlines()
            if not line.strip().upper().startswith("PRAGMA")
        )
        # Use AUTOINCREMENT equivalent: SQLAlchemy will handle INTEGER PRIMARY KEY
        with self._sa_engine.begin() as conn:
            for statement in sa_ddl.split(";"):
                stmt = statement.strip()
                if stmt:
                    try:
                        conn.execute(text(stmt))
                    except Exception:
                        pass  # table already exists

    # ── Write helpers ─────────────────────────────────────────────────────────

    def _execute_write(self, sql: str, params: tuple) -> None:
        """Execute a write statement on whichever backend is active."""
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
        """Execute a read query and return rows as sqlite3.Row-compatible dicts."""
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
        """Record a single RTT measurement for a host."""
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
        """Record a device availability snapshot (UP / DEGRADED / DOWN)."""
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO device_state(ts, ip, mac, hostname, state, rtt_ms) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (now, ip, mac, hostname, state.upper(), rtt_ms),
        )

    # ── Write: device events ─────────────────────────────────────────────────

    def record_device_event(
        self,
        ip: str,
        event_type: str,
        mac: Optional[str] = None,
        detail: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        """Record a discrete device event (JOINED / LEFT / DOWN / RECOVERED …)."""
        now = ts or int(time.time())
        _valid = {"JOINED", "LEFT", "UP", "DOWN", "DEGRADED", "RECOVERED"}
        if event_type.upper() not in _valid:
            raise ValueError(f"event_type must be one of {_valid}, got {event_type!r}")
        self._execute_write(
            "INSERT INTO device_event(ts, ip, mac, event_type, detail) "
            "VALUES(?, ?, ?, ?, ?)",
            (now, ip, mac, event_type.upper(), detail),
        )

    # ── Write: known device inventory ────────────────────────────────────────

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
        """Insert or update the inventory row for a MAC address.

        Pass ``is_authorized=None`` to preserve the existing value on conflict.
        """
        now = ts or int(time.time())
        # None → preserve existing authorization; otherwise convert to int
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
        """Mark a device as authorized or unauthorized in the inventory."""
        self._execute_write(
            "UPDATE known_device SET is_authorized = ? WHERE mac = ?",
            (int(authorized), mac),
        )

    # ── Write: TLS certificate checks ────────────────────────────────────

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
        """Record the result of a TLS certificate check for host:port."""
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO cert_check "
            "(ts, host, port, days_remaining, subject, issuer, not_after, "
            " is_expired, is_self_signed, error) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, host, port, days_remaining, subject, issuer, not_after,
             int(is_expired), int(is_self_signed), error),
        )

    # ── Read: TLS certificate checks ────────────────────────────────────

    def query_cert_status(self, hours: float = 168.0) -> List[CertCheckPoint]:
        """
        Return the latest cert check per (host, port) within the last `hours`.
        Sorted by host then port.
        """
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            """
            SELECT ts, host, port, days_remaining, subject, issuer,
                   not_after, is_expired, is_self_signed, error
            FROM cert_check
            WHERE ts >= ?
              AND id IN (
                  SELECT MAX(id) FROM cert_check
                  WHERE ts >= ?
                  GROUP BY host, port
              )
            ORDER BY host, port
            """,
            (since, since),
        )
        return [self._row_to_cert(r) for r in rows]

    def query_cert_history(
        self,
        host: str,
        port: int = 443,
        hours: float = 168.0,
    ) -> List[CertCheckPoint]:
        """Return all cert checks for host:port over the last `hours` hours, oldest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, host, port, days_remaining, subject, issuer, "
            "not_after, is_expired, is_self_signed, error "
            "FROM cert_check WHERE host = ? AND port = ? AND ts >= ? "
            "ORDER BY ts ASC",
            (host, port, since),
        )
        return [self._row_to_cert(r) for r in rows]

    @staticmethod
    def _row_to_cert(r) -> "CertCheckPoint":
        return CertCheckPoint(
            ts=r["ts"], host=r["host"], port=r["port"],
            days_remaining=r["days_remaining"],
            subject=r["subject"], issuer=r["issuer"],
            not_after=r["not_after"],
            is_expired=bool(r["is_expired"]),
            is_self_signed=bool(r["is_self_signed"]),
            error=r["error"],
        )

    # ── Write: service / port heartbeat checks ───────────────────────────────

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
        """Record the result of a TCP service/port reachability check."""
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO service_check(ts, host, port, label, up, rtt_ms, error) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (now, host, port, label, int(up), rtt_ms, error),
        )

    # ── Read: service / port heartbeat checks ────────────────────────────────

    def query_service_status(self, hours: float = 24.0) -> List["ServiceCheckPoint"]:
        """
        Return the latest check result per (host, port) within the last `hours`.
        Sorted by host then port.
        """
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            """
            SELECT ts, host, port, label, up, rtt_ms, error
            FROM service_check
            WHERE ts >= ?
              AND id IN (
                  SELECT MAX(id) FROM service_check
                  WHERE ts >= ?
                  GROUP BY host, port
              )
            ORDER BY host, port
            """,
            (since, since),
        )
        return [self._row_to_svc(r) for r in rows]

    def query_service_history(
        self,
        host: str,
        port: int,
        hours: float = 24.0,
    ) -> List["ServiceCheckPoint"]:
        """Return all checks for host:port over the last `hours` hours, oldest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, host, port, label, up, rtt_ms, error "
            "FROM service_check WHERE host = ? AND port = ? AND ts >= ? "
            "ORDER BY ts ASC",
            (host, port, since),
        )
        return [self._row_to_svc(r) for r in rows]

    def query_all_service_targets(self) -> List[tuple]:
        """Return distinct (host, port, label) tuples from recent checks."""
        rows = self._execute_read(
            "SELECT DISTINCT host, port, label FROM service_check "
            "ORDER BY host, port",
            (),
        )
        return [(r["host"], r["port"], r["label"]) for r in rows]

    @staticmethod
    def _row_to_svc(r) -> "ServiceCheckPoint":
        return ServiceCheckPoint(
            ts=r["ts"], host=r["host"], port=r["port"], label=r["label"],
            up=bool(r["up"]), rtt_ms=r["rtt_ms"], error=r["error"],
        )

    # ── Read: RTT history ────────────────────────────────────────────────────

    def query_rtt_history(
        self,
        host: str,
        hours: float = 24.0,
    ) -> List[RttPoint]:
        """Return RTT samples for `host` over the last `hours` hours, oldest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, host, rtt_ms, loss_pct, jitter_ms FROM rtt_sample "
            "WHERE host = ? AND ts >= ? ORDER BY ts ASC",
            (host, since),
        )
        return [RttPoint(r["ts"], r["host"], r["rtt_ms"], r["loss_pct"], r["jitter_ms"])
                for r in rows]

    def query_all_rtt_hosts(self, hours: float = 24.0) -> List[str]:
        """Return the distinct host names that have RTT samples in the window."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT DISTINCT host FROM rtt_sample WHERE ts >= ?", (since,)
        )
        return [r["host"] for r in rows]

    def query_all_state_ips(self, hours: float = 720.0) -> List[str]:
        """Return the distinct IPs that have device_state samples in the window."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT DISTINCT ip FROM device_state WHERE ts >= ?", (since,)
        )
        return [r["ip"] for r in rows]

    def query_uptime_table(
        self,
        hours_list: Optional[List[float]] = None,
    ) -> List[Dict]:
        """
        Return one row per monitored IP with uptime % for each window in hours_list.

        Default windows: [24.0, 168.0, 720.0]  (1d, 7d, 30d)

        Each row is a dict:
          {
            "ip":       str,
            "hostname": str | None,    # most recent hostname from device_state
            "24h":      float,         # uptime % over last 24h
            "7d":       float,
            "30d":      float,
          }
        """
        if hours_list is None:
            hours_list = [24.0, 168.0, 720.0]
        # Use 30d as the discovery window
        ips = self.query_all_state_ips(hours=720.0)
        rows = []
        for ip in ips:
            # Most recent hostname
            hn_rows = self._execute_read(
                "SELECT hostname FROM device_state WHERE ip = ? AND hostname IS NOT NULL "
                "ORDER BY ts DESC LIMIT 1",
                (ip,),
            )
            hostname = hn_rows[0]["hostname"] if hn_rows else None
            entry: Dict = {"ip": ip, "hostname": hostname}
            for h in hours_list:
                entry[str(h)] = self.query_uptime_pct(ip, hours=h)
            rows.append(entry)
        return rows

    # ── Read: device state history ───────────────────────────────────────────

    def query_device_state_history(
        self,
        ip: str,
        hours: float = 24.0,
    ) -> List[DeviceStatePoint]:
        """Return device state snapshots for `ip` over the last `hours` hours."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, ip, mac, hostname, state, rtt_ms FROM device_state "
            "WHERE ip = ? AND ts >= ? ORDER BY ts ASC",
            (ip, since),
        )
        return [
            DeviceStatePoint(r["ts"], r["ip"], r["mac"], r["hostname"],
                             r["state"], r["rtt_ms"])
            for r in rows
        ]

    def query_uptime_pct(self, ip: str, hours: float = 24.0) -> float:
        """
        Return the percentage of state samples where the device was UP
        in the given window.  Returns 100.0 if no samples exist.
        """
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN state = 'UP' THEN 1 ELSE 0 END) AS up_count "
            "FROM device_state WHERE ip = ? AND ts >= ?",
            (ip, since),
        )
        row = rows[0] if rows else None
        if not row or not row["total"]:
            return 100.0
        return round(100.0 * row["up_count"] / row["total"], 2)

    # ── Read: device events ──────────────────────────────────────────────────

    def query_device_events(
        self,
        hours: float = 24.0,
        ip: Optional[str] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[DeviceEvent]:
        """Return device events filtered by time window, IP, and/or event type."""
        since = int(time.time()) - int(hours * 3600)
        params: list = [since]
        clauses = ["ts >= ?"]
        if ip:
            clauses.append("ip = ?")
            params.append(ip)
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            clauses.append(f"event_type IN ({placeholders})")
            params.extend([e.upper() for e in event_types])
        sql = (
            "SELECT ts, ip, mac, event_type, detail FROM device_event "
            f"WHERE {' AND '.join(clauses)} ORDER BY ts DESC"
        )
        rows = self._execute_read(sql, tuple(params))
        return [
            DeviceEvent(r["ts"], r["ip"], r["mac"], r["event_type"], r["detail"])
            for r in rows
        ]

    # ── Read: known device inventory ────────────────────────────────────────

    def get_known_devices(self) -> Dict[str, KnownDevice]:
        """Return all known devices keyed by MAC address."""
        rows = self._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, is_authorized, "
            "custom_name, room, category, notes, is_pinned FROM known_device",
            (),
        )
        return {
            r["mac"]: KnownDevice(
                mac=r["mac"], ip=r["ip"], hostname=r["hostname"],
                vendor=r["vendor"], device_type=r["device_type"],
                first_seen=r["first_seen"], last_seen=r["last_seen"],
                is_authorized=bool(r["is_authorized"]),
                custom_name=r["custom_name"],
                room=r["room"],
                category=r["category"] or "unknown",
                notes=r["notes"],
                is_pinned=bool(r["is_pinned"]),
            )
            for r in rows
        }

    # ── Write / Read: speed test results ──────────────────────────────────

    def update_device_ha_info(
        self,
        mac: str,
        custom_name: Optional[str] = None,
        room: Optional[str] = None,
        category: Optional[str] = None,
        notes: Optional[str] = None,
        is_pinned: Optional[bool] = None,
    ) -> None:
        """
        Update the Home Automation Hub metadata for a known device.
        Only non-None arguments are written; others are preserved.
        """
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
        """Record a detected Home Automation protocol/device signature."""
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO ha_detected(ts, ip, mac, ha_type, confidence, detail) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (now, ip, mac, ha_type, confidence, detail),
        )

    def query_ha_detected(
        self, hours: float = 168.0
    ) -> "List[HaDetectedPoint]":
        """Return HA detection events within the last `hours`, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT id, ts, ip, mac, ha_type, confidence, detail "
            "FROM ha_detected WHERE ts >= ? ORDER BY ts DESC",
            (since,),
        )
        return [
            HaDetectedPoint(
                id=r["id"], ts=r["ts"], ip=r["ip"], mac=r["mac"],
                ha_type=r["ha_type"], confidence=r["confidence"],
                detail=r["detail"],
            )
            for r in rows
        ]

    def query_ha_devices(
        self, category: Optional[str] = None
    ) -> "List[KnownDevice]":
        """
        Return known devices tagged as home-automation categories.
        If category is given, filter to that exact category.
        If omitted, returns all devices except category='unknown'.
        """
        HA_CATEGORIES = {
            "home_automation", "smart_speaker", "smart_tv",
            "smart_hub", "camera", "thermostat", "lighting",
            "smart_plug", "security", "media_player",
        }
        if category:
            rows = self._execute_read(
                "SELECT mac, ip, hostname, vendor, device_type, "
                "first_seen, last_seen, is_authorized, "
                "custom_name, room, category, notes, is_pinned "
                "FROM known_device WHERE category = ?",
                (category,),
            )
        else:
            placeholders = ",".join("?" * len(HA_CATEGORIES))
            rows = self._execute_read(
                f"SELECT mac, ip, hostname, vendor, device_type, "
                f"first_seen, last_seen, is_authorized, "
                f"custom_name, room, category, notes, is_pinned "
                f"FROM known_device WHERE category IN ({placeholders})",
                tuple(HA_CATEGORIES),
            )
        return [
            KnownDevice(
                mac=r["mac"], ip=r["ip"], hostname=r["hostname"],
                vendor=r["vendor"], device_type=r["device_type"],
                first_seen=r["first_seen"], last_seen=r["last_seen"],
                is_authorized=bool(r["is_authorized"]),
                custom_name=r["custom_name"], room=r["room"],
                category=r["category"] or "unknown",
                notes=r["notes"], is_pinned=bool(r["is_pinned"]),
            )
            for r in rows
        ]

    # ── Write / Read: speed test results ─────────────────────────────────────

    def record_speed_test(
        self,
        download_mbps: float,
        upload_mbps: float,
        ping_ms: float,
        server_name: Optional[str] = None,
        server_city: Optional[str] = None,
        server_country: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        """Persist a completed speed test result to the database."""
        now = ts or int(time.time())
        self._execute_write(
            "INSERT INTO speed_test "
            "(ts, download_mbps, upload_mbps, ping_ms, server_name, server_city, server_country) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (now, download_mbps, upload_mbps, ping_ms, server_name, server_city, server_country),
        )

    def query_speed_test_history(
        self,
        hours: float = 168.0,
        limit: int = 200,
    ) -> "List[SpeedTestPoint]":
        """Return speed test results within the last `hours`, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, download_mbps, upload_mbps, ping_ms, "
            "server_name, server_city, server_country "
            "FROM speed_test WHERE ts >= ? "
            "ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [
            SpeedTestPoint(
                ts=r["ts"],
                download_mbps=r["download_mbps"],
                upload_mbps=r["upload_mbps"],
                ping_ms=r["ping_ms"],
                server_name=r["server_name"],
                server_city=r["server_city"],
                server_country=r["server_country"],
            )
            for r in rows
        ]

    # ── CVE lifecycle tracker (schema v7) ────────────────────────────────────

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
        """
        Insert or update a CVE lifecycle record.
        Returns the row id.
        """
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
        """Update the remediation state, owner, and notes of a CVE lifecycle record."""
        now = ts or int(time.time())
        self._execute_write(
            "UPDATE cve_lifecycle SET state=?, owner=?, notes=?, updated_ts=? WHERE id=?",
            (state, owner, notes, now, row_id),
        )

    def list_cve_lifecycles(
        self, state_filter: Optional[str] = None
    ) -> List[dict]:
        """Return all CVE lifecycle rows, optionally filtered by state."""
        if state_filter:
            rows = self._execute_read(
                "SELECT * FROM cve_lifecycle WHERE state=? ORDER BY cvss_score DESC, opened_ts ASC",
                (state_filter,),
            )
        else:
            rows = self._execute_read(
                "SELECT * FROM cve_lifecycle ORDER BY cvss_score DESC, opened_ts ASC",
                (),
            )
        return [dict(r) for r in rows]

    def delete_cve_lifecycle(self, row_id: int) -> None:
        """Remove a CVE lifecycle record."""
        self._execute_write("DELETE FROM cve_lifecycle WHERE id=?", (row_id,))

    # ── Alert fired / acknowledgement tracker (schema v7) ────────────────────

    def record_alert_fired(
        self,
        rule_name: str,
        host: str,
        severity: str,
        message: str,
        ts: Optional[int] = None,
    ) -> int:
        """Persist a fired alert for acknowledgement + escalation tracking. Returns row id."""
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
        """Mark an alert as acknowledged."""
        now = ts or int(time.time())
        self._execute_write(
            "UPDATE alert_fired SET acked_ts=?, acked_by=? WHERE id=?",
            (now, acked_by, alert_id),
        )

    def mark_alert_escalated(self, alert_id: int) -> None:
        """Mark an alert as having been escalated."""
        self._execute_write(
            "UPDATE alert_fired SET escalated=1 WHERE id=?",
            (alert_id,),
        )

    def get_unacked_alerts(self, older_than_s: int = 0) -> List[dict]:
        """
        Return alerts that have not been acknowledged.
        older_than_s: only return alerts fired more than this many seconds ago (for escalation checks).
        """
        cutoff = int(time.time()) - older_than_s
        rows = self._execute_read(
            "SELECT * FROM alert_fired WHERE acked_ts IS NULL AND ts <= ? "
            "ORDER BY ts ASC",
            (cutoff,),
        )
        return [dict(r) for r in rows]

    def get_recent_alerts(self, hours: float = 24.0, limit: int = 200) -> List[dict]:
        """Return recent fired alerts, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT * FROM alert_fired WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [dict(r) for r in rows]

    # ── Maintenance ───────────────────────────────────────────────────────────

    def prune_old_data(self, retain_days: Optional[int] = None) -> int:
        """
        Delete records older than `retain_days` (default: instance retain_days).
        Returns the total number of rows deleted.
        """
        days   = retain_days if retain_days is not None else self._retain_days
        cutoff = int(time.time()) - days * 86400
        deleted = 0
        for tbl in ("rtt_sample", "device_state", "device_event", "cert_check", "service_check", "speed_test", "ha_detected"):
            self._execute_write(f"DELETE FROM {tbl} WHERE ts < ?", (cutoff,))
            deleted += 1  # rowcount not tracked per-table in unified path
        return deleted

    def get_db_size_bytes(self) -> int:
        """Return the current size of the database file in bytes."""
        try:
            return self._db_path.stat().st_size
        except OSError:
            return 0

    def get_row_counts(self) -> Dict[str, int]:
        """Return row counts for each data table."""
        result = {}
        for tbl in ("rtt_sample", "device_state", "device_event", "known_device", "cert_check", "service_check", "speed_test", "ha_detected"):
            rows = self._execute_read(f"SELECT COUNT(*) AS n FROM {tbl}", ())
            result[tbl] = rows[0]["n"] if rows else 0
        return result

    # ── Path resolution (mirrors Dashboard._settings_path logic) ─────────────

    @staticmethod
    def _default_path() -> Path:
        """
        Resolve the default DB path:
          1. Same directory as the running exe / script (portable).
          2. Fallback: ~/.config/NetSentinel/metrics.db
        """
        import sys as _sys
        if getattr(_sys, "frozen", False):
            exe_dir = Path(_sys.executable).parent
        else:
            exe_dir = Path(__file__).resolve().parent.parent
        candidate = exe_dir / "NetSentinel.db"
        try:
            candidate.touch(exist_ok=True)
            return candidate
        except OSError:
            fallback = Path.home() / ".config" / "NetSentinel" / "metrics.db"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    # ── Config snapshot CRUD ──────────────────────────────────────────────────

    def store_snapshot(self, ts: int, label: str, data_json: str) -> int:
        """Insert a snapshot row and return its id."""
        import json as _json
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

    def load_snapshot(self, snapshot_id: int) -> Optional[dict]:
        """Return {id, ts, label, data_json} or None."""
        rows = self._execute_read(
            "SELECT id, ts, label, data_json FROM config_snapshot WHERE id = ?",
            (snapshot_id,),
        )
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "ts": r["ts"], "label": r["label"], "data_json": r["data_json"]}

    def list_snapshots(self, limit: int = 100) -> List[dict]:
        """Return the most recent `limit` snapshots (newest first)."""
        rows = self._execute_read(
            "SELECT id, ts, label, data_json FROM config_snapshot "
            "ORDER BY ts DESC LIMIT ?",
            (limit,),
        )
        return [{"id": r["id"], "ts": r["ts"], "label": r["label"],
                 "data_json": r["data_json"]} for r in rows]

    def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a snapshot by id."""
        self._execute_write(
            "DELETE FROM config_snapshot WHERE id = ?", (snapshot_id,)
        )

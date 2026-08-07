"""
MetricStore schema — DDL, schema version, migrations, and data-transfer objects.

Extracted from modules/metric_store.py (S2-1 sprint split).
All symbols are re-exported from modules/metric_store for backwards compatibility.
"""
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional

# ── Schema version — bump when adding columns ────────────────────────────────
_SCHEMA_VERSION = 22

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
    is_pinned    INTEGER NOT NULL DEFAULT 0,
    -- Persistent device map fields (schema v16)
    scan_count    INTEGER NOT NULL DEFAULT 0,
    ip_stability  REAL    NOT NULL DEFAULT 0.0,
    inferred_role TEXT,
    -- Per-device alert opt-in (schema v19)
    alert_opt_in  INTEGER NOT NULL DEFAULT 0,
    -- Hostname TTL cache (schema v21) — epoch seconds of the last ACTIVE name
    -- resolution attempt for this MAC (NULL = never actively resolved).
    -- Distinct from last_seen, which updates on every scan regardless of
    -- whether resolution ran that cycle.
    hostname_resolved_at INTEGER,
    -- Presence episode state (schema v22) — 'present' | 'absent' | NULL.
    -- gone_notified_ts is when LEFT was last emitted for the CURRENT absence,
    -- so one absence episode produces exactly one LEFT. It replaces a
    -- query_device_events() lookback that ran once per absent device per scan
    -- (see DeviceTracker.process_scan).
    presence_state   TEXT,
    gone_notified_ts INTEGER,
    -- Materialised device_importance.Tier (schema v22) — a CACHE for display
    -- and claim ranking (modules/relevance.py), refreshed set-wise once per
    -- scan by refresh_importance_tiers(). It is deliberately NOT the alert
    -- gate's source: get_device_importance_tier() still recomputes from the
    -- live row every time, because the stored columns this model replaced were
    -- wrong for 8 of 13 devices on the reference network and a cache of a
    -- verdict is only ever as fresh as its last write.
    importance_tier   TEXT,
    importance_source TEXT
);
CREATE INDEX IF NOT EXISTS idx_known_device_last_seen ON known_device(last_seen DESC);

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

-- 5G modem periodic signal snapshots for long-term monitoring
CREATE TABLE IF NOT EXISTS modem_signal_log (
    id           INTEGER PRIMARY KEY,
    ts           INTEGER NOT NULL,
    network_type TEXT,
    signal_bars  INTEGER,
    cell_id      TEXT,
    enb_id       TEXT,
    mcc          TEXT,
    mnc          TEXT,
    wan_ip       TEXT,
    nr5g_band    TEXT,
    nr5g_rsrp    REAL,
    nr5g_sinr    REAL,
    nr5g_rsrq    REAL,
    nr5g_pci     INTEGER,
    nr5g_arfcn   INTEGER,
    lte_band     TEXT,
    lte_rsrp     REAL,
    lte_snr      REAL,
    lte_rsrq     REAL,
    lte_pci      INTEGER,
    lte_earfcn   INTEGER
);
CREATE INDEX IF NOT EXISTS idx_msl_ts ON modem_signal_log(ts);

-- Mesh system periodic status snapshots for long-term monitoring
CREATE TABLE IF NOT EXISTS mesh_signal_log (
    id           INTEGER PRIMARY KEY,
    ts           INTEGER NOT NULL,
    unit_count   INTEGER,
    online_count INTEGER,
    worst_unit   TEXT,
    worst_rssi   REAL
);
CREATE INDEX IF NOT EXISTS idx_mesh_ts ON mesh_signal_log(ts);

-- Hardware plugin snapshots for long-term monitoring
CREATE TABLE IF NOT EXISTS plugin_log (
    id          INTEGER PRIMARY KEY,
    ts          INTEGER NOT NULL,
    plugin_name TEXT    NOT NULL,
    data        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plugin_log_ts   ON plugin_log(ts);
CREATE INDEX IF NOT EXISTS idx_plugin_log_name ON plugin_log(plugin_name);

-- Alert acknowledgement + escalation tracking (schema v7, comment added v15)
CREATE TABLE IF NOT EXISTS alert_fired (
    id            INTEGER PRIMARY KEY,
    ts            INTEGER NOT NULL,
    rule_name     TEXT    NOT NULL,
    host          TEXT    NOT NULL DEFAULT '',
    severity      TEXT    NOT NULL DEFAULT 'WARNING',
    message       TEXT    NOT NULL DEFAULT '',
    acked_ts      INTEGER,
    acked_by      TEXT,
    acked_comment TEXT,
    escalated     INTEGER NOT NULL DEFAULT 0,
    -- Stable rule-type enum for badge/query filtering (schema v19)
    rule_type     TEXT    NOT NULL DEFAULT '',
    -- Signal Quality Phase 6 (schema v22) — the six AlertFired fields
    -- record_alert_fired() silently dropped. Without them history could not
    -- tell a resolution from an alert except by inferring it from
    -- severity = 'HEALTHY', and nothing recorded WHY a claim was made.
    --   confidence    — evidence.Evidence.confidence; ordering aid, not a
    --                   probability, and never a severity (RULE-A3 unaffected)
    --   evidence_json — the corroboration behind the claim, as JSON
    --   dedup_key     — "<rule_name>::<host>", the AlertEngine._last_fired key.
    --                   Indexed so cooldown state survives a restart with one
    --                   read instead of a second persistence path.
    --   resolved_ts   — stamped on the OPENING row when its resolution lands,
    --                   so an outage's duration is readable without pairing
    --                   rows by hand
    --   is_resolution — explicit, replacing the severity inference
    --   value         — the triggering metric value
    confidence    REAL,
    evidence_json TEXT,
    dedup_key     TEXT,
    resolved_ts   INTEGER,
    is_resolution INTEGER NOT NULL DEFAULT 0,
    value         REAL
);
CREATE INDEX IF NOT EXISTS idx_af_ts    ON alert_fired(ts);
CREATE INDEX IF NOT EXISTS idx_af_acked ON alert_fired(acked_ts);
-- idx_af_dedup is created in _POST_MIGRATION_INDEXES, not here: this script
-- runs before the ALTER TABLEs, so on an upgrading database dedup_key does not
-- exist yet and executescript() would raise "no such column".

-- Network grade history — one row per grading run (schema v8; append-only since V6 Sprint 1)
CREATE TABLE IF NOT EXISTS grade_result (
    id      INTEGER PRIMARY KEY,
    ts      INTEGER NOT NULL,
    grade   TEXT    NOT NULL,
    score   REAL    NOT NULL,
    verdict TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_grade_result_ts ON grade_result(ts DESC);

-- User-authored device annotations — labels, location, owner (schema v10)
CREATE TABLE IF NOT EXISTS device_annotations (
    mac         TEXT PRIMARY KEY,
    user_label  TEXT DEFAULT '',
    location    TEXT DEFAULT '',
    owner       TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    asset_tag   TEXT DEFAULT '',
    updated_at  DATETIME DEFAULT (datetime('now'))
);

-- Per-device IP address history — how many times each IP was seen (schema v10)
CREATE TABLE IF NOT EXISTS device_ip_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mac         TEXT NOT NULL,
    ip          TEXT NOT NULL,
    first_seen  DATETIME NOT NULL,
    last_seen   DATETIME NOT NULL,
    seen_count  INTEGER DEFAULT 1,
    UNIQUE (mac, ip)
);
CREATE INDEX IF NOT EXISTS idx_dih_mac ON device_ip_history(mac);

-- Network segment / zone definitions (schema v11)
CREATE TABLE IF NOT EXISTS network_segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    cidr         TEXT    NOT NULL UNIQUE,
    color        TEXT    NOT NULL DEFAULT '#0078D4',
    description  TEXT    NOT NULL DEFAULT '',
    auto_created INTEGER NOT NULL DEFAULT 0,
    created_at   DATETIME DEFAULT (datetime('now'))
);

-- Device change audit trail (schema v12)
CREATE TABLE IF NOT EXISTS device_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mac         TEXT    NOT NULL,
    event_type  TEXT    NOT NULL,
    old_value   TEXT    NOT NULL DEFAULT '',
    new_value   TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL DEFAULT '',
    ts          DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_devev_mac_ts ON device_events(mac, ts DESC);
CREATE INDEX IF NOT EXISTS idx_devev_ts     ON device_events(ts DESC);

-- User device type overrides — permanent, override all enrichment (schema v13)
CREATE TABLE IF NOT EXISTS device_classification_overrides (
    mac             TEXT PRIMARY KEY,
    device_type     TEXT NOT NULL,
    overridden_at   DATETIME DEFAULT (datetime('now'))
);

-- Topology change-detection snapshots (schema v14)
CREATE TABLE IF NOT EXISTS topology_snapshots (
    id        INTEGER PRIMARY KEY,
    ts        INTEGER NOT NULL,
    data_json TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topo_snap_ts ON topology_snapshots(ts DESC);

-- App Traffic per-host/category bandwidth samples (schema v17)
-- app/window_s (G12): written on every insert but not currently read by any
-- query — reserved for a future per-app breakdown view. Additive-only
-- migration framework means these stay; do not drop them to "clean up".
CREATE TABLE IF NOT EXISTS app_traffic_sample (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    mac         TEXT    NOT NULL,
    label       TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL,
    app         TEXT    NOT NULL DEFAULT '',
    cdn         TEXT,
    bytes_total INTEGER NOT NULL DEFAULT 0,
    window_s    REAL    NOT NULL DEFAULT 10.0
);
CREATE INDEX IF NOT EXISTS idx_ats_ts       ON app_traffic_sample(ts);
CREATE INDEX IF NOT EXISTS idx_ats_category ON app_traffic_sample(category, ts);
CREATE INDEX IF NOT EXISTS idx_ats_mac      ON app_traffic_sample(mac, ts);

-- Daily min/avg/max/n aggregates — survives raw-row pruning so long-term
-- trend charts have data beyond the 30-day rtt_sample retention window
-- (schema v18, Stability Sprint 2 / G4).
CREATE TABLE IF NOT EXISTS daily_rollup (
    day    TEXT    NOT NULL,   -- UTC calendar day, 'YYYY-MM-DD'
    metric TEXT    NOT NULL,   -- e.g. 'rtt_ms', 'loss_pct', 'jitter_ms'
    host   TEXT    NOT NULL,
    min    REAL    NOT NULL,
    avg    REAL    NOT NULL,
    max    REAL    NOT NULL,
    n      INTEGER NOT NULL,
    PRIMARY KEY (day, metric, host)
);
CREATE INDEX IF NOT EXISTS idx_rollup_metric_host ON daily_rollup(metric, host, day);
"""

# ── Column migrations (applied idempotently on every open) ───────────────────
_MIGRATIONS = [
    "ALTER TABLE known_device ADD COLUMN custom_name TEXT",
    "ALTER TABLE known_device ADD COLUMN room TEXT",
    "ALTER TABLE known_device ADD COLUMN category TEXT NOT NULL DEFAULT 'unknown'",
    "ALTER TABLE known_device ADD COLUMN notes TEXT",
    "ALTER TABLE known_device ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE speed_test ADD COLUMN network_type TEXT",
    "ALTER TABLE speed_test ADD COLUMN signal_bars INTEGER",
    "ALTER TABLE speed_test ADD COLUMN nr5g_rsrp REAL",
    "ALTER TABLE speed_test ADD COLUMN nr5g_sinr REAL",
    "ALTER TABLE speed_test ADD COLUMN nr5g_band TEXT",
    "ALTER TABLE speed_test ADD COLUMN lte_rsrp REAL",
    "ALTER TABLE speed_test ADD COLUMN lte_band TEXT",
    "ALTER TABLE speed_test ADD COLUMN cell_id TEXT",
    "ALTER TABLE speed_test ADD COLUMN enb_id TEXT",
    "ALTER TABLE speed_test ADD COLUMN mcc TEXT",
    "ALTER TABLE speed_test ADD COLUMN mnc TEXT",
    "ALTER TABLE speed_test ADD COLUMN wan_ip TEXT",
    "ALTER TABLE speed_test ADD COLUMN nr5g_rsrq REAL",
    "ALTER TABLE speed_test ADD COLUMN nr5g_pci INTEGER",
    "ALTER TABLE speed_test ADD COLUMN nr5g_arfcn INTEGER",
    "ALTER TABLE speed_test ADD COLUMN lte_snr REAL",
    "ALTER TABLE speed_test ADD COLUMN lte_rsrq REAL",
    "ALTER TABLE speed_test ADD COLUMN lte_pci INTEGER",
    "ALTER TABLE speed_test ADD COLUMN lte_earfcn INTEGER",
    "ALTER TABLE known_device ADD COLUMN tags TEXT",
    # schema v9 — service mapping and classification quality columns
    "ALTER TABLE known_device ADD COLUMN services TEXT DEFAULT NULL",
    "ALTER TABLE known_device ADD COLUMN mac_randomized INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE known_device ADD COLUMN confidence REAL NOT NULL DEFAULT 0.0",
    # schema v15 — ack comment for per-alert acknowledgement with owner+note
    "ALTER TABLE alert_fired ADD COLUMN acked_comment TEXT",
    # schema v16 — persistent device map: stability scoring + role inference
    "ALTER TABLE known_device ADD COLUMN scan_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE known_device ADD COLUMN ip_stability REAL NOT NULL DEFAULT 0.0",
    "ALTER TABLE known_device ADD COLUMN inferred_role TEXT",
    # schema v19 — opt-in device alert scope + stable rule_type on fired alerts
    "ALTER TABLE known_device ADD COLUMN alert_opt_in INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE alert_fired ADD COLUMN rule_type TEXT NOT NULL DEFAULT ''",
    # schema v21 — hostname TTL cache (Part 2/L8)
    "ALTER TABLE known_device ADD COLUMN hostname_resolved_at INTEGER",
    # schema v22 — Signal Quality Phase 6: the six AlertFired fields
    # record_alert_fired() dropped, plus presence episodes and the
    # materialised importance tier. See the DDL above for what each carries.
    "ALTER TABLE alert_fired ADD COLUMN confidence REAL",
    "ALTER TABLE alert_fired ADD COLUMN evidence_json TEXT",
    "ALTER TABLE alert_fired ADD COLUMN dedup_key TEXT",
    "ALTER TABLE alert_fired ADD COLUMN resolved_ts INTEGER",
    "ALTER TABLE alert_fired ADD COLUMN is_resolution INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE alert_fired ADD COLUMN value REAL",
    "ALTER TABLE known_device ADD COLUMN presence_state TEXT",
    "ALTER TABLE known_device ADD COLUMN gone_notified_ts INTEGER",
    "ALTER TABLE known_device ADD COLUMN importance_tier TEXT",
    "ALTER TABLE known_device ADD COLUMN importance_source TEXT",
]

# Indexes that only exist once a v22 migration column does. The _DDL block
# above creates them for a fresh database, but CREATE INDEX in that script runs
# BEFORE the ALTER TABLEs on an upgrading one, where the column does not exist
# yet — so an upgrading database would silently never get the index.
_POST_MIGRATION_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_af_dedup ON alert_fired(dedup_key, ts)",
]


def apply_sqlite_schema(conn: sqlite3.Connection, write_lock: threading.Lock) -> None:
    """Create tables and run idempotent column migrations on a SQLite connection."""
    with write_lock:
        conn.executescript(_DDL)
        for col_def in _MIGRATIONS:
            try:
                conn.execute(col_def)
            except sqlite3.OperationalError:
                pass  # column already exists
        for index_def in _POST_MIGRATION_INDEXES:
            try:
                conn.execute(index_def)
            except sqlite3.OperationalError:
                pass  # index already exists, or its column migration was skipped
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("schema_version", str(_SCHEMA_VERSION)),
        )
        conn.commit()
        # Stability Sprint 1 (G2): a real VACUUM used to be attempted here on
        # every schema apply (i.e. every app startup) via the invalid
        # "PRAGMA VACUUM" — swallowed silently by the bare except, so it was
        # always a no-op AND would have been the wrong place anyway: VACUUM
        # rewrites the whole file and is only worthwhile right after a prune
        # deletes a meaningful number of rows. See MetricStore.vacuum_if_needed(),
        # called from prune_old_data().


def apply_sqlalchemy_schema(engine) -> None:
    """Create tables via SQLAlchemy text DDL (strips PRAGMA for non-SQLite engines)."""
    from sqlalchemy import text
    sa_ddl = "\n".join(
        line for line in _DDL.splitlines()
        if not line.strip().upper().startswith("PRAGMA")
    )
    with engine.begin() as conn:
        for statement in sa_ddl.split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    conn.execute(text(stmt))
                except Exception:
                    pass  # table already exists


# ── Return-type dataclasses ───────────────────────────────────────────────────

@dataclass
class SpeedTestPoint:
    ts:             int
    download_mbps:  float
    upload_mbps:    float
    ping_ms:        float
    server_name:    Optional[str]
    server_city:    Optional[str]
    server_country: Optional[str]
    network_type:   Optional[str] = None
    signal_bars:    Optional[int] = None
    nr5g_rsrp:      Optional[float] = None
    nr5g_sinr:      Optional[float] = None
    nr5g_band:      Optional[str] = None
    lte_rsrp:       Optional[float] = None
    lte_band:       Optional[str] = None
    cell_id:        Optional[str] = None
    enb_id:         Optional[str] = None
    mcc:            Optional[str] = None
    mnc:            Optional[str] = None
    wan_ip:         Optional[str] = None
    nr5g_rsrq:      Optional[float] = None
    nr5g_pci:       Optional[int] = None
    nr5g_arfcn:     Optional[int] = None
    lte_snr:        Optional[float] = None
    lte_rsrq:       Optional[float] = None
    lte_pci:        Optional[int] = None
    lte_earfcn:     Optional[int] = None


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
    ts: int
    host: str
    rtt_ms: float
    loss_pct: float
    jitter_ms: float


@dataclass
class DeviceStatePoint:
    ts: int
    ip: str
    mac: Optional[str]
    hostname: Optional[str]
    state: str
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
    custom_name: Optional[str] = None
    room: Optional[str] = None
    category: str = "unknown"
    notes: Optional[str] = None
    is_pinned: bool = False
    tags: Optional[str] = None
    services: Optional[str] = None      # JSON array of service names
    mac_randomized: bool = False
    confidence: float = 0.0
    scan_count: int = 0
    ip_stability: float = 0.0
    inferred_role: Optional[str] = None
    alert_opt_in: bool = False
    hostname_resolved_at: Optional[int] = None
    presence_state: Optional[str] = None
    gone_notified_ts: Optional[int] = None
    importance_tier: Optional[str] = None
    importance_source: Optional[str] = None


@dataclass
class HaDetectedPoint:
    id: int
    ts: int
    ip: str
    mac: Optional[str]
    ha_type: str
    confidence: str
    detail: Optional[str]


@dataclass
class ModemSignalPoint:
    ts:           int
    network_type: Optional[str]
    signal_bars:  Optional[int]
    cell_id:      Optional[str]
    enb_id:       Optional[str]
    mcc:          Optional[str]
    mnc:          Optional[str]
    wan_ip:       Optional[str]
    nr5g_band:    Optional[str]
    nr5g_rsrp:    Optional[float]
    nr5g_sinr:    Optional[float]
    nr5g_rsrq:    Optional[float]
    nr5g_pci:     Optional[int]
    nr5g_arfcn:   Optional[int]
    lte_band:     Optional[str]
    lte_rsrp:     Optional[float]
    lte_snr:      Optional[float]
    lte_rsrq:     Optional[float]
    lte_pci:      Optional[int]
    lte_earfcn:   Optional[int]


@dataclass
class MeshSignalPoint:
    ts:           int
    unit_count:   int
    online_count: int
    worst_unit:   Optional[str]
    worst_rssi:   Optional[float]


@dataclass
class RollupPoint:
    day:    str
    metric: str
    host:   str
    min:    float
    avg:    float
    max:    float
    n:      int


@dataclass
class AppTrafficSamplePoint:
    ts:          int
    mac:         str
    label:       str
    category:    str
    app:         str
    cdn:         Optional[str]
    bytes_total: int
    window_s:    float

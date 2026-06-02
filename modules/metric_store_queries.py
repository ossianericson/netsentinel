"""
MetricStore query mixin — all read-only query methods for MetricStore.

Extracted from modules/metric_store.py (S2-1 sprint split).
E3 sprint split: time-series metrics → metric_store_queries_metrics.py,
                 uptime/device-state  → metric_store_queries_uptime.py.
MetricStoreQueryMixin is used via multiple inheritance in MetricStore.
All symbols are accessible through MetricStore instances as before.
"""
import time
from pathlib import Path
from typing import Dict, List, Optional

from modules.metric_store_schema import (
    CertCheckPoint, HaDetectedPoint, KnownDevice, ServiceCheckPoint,
)
from modules.metric_store_queries_uptime import _UptimeQueriesMixin
from modules.metric_store_queries_metrics import _MetricsQueriesMixin


def _default_db_path() -> Path:
    """
    Resolve the default DB path:
      1. Same directory as the running exe (portable)
      2. %LOCALAPPDATA%\\NetSentinel\\NetSentinel.db  (installed build)
      3. ~/.config/NetSentinel/metrics.db  (Linux / macOS)
    """
    import sys as _sys
    from modules.utils import get_app_data_dir

    if getattr(_sys, "frozen", False):
        exe_dir = Path(_sys.executable).parent
    else:
        exe_dir = Path(__file__).resolve().parent.parent

    candidate = exe_dir / "NetSentinel.db"
    try:
        candidate.touch(exist_ok=True)
        return candidate
    except OSError:
        pass

    return get_app_data_dir() / "NetSentinel.db"


class MetricStoreQueryMixin(_UptimeQueriesMixin, _MetricsQueriesMixin):
    """Read-only query methods for MetricStore.

    Requires self._execute_read(sql, params) to be provided by the host class.
    """

    # ── Read: TLS certificate checks ─────────────────────────────────────────

    def query_cert_status(self, hours: float = 168.0) -> List[CertCheckPoint]:
        """Return the latest cert check per (host, port) within the last `hours`."""
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
        self, host: str, port: int = 443, hours: float = 168.0,
    ) -> List[CertCheckPoint]:
        """Return all cert checks for host:port over the last `hours`, oldest first."""
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
    def _row_to_cert(r) -> CertCheckPoint:
        return CertCheckPoint(
            ts=r["ts"], host=r["host"], port=r["port"],
            days_remaining=r["days_remaining"],
            subject=r["subject"], issuer=r["issuer"],
            not_after=r["not_after"],
            is_expired=bool(r["is_expired"]),
            is_self_signed=bool(r["is_self_signed"]),
            error=r["error"],
        )

    # ── Read: service / port heartbeat checks ────────────────────────────────

    def query_service_status(self, hours: float = 24.0) -> List[ServiceCheckPoint]:
        """Return the latest check result per (host, port) within the last `hours`."""
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
        self, host: str, port: int, hours: float = 24.0,
    ) -> List[ServiceCheckPoint]:
        """Return all checks for host:port over the last `hours`, oldest first."""
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
            "SELECT DISTINCT host, port, label FROM service_check ORDER BY host, port",
            (),
        )
        return [(r["host"], r["port"], r["label"]) for r in rows]

    @staticmethod
    def _row_to_svc(r) -> ServiceCheckPoint:
        return ServiceCheckPoint(
            ts=r["ts"], host=r["host"], port=r["port"], label=r["label"],
            up=bool(r["up"]), rtt_ms=r["rtt_ms"], error=r["error"],
        )

    # ── Read: known device inventory ─────────────────────────────────────────

    def get_known_devices(self) -> Dict[str, KnownDevice]:
        """Return all known devices keyed by MAC address."""
        rows = self._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, is_authorized, "
            "custom_name, room, category, notes, is_pinned, tags FROM known_device",
            (),
        )
        return {
            r["mac"]: KnownDevice(
                mac=r["mac"], ip=r["ip"], hostname=r["hostname"],
                vendor=r["vendor"], device_type=r["device_type"],
                first_seen=r["first_seen"], last_seen=r["last_seen"],
                is_authorized=bool(r["is_authorized"]),
                custom_name=r["custom_name"], room=r["room"],
                category=r["category"] or "unknown",
                notes=r["notes"], is_pinned=bool(r["is_pinned"]),
                tags=r["tags"],
            )
            for r in rows
        }

    # ── Read: Home Automation ─────────────────────────────────────────────────

    def query_ha_detected(self, hours: float = 168.0) -> List[HaDetectedPoint]:
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

    def query_ha_devices(self, category: Optional[str] = None) -> List[KnownDevice]:
        """Return known devices tagged as home-automation categories."""
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

    # ── Read: config snapshots ────────────────────────────────────────────────

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

    # ── Read: grade result ────────────────────────────────────────────────────

    def query_last_grade(self) -> Optional[dict]:
        """Return {grade, score, verdict, ts} or None if no grade has been run."""
        rows = self._execute_read(
            "SELECT ts, grade, score, verdict FROM grade_result ORDER BY ts DESC LIMIT 1",
            (),
        )
        if not rows:
            return None
        r = rows[0]
        return {"grade": r["grade"], "score": r["score"],
                "verdict": r["verdict"], "ts": r["ts"]}

    # ── Maintenance (read-dominant — safe to keep in query mixin) ─────────────

    def prune_old_data(self, retain_days: Optional[int] = None) -> int:
        """Delete records older than `retain_days`. Returns number of tables pruned."""
        days   = retain_days if retain_days is not None else self._retain_days
        cutoff = int(time.time()) - days * 86400
        deleted = 0
        for tbl in (
            "rtt_sample", "device_state", "device_event", "cert_check",
            "service_check", "speed_test", "ha_detected",
            "modem_signal_log", "mesh_signal_log", "plugin_log",
        ):
            self._execute_write(f"DELETE FROM {tbl} WHERE ts < ?", (cutoff,))
            deleted += 1
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
        for tbl in (
            "rtt_sample", "device_state", "device_event", "known_device",
            "cert_check", "service_check", "speed_test", "ha_detected",
            "modem_signal_log", "mesh_signal_log", "plugin_log",
        ):
            rows = self._execute_read(f"SELECT COUNT(*) AS n FROM {tbl}", ())
            result[tbl] = rows[0]["n"] if rows else 0
        return result

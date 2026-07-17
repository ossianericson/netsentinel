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
from modules.network_segments import NetworkSegment
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
        pass  # non-fatal

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
            "custom_name, room, category, notes, is_pinned, tags, "
            "services, mac_randomized, confidence, "
            "COALESCE(scan_count, 0) AS scan_count, "
            "COALESCE(ip_stability, 0.0) AS ip_stability, "
            "inferred_role, "
            "COALESCE(alert_opt_in, 0) AS alert_opt_in "
            "FROM known_device",
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
                services=r["services"],
                mac_randomized=bool(r["mac_randomized"]),
                confidence=float(r["confidence"] or 0.0),
                scan_count=int(r["scan_count"] or 0),
                ip_stability=float(r["ip_stability"] or 0.0),
                inferred_role=r["inferred_role"],
                alert_opt_in=bool(r["alert_opt_in"]),
            )
            for r in rows
        }

    # ── Read: device IP history ───────────────────────────────────────────────

    def get_ip_history(self, mac: str) -> List[Dict]:
        """Return [{ip, first_seen, last_seen, seen_count}] sorted by last_seen desc."""
        rows = self._execute_read(
            """
            SELECT ip, first_seen, last_seen, seen_count
            FROM device_ip_history
            WHERE mac = ?
            ORDER BY last_seen DESC
            """,
            (mac.lower(),),
        )
        return [
            {"ip": r[0], "first_seen": r[1], "last_seen": r[2], "seen_count": r[3]}
            for r in rows
        ]

    def query_ip_churn(self, hours: float = 24.0, min_ips: int = 3) -> Dict[str, int]:
        """Return {mac: distinct_ip_count} for devices seen at >= min_ips
        distinct IPs within the last `hours` — signals missing DHCP
        reservations (IP_CHURN rule, V6 Sprint 1)."""
        import datetime as _dt
        cutoff = (_dt.datetime.utcnow() - _dt.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        rows = self._execute_read(
            """
            SELECT mac, COUNT(DISTINCT ip) AS cnt
            FROM device_ip_history
            WHERE last_seen >= ?
            GROUP BY mac
            HAVING cnt >= ?
            """,
            (cutoff, min_ips),
        )
        return {r["mac"]: int(r["cnt"]) for r in rows}

    # ── Read: device annotations ──────────────────────────────────────────────

    def get_device_annotations(self, mac: str) -> Dict:
        """Return annotation dict for a MAC; empty dict if not found."""
        rows = self._execute_read(
            "SELECT user_label, location, owner, notes, asset_tag, updated_at "
            "FROM device_annotations WHERE mac = ?",
            (mac.lower(),),
        )
        if not rows:
            return {}
        r = rows[0]
        return {
            "user_label": r[0] or "",
            "location":   r[1] or "",
            "owner":      r[2] or "",
            "notes":      r[3] or "",
            "asset_tag":  r[4] or "",
            "updated_at": r[5] or "",
        }

    def get_all_device_annotations(self) -> Dict[str, Dict]:
        """Return {mac: annotation_dict} for all annotated devices."""
        rows = self._execute_read(
            "SELECT mac, user_label, location, owner, notes, asset_tag, updated_at "
            "FROM device_annotations",
            (),
        )
        result: Dict[str, Dict] = {}
        for r in rows:
            result[r[0]] = {
                "user_label": r[1] or "",
                "location":   r[2] or "",
                "owner":      r[3] or "",
                "notes":      r[4] or "",
                "asset_tag":  r[5] or "",
                "updated_at": r[6] or "",
            }
        return result

    # ── Read: device change audit trail (device_events table) ────────────────

    def get_device_change_events(
        self,
        mac: str,
        limit: int = 50,
    ) -> List[Dict]:
        """Return [{event_type, old_value, new_value, source, ts}] newest-first."""
        rows = self._execute_read(
            """
            SELECT event_type, old_value, new_value, source, ts
            FROM device_events
            WHERE mac = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (mac.lower(), limit),
        )
        return [
            {
                "event_type": r[0],
                "old_value":  r[1] or "",
                "new_value":  r[2] or "",
                "source":     r[3] or "",
                "ts":         r[4],
            }
            for r in rows
        ]

    def get_all_device_change_events(
        self,
        limit: int = 500,
        hours: int = 168,
    ) -> List[Dict]:
        """Return recent device change events across all MACs, newest-first."""
        rows = self._execute_read(
            """
            SELECT mac, event_type, old_value, new_value, source, ts
            FROM device_events
            WHERE ts >= datetime('now', ? || ' hours')
            ORDER BY ts DESC
            LIMIT ?
            """,
            (f"-{hours}", limit),
        )
        return [
            {
                "mac":        r[0],
                "event_type": r[1],
                "old_value":  r[2] or "",
                "new_value":  r[3] or "",
                "source":     r[4] or "",
                "ts":         r[5],
            }
            for r in rows
        ]

    # ── Read: topology snapshots ──────────────────────────────────────────────

    def get_last_topology_snapshot(self) -> Optional[tuple]:
        """Return (ts, data_json) for the most recent topology snapshot, or None."""
        rows = self._execute_read(
            "SELECT ts, data_json FROM topology_snapshots ORDER BY ts DESC LIMIT 1",
        )
        return tuple(rows[0]) if rows else None

    def query_known_devices_summary(self) -> List[Dict]:
        """Return known_device rows as plain dicts (REST API /devices shape)."""
        rows = self._execute_read(
            "SELECT mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, is_authorized, category, custom_name, room "
            "FROM known_device ORDER BY last_seen DESC",
            (),
        )
        return [dict(r) for r in rows]

    def get_max_device_scan_count(self) -> int:
        """Return the highest known_device.scan_count across all devices — a cheap
        proxy for how many scan cycles this install has been through (F8 usage
        signal), with no new write path required."""
        rows = self._execute_read(
            "SELECT COALESCE(MAX(scan_count), 0) AS n FROM known_device",
            (),
        )
        return int(rows[0]["n"]) if rows else 0

    def query_device_state_since(self, ip: str, since: int) -> List[Dict]:
        """Return device_state rows (ts, state, rtt_ms) for `ip` since `since` (REST API /uptime)."""
        rows = self._execute_read(
            "SELECT ts, state, rtt_ms FROM device_state "
            "WHERE ip=? AND ts>=? ORDER BY ts ASC",
            (ip, since),
        )
        return [dict(r) for r in rows]

    # ── Read: Classification overrides ───────────────────────────────────────

    def get_classification_override(self, mac: str) -> Optional[str]:
        """Return the user-set device_type override for this MAC, or None."""
        rows = self._execute_read(
            "SELECT device_type FROM device_classification_overrides WHERE mac = ?",
            (mac.lower(),),
        )
        return rows[0]["device_type"] if rows else None

    def get_all_classification_overrides(self) -> Dict[str, str]:
        """Return a dict mapping lowercase MAC → device_type for all active overrides."""
        rows = self._execute_read(
            "SELECT mac, device_type FROM device_classification_overrides",
            (),
        )
        return {r["mac"]: r["device_type"] for r in rows}

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
            "SELECT ts, grade, score, verdict FROM grade_result ORDER BY ts DESC, id DESC LIMIT 1",
            (),
        )
        if not rows:
            return None
        r = rows[0]
        return {"grade": r["grade"], "score": r["score"],
                "verdict": r["verdict"], "ts": r["ts"]}

    def query_previous_grade(self) -> Optional[dict]:
        """Return the second-most-recent grade row {grade, score, verdict, ts},
        or None if fewer than two grades have been recorded. Used to detect a
        grade improvement between the last two runs (share-at-the-moment-of-pride)."""
        rows = self._execute_read(
            "SELECT ts, grade, score, verdict FROM grade_result "
            "ORDER BY ts DESC, id DESC LIMIT 1 OFFSET 1",
            (),
        )
        if not rows:
            return None
        r = rows[0]
        return {"grade": r["grade"], "score": r["score"],
                "verdict": r["verdict"], "ts": r["ts"]}

    # ── Maintenance (read-dominant — safe to keep in query mixin) ─────────────

    # Stability Sprint 1 (G9): audit-trail tables get a generous window — users
    # may want a year of alert/change history, not the 30-day operational default.
    _AUDIT_RETAIN_DAYS = 365

    def prune_old_data(self, retain_days: Optional[int] = None) -> int:
        """Delete records older than `retain_days`. Returns the total number of
        rows deleted across all pruned tables (used to decide whether a VACUUM
        is worthwhile — see vacuum_if_needed())."""
        days   = retain_days if retain_days is not None else self._retain_days
        cutoff = int(time.time()) - days * 86400
        total_deleted = 0
        # Stability Sprint 2 (G4): speed_test and grade_result are exempt from
        # the 30-day operational prune window. Both are low-volume
        # (per-run / per-grade, not per-poll) so years of history is still
        # tiny, and long-term trend charts need them to survive — pruning
        # grade_result at 30 days also contradicted its own "append-only"
        # DDL comment (see metric_store_schema.py).
        # G4 — roll rtt_sample up into daily_rollup BEFORE the raw rows are
        # deleted below, so long-term trend charts survive the 30-day window.
        self.rollup_rtt_samples_before(cutoff)

        for tbl in (
            "rtt_sample", "device_state", "device_event", "cert_check",
            "service_check", "ha_detected",
            "modem_signal_log", "mesh_signal_log", "plugin_log",
        ):
            total_deleted += self._execute_write_counted(
                f"DELETE FROM {tbl} WHERE ts < ?", (cutoff,)
            )

        # G1 — app_traffic_sample previously had zero runtime prune callers and
        # grew unbounded (~1 row/10s while App Traffic is on). Reuses its own
        # existing (longer) retention default rather than the general `days`.
        total_deleted += self.prune_app_traffic_samples()

        # G9 — alert_fired (epoch ts) and device_events (TEXT datetime ts, the
        # audit trail — distinct from the already-pruned `device_event` singular
        # state-change table) had no retention at all.
        audit_cutoff = int(time.time()) - self._AUDIT_RETAIN_DAYS * 86400
        total_deleted += self._execute_write_counted(
            "DELETE FROM alert_fired WHERE ts < ?", (audit_cutoff,)
        )
        total_deleted += self._execute_write_counted(
            "DELETE FROM device_events WHERE ts < datetime('now', ?)",
            (f"-{self._AUDIT_RETAIN_DAYS} days",),
        )

        # G2 — VACUUM only when meaningful; it rewrites the whole file.
        self.vacuum_if_needed(total_deleted)
        return total_deleted

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

    # ── Read: network segments ────────────────────────────────────────────────

    def get_segments(self) -> List[NetworkSegment]:
        """Return all stored network segments ordered by id."""
        rows = self._execute_read(
            "SELECT id, name, cidr, color, description, auto_created "
            "FROM network_segments ORDER BY id",
            (),
        )
        return [
            NetworkSegment(
                id=r["id"],
                name=r["name"],
                cidr=r["cidr"],
                color=r["color"],
                description=r["description"] or "",
                auto_created=r["auto_created"],
            )
            for r in rows
        ]

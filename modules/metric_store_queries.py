"""
MetricStore query mixin — all read-only query methods for MetricStore.

Extracted from modules/metric_store.py (S2-1 sprint split).
MetricStoreQueryMixin is used via multiple inheritance in MetricStore.
All symbols are accessible through MetricStore instances as before.
"""
import time
from typing import Dict, List, Optional

from modules.metric_store_schema import (
    CertCheckPoint, DeviceEvent, DeviceStatePoint, HaDetectedPoint,
    KnownDevice, MeshSignalPoint, ModemSignalPoint, RttPoint,
    ServiceCheckPoint, SpeedTestPoint,
)


class MetricStoreQueryMixin:
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

    # ── Read: RTT history ─────────────────────────────────────────────────────

    def query_rtt_history(self, host: str, hours: float = 24.0) -> List[RttPoint]:
        """Return RTT samples for `host` over the last `hours`, oldest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, host, rtt_ms, loss_pct, jitter_ms FROM rtt_sample "
            "WHERE host = ? AND ts >= ? ORDER BY ts ASC",
            (host, since),
        )
        return [RttPoint(r["ts"], r["host"], r["rtt_ms"], r["loss_pct"], r["jitter_ms"])
                for r in rows]

    def query_all_rtt_hosts(self, hours: float = 24.0) -> List[str]:
        """Return distinct host names with RTT samples in the window."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT DISTINCT host FROM rtt_sample WHERE ts >= ?", (since,)
        )
        return [r["host"] for r in rows]

    def query_all_state_ips(self, hours: float = 720.0) -> List[str]:
        """Return distinct IPs with device_state samples in the window."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT DISTINCT ip FROM device_state WHERE ts >= ?", (since,)
        )
        return [r["ip"] for r in rows]

    def query_uptime_table(
        self, hours_list: Optional[List[float]] = None,
    ) -> List[Dict]:
        """Return one row per monitored IP with uptime % for each window."""
        if hours_list is None:
            hours_list = [24.0, 168.0, 720.0]
        ips = self.query_all_state_ips(hours=720.0)
        rows = []
        for ip in ips:
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

    # ── Read: device state history ────────────────────────────────────────────

    def query_device_state_history(
        self, ip: str, hours: float = 24.0,
    ) -> List[DeviceStatePoint]:
        """Return device state snapshots for `ip` over the last `hours`."""
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
        """Return uptime % for `ip` in the given window. Returns 100.0 if no samples."""
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

    # ── Read: device events ───────────────────────────────────────────────────

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

    # ── Read: speed test history ──────────────────────────────────────────────

    def query_speed_test_history(
        self, hours: float = 168.0, limit: int = 200,
    ) -> List[SpeedTestPoint]:
        """Return speed test results within the last `hours`, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, download_mbps, upload_mbps, ping_ms, "
            "server_name, server_city, server_country,"
            " network_type, signal_bars, nr5g_rsrp, nr5g_sinr, nr5g_band, lte_rsrp, lte_band,"
            " cell_id, enb_id, mcc, mnc, wan_ip,"
            " nr5g_rsrq, nr5g_pci, nr5g_arfcn, lte_snr, lte_rsrq, lte_pci, lte_earfcn "
            "FROM speed_test WHERE ts >= ? "
            "ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [
            SpeedTestPoint(
                ts=r["ts"], download_mbps=r["download_mbps"],
                upload_mbps=r["upload_mbps"], ping_ms=r["ping_ms"],
                server_name=r["server_name"], server_city=r["server_city"],
                server_country=r["server_country"],
                network_type=r["network_type"], signal_bars=r["signal_bars"],
                nr5g_rsrp=r["nr5g_rsrp"], nr5g_sinr=r["nr5g_sinr"],
                nr5g_band=r["nr5g_band"], lte_rsrp=r["lte_rsrp"],
                lte_band=r["lte_band"], cell_id=r["cell_id"],
                enb_id=r["enb_id"], mcc=r["mcc"], mnc=r["mnc"],
                wan_ip=r["wan_ip"], nr5g_rsrq=r["nr5g_rsrq"],
                nr5g_pci=r["nr5g_pci"], nr5g_arfcn=r["nr5g_arfcn"],
                lte_snr=r["lte_snr"], lte_rsrq=r["lte_rsrq"],
                lte_pci=r["lte_pci"], lte_earfcn=r["lte_earfcn"],
            )
            for r in rows
        ]

    # ── Read: CVE lifecycle ───────────────────────────────────────────────────

    def list_cve_lifecycles(self, state_filter: Optional[str] = None) -> List[dict]:
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

    # ── Read: alert tracking ──────────────────────────────────────────────────

    def get_unacked_alerts(self, older_than_s: int = 0) -> List[dict]:
        """Return alerts that have not been acknowledged."""
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

    def get_last_event_time(self, rule_prefix: str) -> Optional[float]:
        """Return Unix timestamp of the most recent matching alert, or None."""
        rows = self._execute_read(
            "SELECT MAX(ts) AS t FROM alert_fired WHERE rule_name LIKE ?",
            (f"{rule_prefix}%",),
        )
        val = rows[0]["t"] if rows else None
        return float(val) if val is not None else None

    # ── Read: modem signal log ────────────────────────────────────────────────

    def query_modem_signal_log(
        self, hours: float = 168.0, limit: int = 500,
    ) -> List[ModemSignalPoint]:
        """Return modem signal log entries within the last `hours`, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, network_type, signal_bars, cell_id, enb_id, mcc, mnc, wan_ip,"
            " nr5g_band, nr5g_rsrp, nr5g_sinr, nr5g_rsrq, nr5g_pci, nr5g_arfcn,"
            " lte_band, lte_rsrp, lte_snr, lte_rsrq, lte_pci, lte_earfcn "
            "FROM modem_signal_log WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [
            ModemSignalPoint(
                ts=r["ts"], network_type=r["network_type"], signal_bars=r["signal_bars"],
                cell_id=r["cell_id"], enb_id=r["enb_id"], mcc=r["mcc"], mnc=r["mnc"],
                wan_ip=r["wan_ip"], nr5g_band=r["nr5g_band"], nr5g_rsrp=r["nr5g_rsrp"],
                nr5g_sinr=r["nr5g_sinr"], nr5g_rsrq=r["nr5g_rsrq"], nr5g_pci=r["nr5g_pci"],
                nr5g_arfcn=r["nr5g_arfcn"], lte_band=r["lte_band"], lte_rsrp=r["lte_rsrp"],
                lte_snr=r["lte_snr"], lte_rsrq=r["lte_rsrq"], lte_pci=r["lte_pci"],
                lte_earfcn=r["lte_earfcn"],
            )
            for r in rows
        ]

    # ── Read: mesh signal log ─────────────────────────────────────────────────

    def query_mesh_signal_log(
        self, hours: float = 168.0, limit: int = 500,
    ) -> List[MeshSignalPoint]:
        """Return mesh signal log entries within the last `hours`, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT ts, unit_count, online_count, worst_unit, worst_rssi "
            "FROM mesh_signal_log WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [
            MeshSignalPoint(
                ts=r["ts"], unit_count=r["unit_count"], online_count=r["online_count"],
                worst_unit=r["worst_unit"], worst_rssi=r["worst_rssi"],
            )
            for r in rows
        ]

    # ── Read: plugin log ──────────────────────────────────────────────────────

    def query_plugin_log(
        self,
        plugin_name: Optional[str] = None,
        hours: float = 168.0,
        limit: int = 500,
    ) -> List[dict]:
        """Return plugin log entries within the last `hours`, newest first."""
        import json
        since = int(time.time()) - int(hours * 3600)
        if plugin_name:
            rows = self._execute_read(
                "SELECT ts, plugin_name, data FROM plugin_log "
                "WHERE ts >= ? AND plugin_name = ? ORDER BY ts DESC LIMIT ?",
                (since, plugin_name, limit),
            )
        else:
            rows = self._execute_read(
                "SELECT ts, plugin_name, data FROM plugin_log "
                "WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
                (since, limit),
            )
        result = []
        for row in rows:
            try:
                data_dict = json.loads(row["data"])
            except Exception:
                data_dict = {}
            result.append({
                "ts": row["ts"],
                "plugin_name": row["plugin_name"],
                "data": data_dict,
            })
        return result

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

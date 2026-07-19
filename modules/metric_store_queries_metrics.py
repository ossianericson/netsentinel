"""
Time-series metric query methods for MetricStore.

Extracted from metric_store_queries.py (E3 sprint split).
Covers RTT, speed test, CVE, alerts, modem, mesh, and plugin logs.
Included in MetricStoreQueryMixin via multiple inheritance.
"""
import time
from typing import Dict, List, Optional, Sequence

from modules.metric_store_schema import (
    MeshSignalPoint, ModemSignalPoint, RttPoint, SpeedTestPoint,
)


class _MetricsQueriesMixin:
    """Time-series metric query methods.

    Requires self._execute_read(sql, params) from the host class.
    """

    # ── RTT history ───────────────────────────────────────────────────────────

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

    def query_rtt_weekly_avg(self) -> Optional[Dict[str, object]]:
        """Return {"this_avg", "this_n", "last_avg", "last_n"} across ALL
        hosts for the trailing 14-day window, split at the 7-day boundary.
        Returns None if there is no data in the window at all.

        G11: replaces trend_page._update_rtt_headline()'s main-thread
        per-host query_rtt_history() loop (14 days x every host, pulling
        every raw sample into Python) with a single indexed SQL aggregate.
        rtt_ms == -1.0 (unreachable sentinel) is excluded, matching the old
        Python loop's `if rtt is None or rtt <= 0: continue` filter.
        """
        now = int(time.time())
        window_start = now - 14 * 86400
        week_boundary = now - 7 * 86400
        rows = self._execute_read(
            "SELECT "
            "  AVG(CASE WHEN ts >= ? THEN rtt_ms END) AS this_avg, "
            "  COUNT(CASE WHEN ts >= ? THEN 1 END) AS this_n, "
            "  AVG(CASE WHEN ts < ? THEN rtt_ms END) AS last_avg, "
            "  COUNT(CASE WHEN ts < ? THEN 1 END) AS last_n "
            "FROM rtt_sample WHERE ts >= ? AND rtt_ms > 0",
            (week_boundary, week_boundary, week_boundary, week_boundary, window_start),
        )
        r = rows[0] if rows else None
        if not r or not r["this_n"]:
            return None
        return {
            "this_avg": float(r["this_avg"]),
            "this_n": int(r["this_n"]),
            "last_avg": float(r["last_avg"]) if r["last_avg"] is not None else None,
            "last_n": int(r["last_n"] or 0),
        }

    def query_all_rtt_hosts(self, hours: float = 24.0) -> List[str]:
        """Return distinct host names with RTT samples in the window."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT DISTINCT host FROM rtt_sample WHERE ts >= ?", (since,)
        )
        return [r["host"] for r in rows]

    # ── Speed test history ────────────────────────────────────────────────────

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

    # ── CVE lifecycle ─────────────────────────────────────────────────────────

    def list_cve_lifecycles(self, state_filter: Optional[str] = None) -> List[dict]:
        """Return all CVE lifecycle rows, optionally filtered by state."""
        _CVE_COLS = (
            "id, cve_id, service, host, state, owner, notes, "
            "cvss_score, severity, description, opened_ts, updated_ts"
        )
        if state_filter:
            rows = self._execute_read(
                f"SELECT {_CVE_COLS} FROM cve_lifecycle "
                "WHERE state=? ORDER BY cvss_score DESC, opened_ts ASC",
                (state_filter,),
            )
        else:
            rows = self._execute_read(
                f"SELECT {_CVE_COLS} FROM cve_lifecycle "
                "ORDER BY cvss_score DESC, opened_ts ASC",
                (),
            )
        return [dict(r) for r in rows]

    # ── Alert tracking ────────────────────────────────────────────────────────

    def get_unacked_alerts(
        self,
        older_than_s: int = 0,
        rule_types: Optional[Sequence[str]] = None,
    ) -> List[dict]:
        """Return alerts that have not been acknowledged.

        `rule_types`, when given, restricts the result to those stable rule-type
        enum values (see `modules/alert_types.py`) — used to scope the Security
        badge/list to security-relevant alerts only.
        """
        cutoff = int(time.time()) - older_than_s
        sql = (
            "SELECT id, ts, rule_name, host, severity, message, "
            "acked_ts, acked_by, acked_comment, escalated, rule_type "
            "FROM alert_fired WHERE acked_ts IS NULL AND ts <= ?"
        )
        params: List = [cutoff]
        if rule_types:
            placeholders = ", ".join("?" for _ in rule_types)
            sql += f" AND rule_type IN ({placeholders})"
            params.extend(rule_types)
        sql += " ORDER BY ts ASC"
        rows = self._execute_read(sql, tuple(params))
        return [dict(r) for r in rows]

    def get_recent_alerts(self, hours: float = 24.0, limit: int = 200) -> List[dict]:
        """Return recent fired alerts, newest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT id, ts, rule_name, host, severity, message, "
            "acked_ts, acked_by, acked_comment, escalated "
            "FROM alert_fired WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        )
        return [dict(r) for r in rows]

    def get_alert_history(
        self, hours: float = 24.0, limit: int = 500, unacked_only: bool = False
    ) -> List[dict]:
        """Alert History page's query. Same shape as get_recent_alerts(), plus
        an unacked_only path that drops the time bound entirely -- so an
        unacked alert older than any selectable window is still reachable
        (see get_unacked_alerts(), which has no time bound either; this keeps
        the two in agreement). Ordered oldest-first when unacked_only, to
        match get_unacked_alerts()'s own ordering."""
        if unacked_only:
            rows = self._execute_read(
                "SELECT id, ts, rule_name, host, severity, message, "
                "acked_ts, acked_by, acked_comment, escalated "
                "FROM alert_fired WHERE acked_ts IS NULL ORDER BY ts ASC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in rows]
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT id, ts, rule_name, host, severity, message, "
            "acked_ts, acked_by, acked_comment, escalated "
            "FROM alert_fired WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
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

    # ── Modem signal log ──────────────────────────────────────────────────────

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

    # ── Mesh signal log ───────────────────────────────────────────────────────

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

    # ── Plugin log ────────────────────────────────────────────────────────────

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

    # ── App traffic history (Sprint 6) ────────────────────────────────────────

    def query_app_traffic_category_totals(self, hours: float = 24.0) -> Dict[str, int]:
        """Return {category: total_bytes} across all hosts for the last `hours`."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT category, SUM(bytes_total) AS total FROM app_traffic_sample "
            "WHERE ts >= ? GROUP BY category ORDER BY total DESC",
            (since,),
        )
        return {r["category"]: int(r["total"] or 0) for r in rows}

    def query_app_traffic_device_breakdown(
        self, category: str, hours: float = 24.0,
    ) -> List[dict]:
        """Return [{label, mac, bytes_total}] for one category, busiest first."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT mac, label, SUM(bytes_total) AS total FROM app_traffic_sample "
            "WHERE ts >= ? AND category = ? GROUP BY mac, label ORDER BY total DESC",
            (since, category),
        )
        return [
            {"mac": r["mac"], "label": r["label"], "bytes_total": int(r["total"] or 0)}
            for r in rows
        ]

    def query_app_traffic_cdn_breakdown(
        self, category: str, hours: float = 24.0,
    ) -> List[dict]:
        """Return [{cdn, bytes_total}] for one category, busiest first (S6-2)."""
        since = int(time.time()) - int(hours * 3600)
        rows = self._execute_read(
            "SELECT COALESCE(cdn, 'Other') AS cdn_name, SUM(bytes_total) AS total "
            "FROM app_traffic_sample WHERE ts >= ? AND category = ? "
            "GROUP BY cdn_name ORDER BY total DESC",
            (since, category),
        )
        return [
            {"cdn": r["cdn_name"], "bytes_total": int(r["total"] or 0)}
            for r in rows
        ]

    def query_app_traffic_hourly_distribution(
        self, category: Optional[str] = None, hours: float = 168.0,
    ) -> Dict[int, int]:
        """Return {hour_of_day(0-23): total_bytes} for the last `hours` (S6-5).

        G11: SQL GROUP BY bucketing instead of pulling every row into Python —
        this table is unbounded-until-pruned (G1), so the old per-row loop
        scaled with total rows collected, not with the requested window.
        `strftime('%H', ts, 'unixepoch', 'localtime')` buckets by the same
        local hour-of-day that `time.localtime(ts).tm_hour` used to.
        """
        since = int(time.time()) - int(hours * 3600)
        if category:
            rows = self._execute_read(
                "SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER) AS hr, "
                "SUM(bytes_total) AS total FROM app_traffic_sample "
                "WHERE ts >= ? AND category = ? GROUP BY hr",
                (since, category),
            )
        else:
            rows = self._execute_read(
                "SELECT CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER) AS hr, "
                "SUM(bytes_total) AS total FROM app_traffic_sample "
                "WHERE ts >= ? GROUP BY hr",
                (since,),
            )
        return {int(r["hr"]): int(r["total"] or 0) for r in rows}

    def query_app_traffic_category_totals_range(
        self, hours_ago_start: float, hours_ago_end: float,
    ) -> Dict[str, int]:
        """Return {category: bytes} for the window (now-hours_ago_end, now-hours_ago_start].

        Used to compare arbitrary same-length windows (e.g. this week vs last
        week) per category — see ui/widgets/usage_insights_card.py (S6-3).
        """
        now = int(time.time())
        until_ts = now - int(hours_ago_start * 3600)
        since_ts = now - int(hours_ago_end * 3600)
        rows = self._execute_read(
            "SELECT category, SUM(bytes_total) AS total FROM app_traffic_sample "
            "WHERE ts >= ? AND ts <= ? GROUP BY category ORDER BY total DESC",
            (since_ts, until_ts),
        )
        return {r["category"]: int(r["total"] or 0) for r in rows}

    def query_app_traffic_weekly_totals(self) -> Dict[str, int]:
        """Return {"this_week": bytes, "last_week": bytes} (S6-3/S6-5).

        G11: single SQL aggregate instead of pulling every row in the 14-day
        window into Python and summing there.
        """
        now = int(time.time())
        this_week_start = now - 7 * 86400
        last_week_start = now - 14 * 86400
        rows = self._execute_read(
            "SELECT "
            "  SUM(CASE WHEN ts >= ? THEN bytes_total ELSE 0 END) AS this_week, "
            "  SUM(CASE WHEN ts < ? THEN bytes_total ELSE 0 END) AS last_week "
            "FROM app_traffic_sample WHERE ts >= ?",
            (this_week_start, this_week_start, last_week_start),
        )
        r = rows[0] if rows else {}
        return {
            "this_week": int(r["this_week"] or 0) if r else 0,
            "last_week": int(r["last_week"] or 0) if r else 0,
        }

    def query_app_traffic_active_device_count(
        self, category: Optional[str] = None, seconds: float = 60.0,
    ) -> int:
        """Return the count of distinct MACs seen in the last `seconds` (S6-6)."""
        since = int(time.time()) - int(seconds)
        if category:
            rows = self._execute_read(
                "SELECT COUNT(DISTINCT mac) AS n FROM app_traffic_sample "
                "WHERE ts >= ? AND category = ?",
                (since, category),
            )
        else:
            rows = self._execute_read(
                "SELECT COUNT(DISTINCT mac) AS n FROM app_traffic_sample WHERE ts >= ?",
                (since,),
            )
        return int(rows[0]["n"] or 0) if rows else 0

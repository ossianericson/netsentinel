"""
Uptime / device-state query methods for MetricStore.

Extracted from metric_store_queries.py (E3 sprint split).
Included in MetricStoreQueryMixin via multiple inheritance.
"""
import time
from typing import Dict, List, Optional

from modules.metric_store_schema import DeviceEvent, DeviceStatePoint


class _UptimeQueriesMixin:
    """Uptime and device-state query methods.

    Requires self._execute_read(sql, params) from the host class.
    """

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
        """Return one row per monitored IP with uptime % for each window.

        Uses 1 + len(hours_list) queries total (not N+1+N*M) by aggregating
        all IPs in a single GROUP BY pass per window.
        """
        if hours_list is None:
            hours_list = [24.0, 168.0, 720.0]
        now = int(time.time())
        max_hours = max(hours_list)
        since_max = now - int(max_hours * 3600)

        # Query 1: latest hostname per IP — SQLite's max-row selection rule
        # picks the non-aggregated column from the row with MAX(ts).
        hn_rows = self._execute_read(
            "SELECT ip, MAX(ts) AS last_ts, hostname "
            "FROM device_state "
            "WHERE ts >= ? AND hostname IS NOT NULL "
            "GROUP BY ip",
            (since_max,),
        )
        hostnames: Dict[str, str] = {r["ip"]: r["hostname"] for r in hn_rows}

        # Queries 2..N: one GROUP BY per window — all IPs aggregated at once.
        window_data: Dict[str, Dict[str, float]] = {}
        for h in hours_list:
            since_h = now - int(h * 3600)
            agg_rows = self._execute_read(
                "SELECT ip, COUNT(*) AS total, "
                "SUM(CASE WHEN state = 'UP' THEN 1 ELSE 0 END) AS up_count "
                "FROM device_state WHERE ts >= ? GROUP BY ip",
                (since_h,),
            )
            for r in agg_rows:
                ip = r["ip"]
                if ip not in window_data:
                    window_data[ip] = {}
                total = r["total"] or 0
                up = r["up_count"] or 0
                window_data[ip][str(h)] = (
                    round(100.0 * up / total, 2) if total else None
                )

        all_ips = set(hostnames.keys()) | set(window_data.keys())
        rows = []
        for ip in sorted(all_ips):
            entry: Dict = {"ip": ip, "hostname": hostnames.get(ip)}
            for h in hours_list:
                entry[str(h)] = window_data.get(ip, {}).get(str(h))
            rows.append(entry)
        return rows

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

    def query_uptime_pct(self, ip: str, hours: float = 24.0) -> Optional[float]:
        """Return uptime % for `ip` in the given window.

        Returns None when there are no samples (device not yet monitored or
        outside the window), so callers can display '—' rather than a
        misleading '100%'.
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
            return None
        return round(100.0 * row["up_count"] / row["total"], 2)

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

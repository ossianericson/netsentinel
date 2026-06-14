"""
Time-series metric query methods for MetricStore.

Extracted from metric_store_queries.py (E3 sprint split).
Covers RTT, speed test, CVE, alerts, modem, mesh, and plugin logs.
Included in MetricStoreQueryMixin via multiple inheritance.
"""
import time
from typing import List, Optional

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

    def get_unacked_alerts(self, older_than_s: int = 0) -> List[dict]:
        """Return alerts that have not been acknowledged."""
        cutoff = int(time.time()) - older_than_s
        rows = self._execute_read(
            "SELECT id, ts, rule_name, host, severity, message, "
            "acked_ts, acked_by, acked_comment, escalated "
            "FROM alert_fired WHERE acked_ts IS NULL AND ts <= ? "
            "ORDER BY ts ASC",
            (cutoff,),
        )
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

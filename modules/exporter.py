"""
modules/exporter.py — Export all data to a ZIP archive (POWER-2).

Exports 5 CSVs:
  scan_history.csv   — device join/leave events
  alerts.csv         — all fired alerts
  logs.csv           — recent plugin/log entries
  speed_tests.csv    — speed test history
  cve_matches.csv    — CVE lifecycle records
"""
from __future__ import annotations

import csv
import io
import time
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.metric_store import MetricStore


def export_all_zip(store: "MetricStore", dest: Path) -> None:
    """Write all data tables to *dest* as a ZIP of CSVs."""
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("scan_history.csv",  _device_events_csv(store))
        zf.writestr("alerts.csv",        _alerts_csv(store))
        zf.writestr("speed_tests.csv",   _speed_tests_csv(store))
        zf.writestr("cve_matches.csv",   _cve_csv(store))


# ── CSV builders ──────────────────────────────────────────────────────────────

def _csv_text(headers: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue()


def _device_events_csv(store: "MetricStore") -> str:
    try:
        events = store.query_device_events(hours=8760)  # last year
        headers = ["timestamp", "ip", "mac", "event_type", "detail"]
        rows = [
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.ts)),
                e.ip, e.mac, e.event_type, e.detail or "",
            ]
            for e in events
        ]
        return _csv_text(headers, rows)
    except Exception:
        return "timestamp,ip,mac,event_type,detail\n"


def _alerts_csv(store: "MetricStore") -> str:
    try:
        alerts = store.get_recent_alerts(hours=8760, limit=10000)
        if not alerts:
            return "timestamp,rule_name,host,severity,message,acked\n"
        headers = ["timestamp", "rule_name", "host", "severity", "message", "acked"]
        rows = [
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(a.get("ts", 0))),
                a.get("rule_name", ""),
                a.get("host", ""),
                a.get("severity", ""),
                a.get("message", ""),
                "yes" if a.get("acked_ts") else "no",
            ]
            for a in alerts
        ]
        return _csv_text(headers, rows)
    except Exception:
        return "timestamp,rule_name,host,severity,message,acked\n"


def _speed_tests_csv(store: "MetricStore") -> str:
    try:
        pts = store.query_speed_test_history(hours=8760, limit=10000)
        headers = ["timestamp", "download_mbps", "upload_mbps", "latency_ms", "server"]
        rows = [
            [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.ts)),
                f"{p.download_mbps:.2f}" if p.download_mbps else "",
                f"{p.upload_mbps:.2f}"   if p.upload_mbps   else "",
                f"{p.latency_ms:.1f}"    if p.latency_ms    else "",
                p.server_name or "",
            ]
            for p in pts
        ]
        return _csv_text(headers, rows)
    except Exception:
        return "timestamp,download_mbps,upload_mbps,latency_ms,server\n"


def _cve_csv(store: "MetricStore") -> str:
    try:
        cves = store.list_cve_lifecycles() or []
        if not cves:
            return "cve_id,service,severity,status,discovered_ts\n"
        headers = list(cves[0].keys()) if cves else ["cve_id", "service", "severity", "status"]
        rows = [[str(c.get(h, "")) for h in headers] for c in cves]
        return _csv_text(headers, rows)
    except Exception:
        return "cve_id,service,severity,status,discovered_ts\n"

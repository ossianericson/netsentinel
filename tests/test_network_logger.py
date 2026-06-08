"""
Behavioural tests for modules/network_logger.py

Covers:
  - CSV output format  — header row matches enabled options; data rows match
  - Outage detection   — _compute_summary() groups consecutive FAILs correctly

No real network calls, no real files — tmp_path fixture for disk writes,
subprocess.run patched out for any ping calls.
"""

import csv
import sys
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.network_logger import (
    NetworkLogger,
    LogEntry,
    _compute_summary,
    load_log_file,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry(host="8.8.8.8", status="OK", rtt=12.0,
           ts="2026-04-26T10:00:00", jitter=-1.0, dns_ms=-1.0,
           http_status=-1, http_ms=-1.0, arp_event=""):
    return LogEntry(
        timestamp=ts, host=host, rtt_ms=rtt if status != "FAIL" else -1.0,
        status=status, jitter_ms=jitter, dns_ms=dns_ms,
        http_status=http_status, http_ms=http_ms, arp_event=arp_event,
    )


def _make_ping_run(rtt_line="time=12ms"):
    """Return a subprocess.run mock that returns a ping reply."""
    def _run(cmd, **kwargs):
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = rtt_line
        return mock
    return _run


# ── CSV format — header row ───────────────────────────────────────────────────

class TestCsvHeader:
    def test_base_header_columns(self, tmp_path):
        log_file = tmp_path / "test.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            logger.start()
            time.sleep(0.1)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)

        assert header == ["timestamp", "host", "rtt_ms", "status"]

    def test_jitter_appended_when_enabled(self, tmp_path):
        log_file = tmp_path / "jitter.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
            enable_jitter=True,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            logger.start()
            time.sleep(0.1)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert "jitter_ms" in header

    def test_dns_appended_when_enabled(self, tmp_path):
        log_file = tmp_path / "dns.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
            enable_dns=True,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            with patch("socket.getaddrinfo", return_value=[]):
                logger.start()
                time.sleep(0.1)
                logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert "dns_ms" in header

    def test_http_columns_appended_when_enabled(self, tmp_path):
        log_file = tmp_path / "http.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
            enable_http=True,
        )
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", side_effect=_make_ping_run()):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                logger.start()
                time.sleep(0.1)
                logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert "http_status" in header
        assert "http_ms" in header

    def test_arp_event_appended_when_enabled(self, tmp_path):
        log_file = tmp_path / "arp.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
            enable_arp=True,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            logger.start()
            time.sleep(0.1)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert "arp_event" in header

    def test_all_options_full_header(self, tmp_path):
        log_file = tmp_path / "full.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
            enable_jitter=True,
            enable_dns=True,
            enable_http=True,
            enable_arp=True,
        )
        mock_resp = MagicMock()
        mock_resp.status = 204
        mock_resp.read.return_value = b""
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("subprocess.run", side_effect=_make_ping_run()):
            with patch("socket.getaddrinfo", return_value=[]):
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    logger.start()
                    time.sleep(0.1)
                    logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f))

        expected = ["timestamp", "host", "rtt_ms", "status",
                    "jitter_ms", "dns_ms", "http_status", "http_ms", "arp_event"]
        assert header == expected


# ── CSV format — data rows ────────────────────────────────────────────────────

class TestCsvDataRows:
    def test_data_row_written_for_each_target(self, tmp_path):
        log_file = tmp_path / "data.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8", "1.1.1.1"],
            log_path=log_file,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            logger.start()
            time.sleep(0.15)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        # First row is header; should have at least one data row per target
        data_rows = rows[1:]
        hosts = [r[1] for r in data_rows if len(r) > 1]
        assert "8.8.8.8" in hosts
        assert "1.1.1.1" in hosts

    def test_fail_row_has_minus_one_rtt(self, tmp_path):
        """When ping fails, rtt_ms column must be -1."""
        log_file = tmp_path / "fail.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
        )

        def _fail_run(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            mock.stdout = ""
            return mock

        with patch("subprocess.run", side_effect=_fail_run):
            logger.start()
            time.sleep(0.15)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        data_rows = [r for r in rows[1:] if len(r) >= 4]
        assert any(r[2] == "-1" for r in data_rows)

    def test_fail_row_has_fail_status(self, tmp_path):
        log_file = tmp_path / "fail_status.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
        )

        def _fail_run(cmd, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            mock.stdout = ""
            return mock

        with patch("subprocess.run", side_effect=_fail_run):
            logger.start()
            time.sleep(0.15)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        data_rows = [r for r in rows[1:] if len(r) >= 4]
        assert any(r[3] == "FAIL" for r in data_rows)

    def test_timestamp_column_is_iso8601(self, tmp_path):
        import re
        log_file = tmp_path / "ts.csv"
        logger = NetworkLogger(
            interval_s=9999,
            targets=["8.8.8.8"],
            log_path=log_file,
        )
        with patch("subprocess.run", side_effect=_make_ping_run()):
            logger.start()
            time.sleep(0.15)
            logger.stop()

        with open(log_file, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

        data_rows = [r for r in rows[1:] if r]
        assert data_rows, "No data rows written"
        ts = data_rows[0][0]
        # ISO 8601 local: YYYY-MM-DDTHH:MM:SS
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ts), f"Bad timestamp: {ts!r}"


# ── load_log_file round-trip ──────────────────────────────────────────────────

class TestLoadLogFile:
    def _write_csv(self, path: Path, rows: list):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "host", "rtt_ms", "status"])
            writer.writerows(rows)

    def test_loads_entries_correctly(self, tmp_path):
        csv_file = tmp_path / "log.csv"
        self._write_csv(csv_file, [
            ["2026-04-26T10:00:00", "8.8.8.8", "12.4", "OK"],
            ["2026-04-26T10:01:00", "8.8.8.8", "-1",   "FAIL"],
        ])
        summary = load_log_file(csv_file)
        assert summary.total_pings == 2
        assert summary.failed_pings == 1

    def test_uptime_calculation(self, tmp_path):
        csv_file = tmp_path / "uptime.csv"
        # 9 OK + 1 FAIL → 90 %
        rows = [["2026-04-26T10:00:00", "8.8.8.8", "10.0", "OK"]] * 9
        rows.append(["2026-04-26T10:09:00", "8.8.8.8", "-1", "FAIL"])
        self._write_csv(csv_file, rows)
        summary = load_log_file(csv_file)
        assert abs(summary.uptime_pct - 90.0) < 0.1

    def test_missing_file_returns_empty_summary(self, tmp_path):
        summary = load_log_file(tmp_path / "does_not_exist.csv")
        assert summary.total_pings == 0
        assert summary.entries == []


# ── Outage detection — _compute_summary ──────────────────────────────────────

class TestOutageDetection:
    def _ts(self, minute: int) -> str:
        return f"2026-04-26T10:{minute:02d}:00"

    def test_no_outage_when_all_ok(self):
        entries = [_entry(ts=self._ts(i)) for i in range(5)]
        summary = _compute_summary(entries, "")
        assert summary.outages == []

    def test_single_fail_creates_outage(self):
        entries = [
            _entry(ts=self._ts(0), status="OK"),
            _entry(ts=self._ts(1), status="FAIL"),
            _entry(ts=self._ts(2), status="OK"),
        ]
        summary = _compute_summary(entries, "")
        assert len(summary.outages) == 1

    def test_consecutive_fails_grouped_as_one_outage(self):
        entries = [
            _entry(ts=self._ts(0), status="OK"),
            _entry(ts=self._ts(1), status="FAIL"),
            _entry(ts=self._ts(2), status="FAIL"),
            _entry(ts=self._ts(3), status="FAIL"),
            _entry(ts=self._ts(4), status="OK"),
        ]
        summary = _compute_summary(entries, "")
        assert len(summary.outages) == 1
        assert summary.outages[0].consecutive_fails == 3

    def test_two_separate_outages_detected(self):
        entries = [
            _entry(ts=self._ts(0), status="OK"),
            _entry(ts=self._ts(1), status="FAIL"),
            _entry(ts=self._ts(2), status="OK"),
            _entry(ts=self._ts(3), status="FAIL"),
            _entry(ts=self._ts(4), status="OK"),
        ]
        summary = _compute_summary(entries, "")
        assert len(summary.outages) == 2

    def test_outage_start_and_end_timestamps(self):
        entries = [
            _entry(ts=self._ts(0), status="OK"),
            _entry(ts=self._ts(1), status="FAIL"),
            _entry(ts=self._ts(2), status="FAIL"),
            _entry(ts=self._ts(3), status="OK"),
        ]
        summary = _compute_summary(entries, "")
        assert len(summary.outages) == 1
        assert summary.outages[0].start == self._ts(1)
        assert summary.outages[0].end   == self._ts(2)

    def test_uptime_pct_with_outage(self):
        # 4 OK + 1 FAIL from 5 total → 80 %
        entries = [_entry(ts=self._ts(i), status="OK") for i in range(4)]
        entries.append(_entry(ts=self._ts(4), status="FAIL"))
        summary = _compute_summary(entries, "")
        assert abs(summary.uptime_pct - 80.0) < 0.1

    def test_outage_duration_estimated_from_interval(self):
        # 2 FAILs at 1-minute intervals → ~120 s
        entries = [
            _entry(ts=self._ts(1), status="FAIL"),
            _entry(ts=self._ts(2), status="FAIL"),
        ]
        summary = _compute_summary(entries, "")
        assert len(summary.outages) == 1
        # Duration = consecutive_fails * estimated_interval
        # With only FAILs the interval gap is 60 s → 2 × 60 = 120
        assert summary.outages[0].duration_s == pytest.approx(120.0, abs=5)

    def test_failed_pings_counter(self):
        entries = [
            _entry(status="OK"),
            _entry(status="FAIL"),
            _entry(status="FAIL"),
        ]
        summary = _compute_summary(entries, "")
        assert summary.failed_pings == 2

    def test_slow_pings_counter(self):
        entries = [
            _entry(status="OK"),
            _entry(status="SLOW", rtt=200.0),
            _entry(status="SLOW", rtt=180.0),
        ]
        summary = _compute_summary(entries, "")
        assert summary.slow_pings == 2

    def test_avg_rtt_excludes_failed(self):
        entries = [
            _entry(status="OK",   rtt=10.0),
            _entry(status="OK",   rtt=20.0),
            _entry(status="FAIL"),           # rtt = -1, must not skew average
        ]
        summary = _compute_summary(entries, "")
        assert abs(summary.avg_rtt_ms - 15.0) < 0.1

    def test_outages_per_host_independent(self):
        """Outage grouping must be per-host, not global."""
        entries = [
            _entry(host="8.8.8.8",  ts=self._ts(0), status="OK"),
            _entry(host="8.8.8.8",  ts=self._ts(1), status="FAIL"),
            _entry(host="1.1.1.1",  ts=self._ts(0), status="OK"),
            _entry(host="1.1.1.1",  ts=self._ts(1), status="OK"),
        ]
        summary = _compute_summary(entries, "")
        outage_hosts = [o.host for o in summary.outages]
        assert "8.8.8.8" in outage_hosts
        assert "1.1.1.1" not in outage_hosts

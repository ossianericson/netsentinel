"""Tests for modules/network_log_writer.py — see also test_sprint20_splits.py."""


def test_import():
    from modules import network_log_writer as m
    assert hasattr(m, "LogEntry")
    assert hasattr(m, "LogSummary")
    assert hasattr(m, "OutageSummary")
    assert hasattr(m, "AnalysisFinding")
    assert hasattr(m, "_compute_summary")
    assert hasattr(m, "analyse_log")
    assert hasattr(m, "load_log_file")
    assert hasattr(m, "list_log_files")


def test_log_entry_defaults():
    from modules.network_log_writer import LogEntry
    e = LogEntry(timestamp="2026-01-01T00:00:00", host="8.8.8.8",
                 rtt_ms=12.5, status="OK")
    assert e.jitter_ms == -1.0
    assert e.dns_ms == -1.0
    assert e.arp_event == ""


def test_compute_summary_with_entries():
    from modules.network_log_writer import LogEntry, _compute_summary
    entries = [
        LogEntry(timestamp="2026-01-01T00:00:00", host="8.8.8.8", rtt_ms=10.0, status="OK"),
        LogEntry(timestamp="2026-01-01T00:01:00", host="8.8.8.8", rtt_ms=-1.0, status="FAIL"),
        LogEntry(timestamp="2026-01-01T00:02:00", host="8.8.8.8", rtt_ms=15.0, status="OK"),
    ]
    s = _compute_summary(entries, "/tmp/test.csv")
    assert s.total_pings == 3
    assert s.failed_pings == 1
    assert s.uptime_pct < 100.0


def test_analyse_log_returns_findings():
    from modules.network_log_writer import LogSummary, analyse_log
    s = LogSummary()
    findings = analyse_log(s)
    assert len(findings) >= 1
    assert findings[0].severity in ("HIGH", "WARN", "INFO")


def test_default_log_dir():
    from pathlib import Path
    from modules.network_log_writer import _default_log_dir
    d = _default_log_dir()
    assert isinstance(d, Path)

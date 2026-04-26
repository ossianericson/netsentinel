"""
Tests for modules/network_logger.py :: analyse_log()

All tests use in-memory fixture data — no network, no disk, no GUI.
"""

import sys
import os
import pytest

# Make the project root importable without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.network_logger import (
    LogEntry,
    LogSummary,
    OutageSummary,
    AnalysisFinding,
    analyse_log,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _entry(host: str, status: str = "OK", rtt: float = 10.0, ts: str = "2026-04-26T10:00:00") -> LogEntry:
    return LogEntry(timestamp=ts, host=host, rtt_ms=rtt if status != "FAIL" else -1.0, status=status)


def _outage(host: str, start: str, end: str, duration_s: float = 120.0) -> OutageSummary:
    return OutageSummary(host=host, start=start, end=end,
                         duration_s=duration_s, peak_latency_ms=-1.0, consecutive_fails=5)


def _severities(findings):
    return [f.severity for f in findings]


def _categories(findings):
    return [f.category for f in findings]


# ── Test: clean summary returns INFO / Clean ──────────────────────────────────

def test_clean_summary_returns_info():
    summary = LogSummary(
        entries=[_entry("8.8.8.8", "OK", 10.0)],
        total_pings=100,
        failed_pings=0,
        slow_pings=0,
        avg_rtt_ms=10.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    assert len(findings) == 1
    assert findings[0].severity == "INFO"
    assert findings[0].category == "Clean"


# ── Test: single outage → WARN ────────────────────────────────────────────────

def test_single_outage_is_warn():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=[_outage("8.8.8.8", "2026-04-26T02:00:00", "2026-04-26T02:02:00", 120.0)],
        total_pings=100,
        uptime_pct=98.0,
    )
    findings = analyse_log(summary)
    sev = _severities(findings)
    assert "WARN" in sev
    assert "INFO" not in sev or "Outages" in _categories(findings)


# ── Test: 5+ outages → HIGH ───────────────────────────────────────────────────

def test_five_outages_is_high():
    outages = [
        _outage("8.8.8.8", f"2026-04-26T0{i}:00:00", f"2026-04-26T0{i}:02:00")
        for i in range(5)
    ]
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=outages,
        total_pings=300,
        uptime_pct=90.0,
    )
    findings = analyse_log(summary)
    assert any(f.severity == "HIGH" and f.category == "Outages" for f in findings)


# ── Test: findings sorted HIGH before WARN before INFO ───────────────────────

def test_findings_sorted_high_first():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=[_outage("8.8.8.8", "2026-04-26T02:00:00", "2026-04-26T02:02:00")] * 5,
        total_pings=200,
        failed_pings=10,
        slow_pings=120,       # >50% → HIGH latency finding
        avg_rtt_ms=200.0,
        avg_jitter_ms=60.0,   # ≥50 → HIGH jitter
        uptime_pct=85.0,
        arp_events=["NEW 192.168.1.99=aa:bb:cc:dd:ee:ff"] * 3,  # ≥3 → HIGH ARP
    )
    findings = analyse_log(summary)
    order = {"HIGH": 0, "WARN": 1, "INFO": 2}
    positions = [order[f.severity] for f in findings]
    assert positions == sorted(positions), "Findings are not sorted HIGH → WARN → INFO"


# ── Test: high jitter ─────────────────────────────────────────────────────────

def test_high_jitter_finding():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        avg_rtt_ms=20.0,
        avg_jitter_ms=55.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    jitter_findings = [f for f in findings if f.category == "Jitter"]
    assert len(jitter_findings) == 1
    assert jitter_findings[0].severity == "HIGH"


def test_moderate_jitter_finding():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        avg_rtt_ms=20.0,
        avg_jitter_ms=25.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    jitter_findings = [f for f in findings if f.category == "Jitter"]
    assert len(jitter_findings) == 1
    assert jitter_findings[0].severity == "WARN"


def test_low_jitter_no_finding():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        avg_rtt_ms=20.0,
        avg_jitter_ms=5.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    assert not any(f.category == "Jitter" for f in findings)


# ── Test: DNS vs ping ratio ───────────────────────────────────────────────────

def test_dns_much_higher_than_ping_is_warn():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        avg_rtt_ms=10.0,
        avg_dns_ms=80.0,   # 8× ratio
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    dns_findings = [f for f in findings if f.category == "DNS"]
    assert len(dns_findings) == 1
    assert dns_findings[0].severity == "WARN"
    assert "×" in dns_findings[0].title


def test_dns_slightly_higher_than_ping_is_info():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        avg_rtt_ms=10.0,
        avg_dns_ms=35.0,   # 3.5× ratio
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    dns_findings = [f for f in findings if f.category == "DNS"]
    assert len(dns_findings) == 1
    assert dns_findings[0].severity == "INFO"


# ── Test: slow pings threshold ────────────────────────────────────────────────

def test_50pct_slow_pings_is_high():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=100,
        slow_pings=55,
        avg_rtt_ms=10.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    lat = [f for f in findings if f.category == "Latency"]
    assert len(lat) == 1
    assert lat[0].severity == "HIGH"


def test_25pct_slow_pings_is_warn():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=100,
        slow_pings=25,
        avg_rtt_ms=10.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    lat = [f for f in findings if f.category == "Latency"]
    assert len(lat) == 1
    assert lat[0].severity == "WARN"


def test_5pct_slow_pings_no_latency_finding():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=100,
        slow_pings=5,
        avg_rtt_ms=10.0,
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    assert not any(f.category == "Latency" for f in findings)


# ── Test: ARP events ──────────────────────────────────────────────────────────

def test_one_arp_event_is_warn():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        arp_events=["NEW 192.168.1.5=aa:bb:cc:dd:ee:ff"],
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    arp = [f for f in findings if f.category == "ARP"]
    assert len(arp) == 1
    assert arp[0].severity == "WARN"


def test_three_arp_events_is_high():
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        total_pings=50,
        arp_events=[
            "NEW 192.168.1.5=aa:bb:cc:dd:ee:ff",
            "CHANGED 192.168.1.1 old->new",
            "NEW 192.168.1.6=11:22:33:44:55:66",
        ],
        uptime_pct=100.0,
    )
    findings = analyse_log(summary)
    arp = [f for f in findings if f.category == "ARP"]
    assert len(arp) == 1
    assert arp[0].severity == "HIGH"


# ── Test: DNS-only failure (google.com fails, 8.8.8.8 ok) ────────────────────

def test_dns_only_failure_detected():
    entries = (
        [_entry("google.com", "FAIL", -1.0, f"2026-04-26T10:{i:02d}:00") for i in range(30)]
        + [_entry("8.8.8.8", "OK",  10.0, f"2026-04-26T10:{i:02d}:00") for i in range(30)]
    )
    summary = LogSummary(
        entries=entries,
        total_pings=60,
        uptime_pct=75.0,
    )
    findings = analyse_log(summary)
    dns_fail = [f for f in findings if "DNS resolution failing" in f.title]
    assert len(dns_fail) == 1
    assert dns_fail[0].severity == "HIGH"


def test_symmetric_failure_not_dns_only():
    """If both google.com and 8.8.8.8 fail equally, the DNS-only check should NOT fire."""
    entries = (
        [_entry("google.com", "FAIL", -1.0, f"2026-04-26T10:{i:02d}:00") for i in range(20)]
        + [_entry("8.8.8.8",   "FAIL", -1.0, f"2026-04-26T10:{i:02d}:00") for i in range(20)]
    )
    summary = LogSummary(entries=entries, total_pings=40, uptime_pct=60.0)
    findings = analyse_log(summary)
    dns_only = [f for f in findings if "DNS resolution failing" in f.title]
    assert len(dns_only) == 0


# ── Test: time-of-day clustering ─────────────────────────────────────────────

def test_outages_clustered_in_same_window():
    outages = [
        _outage("8.8.8.8", f"2026-04-26T03:{i:02d}:00", f"2026-04-26T03:{i:02d}:30")
        for i in range(4)   # all in 03:00–04:00
    ]
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=outages,
        total_pings=200,
        uptime_pct=97.0,
    )
    findings = analyse_log(summary)
    pattern = [f for f in findings if f.category == "Pattern" and "concentrated" in f.title]
    assert len(pattern) == 1
    assert "03:00" in pattern[0].title


# ── Test: all-hosts-simultaneously finding ────────────────────────────────────

def test_all_hosts_affected_simultaneously():
    entries = [
        _entry("8.8.8.8", "OK"),
        _entry("1.1.1.1", "OK"),
    ]
    outages = [
        _outage("8.8.8.8", "2026-04-26T02:00:00", "2026-04-26T02:02:00"),
        _outage("1.1.1.1", "2026-04-26T02:00:00", "2026-04-26T02:02:00"),
    ]
    summary = LogSummary(
        entries=entries,
        outages=outages,
        total_pings=100,
        uptime_pct=96.0,
    )
    findings = analyse_log(summary)
    simul = [f for f in findings if "simultaneously" in f.title]
    assert len(simul) == 1


def test_partial_host_failure_no_simultaneous_finding():
    entries = [_entry("8.8.8.8"), _entry("1.1.1.1")]
    outages = [_outage("8.8.8.8", "2026-04-26T02:00:00", "2026-04-26T02:02:00")]
    summary = LogSummary(
        entries=entries,
        outages=outages,
        total_pings=100,
        uptime_pct=98.0,
    )
    findings = analyse_log(summary)
    simul = [f for f in findings if "simultaneously" in f.title]
    assert len(simul) == 0


# ── Test: periodic outage pattern ────────────────────────────────────────────

def test_periodic_outage_detected():
    # Outages every exactly 30 minutes
    times = [
        ("2026-04-26T01:00:00", "2026-04-26T01:00:30"),
        ("2026-04-26T01:30:00", "2026-04-26T01:30:30"),
        ("2026-04-26T02:00:00", "2026-04-26T02:00:30"),
        ("2026-04-26T02:30:00", "2026-04-26T02:30:30"),
    ]
    outages = [_outage("8.8.8.8", s, e, 30.0) for s, e in times]
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=outages,
        total_pings=200,
        uptime_pct=97.0,
    )
    findings = analyse_log(summary)
    periodic = [f for f in findings if "recurring" in f.title]
    assert len(periodic) == 1
    assert "30" in periodic[0].title


def test_irregular_outages_no_periodic_finding():
    times = [
        ("2026-04-26T01:00:00", "2026-04-26T01:00:30"),
        ("2026-04-26T01:07:00", "2026-04-26T01:07:30"),   # 7 min gap
        ("2026-04-26T03:40:00", "2026-04-26T03:40:30"),   # 153 min gap
        ("2026-04-26T03:42:00", "2026-04-26T03:42:30"),   # 2 min gap
    ]
    outages = [_outage("8.8.8.8", s, e, 30.0) for s, e in times]
    summary = LogSummary(
        entries=[_entry("8.8.8.8")],
        outages=outages,
        total_pings=200,
        uptime_pct=97.0,
    )
    findings = analyse_log(summary)
    periodic = [f for f in findings if "recurring" in f.title]
    assert len(periodic) == 0

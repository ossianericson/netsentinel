"""
Tests for ReportScheduler and report_scheduler module (T2#9).
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from modules.metric_store import MetricStore
from modules.report_scheduler import ReportConfig, ReportScheduler, generate_status_report


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "test.db")
    yield s
    s.close()


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "reports"
    return d


@pytest.fixture
def config(out_dir):
    return ReportConfig(output_dir=out_dir, interval_hours=24.0, enabled=True)


# ── ReportConfig defaults ─────────────────────────────────────────────────────

class TestReportConfig:
    def test_default_interval_is_24h(self):
        c = ReportConfig()
        assert c.interval_hours == 24.0

    def test_default_enabled_true(self):
        assert ReportConfig().enabled is True

    def test_default_formats_html(self):
        assert "html" in ReportConfig().formats

    def test_default_max_reports(self):
        assert ReportConfig().max_reports == 30

    def test_custom_interval(self):
        c = ReportConfig(interval_hours=168.0)
        assert c.interval_hours == 168.0


# ── generate_status_report ────────────────────────────────────────────────────

class TestGenerateStatusReport:
    def test_returns_html_string(self, store):
        html = generate_status_report(store)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_contains_title(self, store):
        html = generate_status_report(store)
        assert "NetSentinel" in html

    def test_contains_timestamp(self, store):
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        html = generate_status_report(store)
        assert today in html

    def test_empty_store_no_crash(self, store):
        """Should produce valid HTML even with no MetricStore data."""
        html = generate_status_report(store)
        assert len(html) > 200

    def test_uptime_section_present(self, store):
        html = generate_status_report(store)
        assert "Device Uptime" in html

    def test_cert_section_present(self, store):
        html = generate_status_report(store)
        assert "TLS Certificate" in html

    def test_service_section_present(self, store):
        html = generate_status_report(store)
        assert "Service Heartbeat" in html

    def test_events_section_present(self, store):
        html = generate_status_report(store)
        assert "Device Events" in html

    def test_uptime_row_rendered(self, store):
        store.record_device_state("192.168.1.1", mac="aa:bb:cc:dd:ee:ff",
                                   hostname=None, state="UP")
        html = generate_status_report(store)
        assert "192.168.1.1" in html

    def test_cert_row_rendered(self, store):
        store.record_cert_check(
            "example.com", 443,
            days_remaining=60, subject="CN=example.com",
            issuer="Let's Encrypt", not_after="2024-12-31",
            is_expired=False, is_self_signed=False, error="",
        )
        html = generate_status_report(store)
        assert len(html.split("example.com")) > 1, "Cert hostname not rendered in status report HTML"

    def test_service_row_rendered(self, store):
        store.record_service_check("myserver.local", 80, up=True, rtt_ms=5.0, label="HTTP")
        html = generate_status_report(store)
        assert "myserver.local" in html

    def test_event_row_rendered(self, store):
        store.record_device_event("10.0.0.5", event_type="JOINED", mac="aa:bb:cc:00:11:22")
        html = generate_status_report(store)
        assert "JOINED" in html

    def test_device_silent_for_a_day_does_not_break_the_report(self, store):
        """A device seen 3 days ago has no samples in the 24 h window: query_uptime_table() gives
        that window as None. min() over it raised TypeError, so every scheduled report and
        Reports -> Copy summary failed on any network where one device went quiet (live,
        2026-09-18: 5 of 26 monitored devices)."""
        three_days_ago = int(time.time()) - 3 * 86400
        store.record_device_state("10.0.0.9", mac=None, hostname="old-tv", state="UP",
                                  ts=three_days_ago)
        html = generate_status_report(store)
        row = next(tr for tr in html.split("<tr>") if "old-tv" in tr)
        assert "—" in row, f"the empty 24 h window must read as no data, not a number: {row!r}"

    def test_device_with_no_samples_in_any_window_reads_as_no_data(self, store, monkeypatch):
        """Unreachable with today's windows (the 30 d window always has the row's samples), but a
        caller passing other windows gets all-None rows: that is no data, not a crash."""
        monkeypatch.setattr(store, "query_uptime_table", lambda: [
            {"ip": "10.0.0.7", "hostname": "ghost", "24.0": None, "168.0": None, "720.0": None},
        ])
        html = generate_status_report(store)
        row = next(tr for tr in html.split("<tr>") if "ghost" in tr)
        assert row.count("<td>—</td>") == 3, row

    def test_kpi_total_devices_in_html(self, store):
        store.record_device_state("10.0.0.1", mac=None, hostname=None, state="UP")
        store.record_device_state("10.0.0.2", mac=None, hostname=None, state="UP")
        html = generate_status_report(store)
        assert "Devices Monitored" in html

    def test_expiring_cert_flagged(self, store):
        store.record_cert_check(
            "soon.com", 443,
            days_remaining=10, subject="CN=soon.com",
            issuer="CA", not_after="2024-02-01",
            is_expired=False, is_self_signed=False, error="",
        )
        html = generate_status_report(store)
        assert "EXPIRING" in html

    def test_expired_cert_flagged(self, store):
        store.record_cert_check(
            "old.com", 443,
            days_remaining=0, subject="CN=old.com",
            issuer="CA", not_after="2020-01-01",
            is_expired=True, is_self_signed=False, error="",
        )
        html = generate_status_report(store)
        assert "EXPIRED" in html

    def test_down_service_flagged(self, store):
        store.record_service_check("host", 80, up=False, rtt_ms=None, error="refused")
        html = generate_status_report(store)
        assert "DOWN" in html


# ── ReportScheduler ───────────────────────────────────────────────────────────

class TestReportScheduler:
    def test_generate_now_creates_file(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        paths = sched.generate_now()
        assert len(paths) == 1
        assert paths[0].exists()
        assert paths[0].suffix == ".html"

    def test_generate_now_creates_output_dir(self, store, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        config = ReportConfig(output_dir=nested, enabled=True)
        sched = ReportScheduler(store=store, config=config)
        sched.generate_now()
        assert nested.exists()

    def test_generate_now_calls_on_saved(self, store, out_dir, config):
        cb = MagicMock()
        sched = ReportScheduler(store=store, config=config, on_saved=cb)
        sched.generate_now()
        cb.assert_called_once()
        called_path = cb.call_args[0][0]
        assert isinstance(called_path, Path)

    def test_generate_now_returns_empty_when_disabled(self, store, out_dir):
        config = ReportConfig(output_dir=out_dir, enabled=False)
        sched = ReportScheduler(store=store, config=config)
        paths = sched.generate_now()
        assert paths == []

    def test_is_due_true_when_never_run(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        assert sched.is_due() is True

    def test_is_due_false_immediately_after_generate(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        sched.generate_now()
        assert sched.is_due() is False

    def test_is_due_false_when_disabled(self, store, out_dir):
        config = ReportConfig(output_dir=out_dir, enabled=False)
        sched = ReportScheduler(store=store, config=config)
        assert sched.is_due() is False

    def test_run_if_due_generates_when_due(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        paths = sched.run_if_due()
        assert len(paths) == 1

    def test_run_if_due_skips_when_not_due(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        sched.generate_now()           # marks last_run = now
        paths = sched.run_if_due()     # should skip
        assert paths == []

    def test_prune_removes_excess_reports(self, store, out_dir):
        config = ReportConfig(output_dir=out_dir, max_reports=3, enabled=True)
        sched = ReportScheduler(store=store, config=config)
        # Generate 5 reports
        for _ in range(5):
            sched.generate_now()
            time.sleep(0.01)   # ensure unique timestamps
        reports = list(out_dir.glob("netsentinel-report-*.html"))
        assert len(reports) <= 3

    def test_set_config_updates(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        new_dir = out_dir / "sub"
        sched.set_config(ReportConfig(output_dir=new_dir, enabled=True))
        assert sched.get_config().output_dir == new_dir

    def test_html_file_content_is_valid(self, store, out_dir, config):
        sched = ReportScheduler(store=store, config=config)
        paths = sched.generate_now()
        content = paths[0].read_text(encoding="utf-8")
        assert "<html" in content
        assert "</html>" in content

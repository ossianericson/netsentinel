"""
Tests for the DNS Benchmark tab (F-23 -- ui/help.py's "DNS & Stability" tip
claimed a 'DNS Benchmark' tab that did not exist anywhere in the app).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from modules.network_diagnostics import DnsResult  # noqa: E402
from ui.tabs_scan import _ScanTabsMixin  # noqa: E402


class _FakeHost(_ScanTabsMixin):
    """Minimal stand-in — only needs the widgets _build_m5_dns_benchmark_tab() builds."""

    def __init__(self) -> None:
        self._nav_rail_go_to = MagicMock()
        self._start_full_scan = MagicMock()


@pytest.fixture
def host():
    h = _FakeHost()
    # Keep the returned container widget alive — its layout parents the
    # buttons/table under test, and Python GC would destroy the C++ objects
    # immediately once the builder call's local `w` goes out of scope (RULE-WIN4).
    h._test_widget = h._build_m5_dns_benchmark_tab()
    yield h
    try:
        h._test_widget.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already deleted
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


class TestDnsBenchmarkTabExists:
    def test_tab_builder_creates_run_button_and_table(self, host):
        assert host._dns_bench_btn.text() == "Run DNS Benchmark"
        assert host._dns_bench_table.columnCount() == 4


class TestDnsBenchmarkDispatch:
    def test_run_button_starts_worker(self, host):
        with patch("workers.dns_benchmark_worker.DnsBenchmarkWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_dns_benchmark()
        mock_cls.assert_called_once()
        host._dns_bench_worker.start.assert_called_once()

    def test_skips_if_already_running(self, host):
        host._dns_bench_worker = MagicMock()
        host._dns_bench_worker.isRunning.return_value = True
        with patch("workers.dns_benchmark_worker.DnsBenchmarkWorker") as mock_cls:
            host._start_dns_benchmark()
        mock_cls.assert_not_called()


class TestDnsBenchmarkResult:
    def test_populates_table_with_all_four_resolvers(self, host):
        results = [
            DnsResult(server="System DNS", domain="google.com", latency_ms=5.0, resolved_ip="1.1.1.1", status="OK"),
            DnsResult(server="Cloudflare", domain="google.com", latency_ms=250.0, resolved_ip="1.1.1.1", status="SLOW"),
            DnsResult(server="Google",     domain="google.com", latency_ms=-1.0, resolved_ip="", status="FAIL"),
            DnsResult(server="Quad9",      domain="google.com", latency_ms=9.0, resolved_ip="9.9.9.9", status="OK"),
        ]
        host._on_dns_benchmark_result(results)
        assert host._dns_bench_table.rowCount() == 4
        assert host._dns_bench_table.item(0, 0).text() == "System DNS"
        assert host._dns_bench_table.item(1, 1).text() == "250 ms"
        assert host._dns_bench_table.item(2, 1).text() == "failed"
        assert host._dns_bench_status.text() == "Done."
        assert host._dns_bench_btn.isEnabled()

    def test_error_updates_status_and_reenables_button(self, host):
        host._dns_bench_btn.setEnabled(False)
        host._on_dns_benchmark_error("network unreachable")
        assert "network unreachable" in host._dns_bench_status.text()
        assert host._dns_bench_btn.isEnabled()

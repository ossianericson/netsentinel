"""
Tests for ui/tabs_recon.py::_ReconTabsMixin._start_cve_lookup (F-43).

CVE Lookup previously only read service versions from _ps_table (the separate
"Port Scanner" tool in Analysis) -- running "Port Scan (TCP)" (the tool the
help text and F-43's claim actually reference) and then clicking Lookup CVEs
reported "No service versions found." This covers the fix: versions are now
collected from both tables.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QTableWidgetItem  # noqa: E402

from ui.tabs_helpers import _table  # noqa: E402
from ui.tabs_recon import _ReconTabsMixin  # noqa: E402


class _FakeHost(_ReconTabsMixin):
    """Minimal stand-in exposing only the attributes _start_cve_lookup touches."""

    def __init__(self) -> None:
        self._cve_worker = None
        self._cve_target_input = MagicMock()
        self._cve_target_input.text.return_value = ""
        self._ps_table = _table(["Port", "Service", "Version", "Banner", "Risk"])
        self._recon_syn_table = _table(
            ["Port", "State", "Protocol", "Service", "Version", "Banner", "CVEs"]
        )
        self._recon_cve_table = _table(
            ["CVE ID", "Service", "Score", "Severity", "Published", "Description"]
        )
        self._cve_status = MagicMock()
        self._nav_set_scan_state = MagicMock()
        self._on_cve_result = MagicMock()
        self._advance_security_audit = MagicMock()


def _versions_passed_to_worker(mock_worker_cls) -> list[str]:
    _, kwargs = mock_worker_cls.call_args
    return sorted(kwargs["service_versions"])


class TestCveLookupSourceTables:
    def test_reads_versions_from_port_scan_tcp_table(self):
        """Port Scan (TCP) is the tool F-43's claim names -- it must feed CVE Lookup."""
        host = _FakeHost()
        host._recon_syn_table.insertRow(0)
        host._recon_syn_table.setItem(0, 4, QTableWidgetItem("OpenSSH 8.9p1"))

        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cve_lookup()

        mock_cls.assert_called_once()
        assert _versions_passed_to_worker(mock_cls) == ["OpenSSH 8.9p1"]

    def test_reads_versions_from_port_scanner_table(self):
        """The existing Analysis "Port Scanner" source must keep working."""
        host = _FakeHost()
        host._ps_table.insertRow(0)
        host._ps_table.setItem(0, 2, QTableWidgetItem("Apache/2.4.54"))

        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cve_lookup()

        mock_cls.assert_called_once()
        assert _versions_passed_to_worker(mock_cls) == ["Apache/2.4.54"]

    def test_merges_versions_from_both_tables(self):
        host = _FakeHost()
        host._ps_table.insertRow(0)
        host._ps_table.setItem(0, 2, QTableWidgetItem("Apache/2.4.54"))
        host._recon_syn_table.insertRow(0)
        host._recon_syn_table.setItem(0, 4, QTableWidgetItem("OpenSSH 8.9p1"))

        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cve_lookup()

        assert _versions_passed_to_worker(mock_cls) == ["Apache/2.4.54", "OpenSSH 8.9p1"]

    def test_no_versions_anywhere_reports_status_and_skips_worker(self):
        host = _FakeHost()
        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            host._start_cve_lookup()
        mock_cls.assert_not_called()
        host._cve_status.setText.assert_called_once()
        assert "No service versions found" in host._cve_status.setText.call_args[0][0]

    def test_no_versions_advances_queue_when_part_of_security_audit(self):
        """F-02: when CVE Lookup is dispatched from the 'Run Selected' audit queue
        and no port-scan data exists yet, the queue must advance instead of
        stalling silently (previously nothing ever called _advance_security_audit()
        on this path)."""
        host = _FakeHost()
        host._pending_security_tools = ["CVE Lookup"]
        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            host._start_cve_lookup()
        mock_cls.assert_not_called()
        host._advance_security_audit.assert_called_once()

    def test_no_versions_outside_audit_does_not_advance(self):
        """A manual click (not part of the audit queue) must not touch the queue."""
        host = _FakeHost()
        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            host._start_cve_lookup()
        mock_cls.assert_not_called()
        host._advance_security_audit.assert_not_called()

    def test_manual_input_overrides_tables(self):
        host = _FakeHost()
        host._cve_target_input.text.return_value = "Nginx 1.20"
        host._recon_syn_table.insertRow(0)
        host._recon_syn_table.setItem(0, 4, QTableWidgetItem("OpenSSH 8.9p1"))

        with patch("workers.scan_worker.CVELookupWorker") as mock_cls:
            mock_cls.return_value = MagicMock()
            host._start_cve_lookup()

        assert _versions_passed_to_worker(mock_cls) == ["Nginx 1.20"]

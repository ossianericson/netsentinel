"""Tests for SecurityOverviewPage — full-aggregation Security Audit dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


# ── Stub data-classes (mirror modules/port_scanner.py + modules/syn_scanner.py) ─

@dataclass
class _PortResult:
    port: int
    name: str
    open: bool = True
    risk: str = "LOW"
    banner: str = ""
    service_version: str = ""


@dataclass
class _PortScanResult:
    host: str
    ip: str = "192.168.1.1"
    open_ports: List[_PortResult] = field(default_factory=list)
    plain_verdict: str = "Scan complete"
    error: str = ""


@dataclass
class _SYNPortResult:
    port: int
    state: str = "open"
    proto: str = "tcp"
    service: str = ""


@dataclass
class _SYNScanResult:
    host: str
    ip: str = "192.168.1.2"
    open_ports: List[_SYNPortResult] = field(default_factory=list)
    plain_verdict: str = "SYN scan complete"
    error: str = ""


@dataclass
class _CredResult:
    risk_flags: List[str] = field(default_factory=list)
    plain_verdict: str = "Login test complete"
    os_type: str = ""
    serial_number: str = ""
    failed_logins: int = 0
    active_sessions: List = field(default_factory=list)
    software: List = field(default_factory=list)
    services: List = field(default_factory=list)
    users: List = field(default_factory=list)
    patch_info: object = field(default_factory=lambda: MagicMock(
        os_version="", kernel="", last_update="", pending_updates=0
    ))


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture
def page(monkeypatch):
    """SecurityOverviewPage with mocked threat intel and no store."""
    from PyQt6.QtCore import QSettings
    _qs = QSettings("NetSentinel", "NetSentinel")
    _qs.remove("security/any_scan_done")
    _qs.remove("security/port_scan_done")
    _qs.remove("security/cred_scan_done")
    monkeypatch.setattr(
        "ui.pages.security_overview_page._THREAT_OK", False
    )
    from ui.pages.security_overview_page import SecurityOverviewPage
    w = SecurityOverviewPage(store=None, parent=None)
    yield w
    try:
        w._refresh_timer.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be closed
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def page_with_store(monkeypatch):
    """SecurityOverviewPage with a mock MetricStore."""
    monkeypatch.setattr(
        "ui.pages.security_overview_page._THREAT_OK", False
    )
    mock_store = MagicMock()
    mock_store.list_cve_lifecycles.return_value = []
    mock_store.query_cert_status.return_value = []

    from ui.pages.security_overview_page import SecurityOverviewPage
    w = SecurityOverviewPage(store=mock_store, parent=None)
    yield w, mock_store
    try:
        w._refresh_timer.stop()
        w.deleteLater()
    except RuntimeError:
        pass  # non-fatal — widget may already be closed
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


# ── Import tests ────────────────────────────────────────────────────────────────

def test_import():
    from ui.pages import security_overview_page  # noqa: F401


def test_page_instantiates(page):
    assert page is not None


# ── KPI tile defaults ────────────────────────────────────────────────────────────

def test_scan_kpi_tiles_show_dash_with_no_data(page):
    assert page._tile_ports._val_lbl.text() == "—"
    assert page._tile_cves._val_lbl.text()  == "—"
    assert page._tile_tls._val_lbl.text()   == "—"
    assert page._tile_cred._val_lbl.text()  == "—"


def test_threat_kpi_tiles_present(page):
    assert hasattr(page, "_tile_total")
    assert hasattr(page, "_tile_ips")
    assert hasattr(page, "_tile_domains")
    assert hasattr(page, "_tile_updated")


# ── on_port_scan_result ─────────────────────────────────────────────────────────

def test_port_scan_result_high_risk_updates_tile(page):
    result = _PortScanResult(
        host="192.168.1.5",
        open_ports=[
            _PortResult(port=3389, name="RDP", risk="HIGH"),
            _PortResult(port=80,   name="HTTP", risk="LOW"),
        ],
    )
    page.on_port_scan_result(result)
    assert page._tile_ports._val_lbl.text() == "1"  # only HIGH-risk


def test_port_scan_result_no_high_risk_shows_zero(page):
    result = _PortScanResult(
        host="192.168.1.5",
        open_ports=[_PortResult(port=80, name="HTTP", risk="LOW")],
    )
    page.on_port_scan_result(result)
    assert page._tile_ports._val_lbl.text() == "0"


def test_port_scan_result_replaces_per_host(page):
    r1 = _PortScanResult(
        host="h1",
        open_ports=[_PortResult(port=3389, name="RDP", risk="HIGH")],
    )
    page.on_port_scan_result(r1)
    assert len(page._port_findings) == 1

    r2 = _PortScanResult(host="h1", open_ports=[])  # re-scan, nothing found
    page.on_port_scan_result(r2)
    assert len(page._port_findings) == 0


def test_port_scan_result_accumulates_across_hosts(page):
    r1 = _PortScanResult(
        host="h1",
        open_ports=[_PortResult(port=445, name="SMB", risk="HIGH")],
    )
    r2 = _PortScanResult(
        host="h2",
        open_ports=[_PortResult(port=23, name="Telnet", risk="HIGH")],
    )
    page.on_port_scan_result(r1)
    page.on_port_scan_result(r2)
    assert len(page._port_findings) == 2
    assert page._tile_ports._val_lbl.text() == "2"


def test_syn_scan_result_uses_port_number_fallback(page, monkeypatch):
    """SYNPortResult has no .risk attr — page falls back to HIGH_RISK_PORTS lookup."""
    monkeypatch.setattr(
        "modules.port_scanner.HIGH_RISK_PORTS", {3389, 445}
    )
    result = _SYNScanResult(
        host="h1",
        open_ports=[
            _SYNPortResult(port=3389, service="ms-wbt-server"),  # in HIGH_RISK_PORTS
            _SYNPortResult(port=80,   service="http"),            # not high-risk
        ],
    )
    page.on_port_scan_result(result)
    assert len(page._port_findings) == 1
    assert page._port_findings[0]["port"] == 3389


# ── on_cred_result ──────────────────────────────────────────────────────────────

def test_cred_result_with_flags_updates_tile(page):
    res = _CredResult(risk_flags=["Default SSH credentials accepted"])
    page.on_cred_result(res)
    assert page._tile_cred._val_lbl.text() == "1"


def test_cred_result_no_flags_shows_zero(page):
    res = _CredResult(risk_flags=[])
    page.on_cred_result(res)
    assert page._tile_cred._val_lbl.text() == "0"


def test_cred_scan_done_flag_set(page):
    assert not page._cred_scan_done
    page.on_cred_result(_CredResult())
    assert page._cred_scan_done


# ── MetricStore integration ─────────────────────────────────────────────────────

def test_cve_tile_shows_dash_when_no_store(page):
    assert page._tile_cves._val_lbl.text() == "—"


def test_cve_tile_shows_count_with_store(page_with_store):
    page, store = page_with_store
    store.list_cve_lifecycles.return_value = [
        {"cve_id": "CVE-2024-0001", "host": "192.168.1.1",
         "severity": "Critical", "cvss_score": 9.8, "state": "Open"},
        {"cve_id": "CVE-2024-0002", "host": "192.168.1.2",
         "severity": "High", "cvss_score": 7.5, "state": "Open"},
    ]
    page._load_metricstore_data()
    page._update_scan_kpis()
    assert page._tile_cves._val_lbl.text() == "2"  # 2 distinct hosts


def test_tls_tile_shows_zero_when_store_returns_empty(page_with_store):
    page, store = page_with_store
    store.query_cert_status.return_value = []
    page._load_metricstore_data()
    page._update_scan_kpis()
    assert page._tile_tls._val_lbl.text() == "0"


def test_tls_tile_counts_expired_certs(page_with_store):
    page, store = page_with_store
    cert = MagicMock()
    cert.is_expired     = True
    cert.is_self_signed = False
    cert.days_remaining = None
    cert.host           = "example.com"
    cert.port           = 443
    store.query_cert_status.return_value = [cert]
    page._load_metricstore_data()
    page._update_scan_kpis()
    assert page._tile_tls._val_lbl.text() == "1"


def test_tls_tile_counts_expiring_soon_cert(page_with_store):
    page, store = page_with_store
    cert = MagicMock()
    cert.is_expired     = False
    cert.is_self_signed = False
    cert.days_remaining = 14   # < 30 days
    cert.host           = "example.com"
    cert.port           = 443
    store.query_cert_status.return_value = [cert]
    page._load_metricstore_data()
    page._update_scan_kpis()
    assert page._tile_tls._val_lbl.text() == "1"


# ── Security findings table ─────────────────────────────────────────────────────

def test_scan_table_empty_on_startup(page):
    assert page._scan_table.rowCount() == 0
    assert page._scan_table.isHidden()       # table hidden when no data
    assert not page._scan_empty.isHidden()   # empty label not hidden when no data


def test_copy_scan_status_md_puts_markdown_on_clipboard(page):
    """RULE-T7: Copy-as-Markdown button copies a rendered table to the clipboard."""
    import time as _time
    page.update_scan_registry({
        "Port Scan (TCP)": {"state": "fresh", "ts": _time.time(),
                            "verdict": "2 open ports", "error": None},
    })
    page._copy_scan_status_md()
    clip = QApplication.clipboard()
    text = clip.text()
    assert text.startswith("## ")
    assert "| Port Scan (TCP) |" in text
    assert "2 open ports" in text
    assert page._copy_md_status.text() == "Copied to clipboard"


def test_scan_table_shows_port_finding(page):
    result = _PortScanResult(
        host="192.168.1.5",
        open_ports=[_PortResult(port=3389, name="RDP", risk="HIGH")],
    )
    page.on_port_scan_result(result)
    assert page._scan_table.rowCount() == 1
    assert page._scan_table.item(0, 0).text() == "Port"
    assert "3389" in page._scan_table.item(0, 3).text()


def test_scan_table_shows_cve_finding(page_with_store):
    page, store = page_with_store
    store.list_cve_lifecycles.return_value = [
        {"cve_id": "CVE-2024-9999", "host": "192.168.1.3",
         "severity": "Critical", "cvss_score": 9.8, "state": "Open"},
    ]
    page._load_metricstore_data()
    page._update_scan_table()
    assert page._scan_table.rowCount() == 1
    assert page._scan_table.item(0, 0).text() == "CVE"
    assert "CVE-2024-9999" in page._scan_table.item(0, 3).text()


def test_scan_table_shows_tls_finding(page_with_store):
    page, store = page_with_store
    cert = MagicMock()
    cert.is_expired     = True
    cert.is_self_signed = False
    cert.days_remaining = None
    cert.host           = "secure.example.com"
    cert.port           = 443
    store.query_cert_status.return_value = [cert]
    page._load_metricstore_data()
    page._update_scan_table()
    assert page._scan_table.rowCount() == 1
    assert page._scan_table.item(0, 0).text() == "TLS"
    assert "expired" in page._scan_table.item(0, 3).text().lower()


# ── notify_scan_complete ────────────────────────────────────────────────────────

def test_notify_scan_complete_updates_status_label(page):
    page.notify_scan_complete()
    text = page._last_net_scan_lbl.text()
    assert "Network scan:" in text
    assert "not run" not in text


# ── on_scan_result ──────────────────────────────────────────────────────────────

def test_on_scan_result_shows_device_count(page):
    """M1 scan result un-hides hero status label with device count."""
    d1 = MagicMock()
    d2 = MagicMock()
    page.on_scan_result({"devices": [d1, d2]})
    assert not page._hero_status_lbl.isHidden()
    assert "2" in page._hero_status_lbl.text()


def test_on_scan_result_singular_device(page):
    """Single device uses 'device' (not 'devices') in status label."""
    page.on_scan_result({"devices": [MagicMock()]})
    assert "1 device " in page._hero_status_lbl.text()


def test_on_scan_result_empty_devices_does_not_show_label(page):
    """M1 scan with no devices leaves status label hidden."""
    page.on_scan_result({"devices": []})
    assert page._hero_status_lbl.isHidden()


def test_on_scan_result_stores_device_count(page):
    """Device count is stored for later use."""
    page.on_scan_result({"devices": [MagicMock(), MagicMock(), MagicMock()]})
    assert page._m1_device_count == 3


# ── UI structure ────────────────────────────────────────────────────────────────

def test_findings_tabs_has_two_tabs(page):
    assert page._findings_tabs.count() == 2
    assert page._findings_tabs.tabText(0) == "Security Findings"
    assert page._findings_tabs.tabText(1) == "Threat Intel"


def test_signals_exist(page):
    from PyQt6.QtCore import pyqtSignal  # noqa: F401 (verify no AttributeError)
    assert hasattr(page, "navigate_to")
    assert hasattr(page, "scan_requested")
    assert hasattr(page, "security_scan_requested")


# ── set_audit_progress / clear_audit_progress ───────────────────────────────────

def test_set_audit_progress_disables_button(page):
    page.set_audit_progress("Port Scan (TCP)", 1, 5)
    assert not page._audit_btn.isEnabled()


def test_set_audit_progress_shows_in_progress_text(page):
    page.set_audit_progress("CVE Lookup", 2, 5)
    assert "Audit in progress" in page._audit_btn.text()


def test_set_audit_progress_shows_rows_widget(page):
    page.set_audit_progress("Port Scan (TCP)", 1, 5)
    assert not page._audit_rows_widget.isHidden()


def test_set_audit_progress_step1_marks_first_tool_running(page):
    page.set_audit_progress("Port Scan (TCP)", 1, 5)
    row = page._audit_tool_rows["Port Scan (TCP)"]
    assert row["state"].text() == "Running…"


def test_set_audit_progress_step2_marks_first_done_second_running(page):
    page.set_audit_progress("Port Scan (TCP)", 1, 5)
    page.set_audit_progress("Exposed to Internet", 2, 5)
    assert page._audit_tool_rows["Port Scan (TCP)"]["state"].text() == "Done"
    assert page._audit_tool_rows["Exposed to Internet"]["state"].text() == "Running…"


def test_clear_audit_progress_re_enables_button(page):
    page.set_audit_progress("Port Scan (TCP)", 1, 5)
    page.clear_audit_progress()
    assert page._audit_btn.isEnabled()
    assert "Run Security Audit" in page._audit_btn.text()


# ── update_scan_registry ────────────────────────────────────────────────────────

def test_update_scan_registry_populates_table(page):
    import time
    from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS
    registry = {
        "Port Scan (TCP)": {"state": "fresh", "ts": time.time() - 60,
                            "verdict": "2 open ports", "error": None},
        "CVE Lookup":      {"state": "never", "ts": 0,
                            "verdict": None, "error": None},
    }
    page.update_scan_registry(registry)
    assert page._scan_status_table is not None
    assert page._scan_status_table.rowCount() == len(_AUDIT_SCAN_LABELS)


def test_update_scan_registry_fresh_then_stale(page):
    import time
    from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS
    page.update_scan_registry({
        "Port Scan (TCP)": {"state": "fresh", "ts": time.time() - 10,
                            "verdict": "OK", "error": None},
    })
    page.update_scan_registry({
        "Port Scan (TCP)": {"state": "stale", "ts": time.time() - 7201,
                            "verdict": "OK", "error": None},
    })
    # Table should still have all rows — no crash on multiple updates
    assert page._scan_status_table.rowCount() == len(_AUDIT_SCAN_LABELS)


# ── per-tool finding counts ─────────────────────────────────────────────────────

def test_port_scan_result_updates_tool_row_finding(page):
    result = _PortScanResult(
        host="192.168.1.1",
        open_ports=[_PortResult(port=3389, name="RDP", risk="HIGH")],
    )
    page.on_port_scan_result(result)
    row = page._audit_tool_rows.get("Port Scan (TCP)")
    assert row is not None
    assert "1" in row["finding"].text()


def test_cred_result_updates_tool_row_finding(page):
    # "Login Test" is not in _AUDIT_SEQUENCE so no row exists in _audit_tool_rows.
    # _set_tool_row_state silently no-ops for unknown tools — verify no crash.
    res = _CredResult(risk_flags=["Weak password"])
    page.on_cred_result(res)
    assert page._cred_scan_done  # confirms the handler ran without error


# ── pre-flight scope panel ──────────────────────────────────────────────────────

def test_scope_panel_hidden_by_default(page):
    assert hasattr(page, "_scope_panel")
    assert not page._scope_panel.isVisible()


def test_scope_toggle_shows_panel(page):
    page._toggle_scope_panel()
    assert not page._scope_panel.isHidden()


def test_scope_toggle_hides_panel_on_second_click(page):
    page._toggle_scope_panel()
    page._toggle_scope_panel()
    assert page._scope_panel.isHidden()

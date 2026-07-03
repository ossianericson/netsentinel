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
    # RULE-WIN6: reset EVERY persisted key the page reads at construction —
    # all 5 posture toggles, not just the original 3, or real machine state
    # (e.g. arp_watch enabled by the developer) leaks into the checkboxes.
    _reset_keys = (
        "security/any_scan_done",
        "security/port_scan_done",
        "security/cred_scan_done",
        "posture/port_sweep_enabled",
        "posture/cve_recheck_enabled",
        "posture/exposure_check_enabled",
        "posture/arp_watch_enabled",
        "posture/dhcp_watch_enabled",
    )
    _saved = {k: _qs.value(k) for k in _reset_keys if _qs.contains(k)}
    for _k in _reset_keys:
        _qs.remove(_k)
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
    # Restore the developer's real QSettings values wiped by the reset above
    for _k in _reset_keys:
        _qs.remove(_k)
    for _k, _v in _saved.items():
        _qs.setValue(_k, _v)


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

def test_notify_scan_complete_refreshes_scan_kpis(page):
    """notify_scan_complete pulls fresh MetricStore data without raising."""
    page.notify_scan_complete()


# ── on_scan_result ──────────────────────────────────────────────────────────────

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

def test_port_scan_result_updates_findings(page):
    result = _PortScanResult(
        host="192.168.1.1",
        open_ports=[_PortResult(port=3389, name="RDP", risk="HIGH")],
    )
    page.on_port_scan_result(result)
    assert len(page._port_findings) == 1


def test_cred_result_updates_flags(page):
    res = _CredResult(risk_flags=["Weak password"])
    page.on_cred_result(res)
    assert page._cred_scan_done  # confirms the handler ran without error


# ── V6 Sprint 3: Scheduled Posture Scans card ────────────────────────────────

def test_posture_toggles_default_off(page):
    assert page._posture_checks["port_sweep"].isChecked() is False
    assert page._posture_checks["cve_recheck"].isChecked() is False
    assert page._posture_checks["exposure_check"].isChecked() is False
    assert page._posture_checks["arp_watch"].isChecked() is False
    assert page._posture_checks["dhcp_watch"].isChecked() is False


def test_toggling_arp_watch_checkbox_persists_and_emits(page):
    from PyQt6.QtCore import QSettings
    received = []
    page.posture_scheduling_changed.connect(lambda key, enabled: received.append((key, enabled)))

    page._posture_checks["arp_watch"].setChecked(True)

    assert received == [("arp_watch", True)]
    qs = QSettings("NetSentinel", "NetSentinel")
    assert qs.value("posture/arp_watch_enabled", False, type=bool) is True
    qs.remove("posture/arp_watch_enabled")


def test_toggling_posture_checkbox_persists_and_emits(page):
    from PyQt6.QtCore import QSettings
    received = []
    page.posture_scheduling_changed.connect(lambda key, enabled: received.append((key, enabled)))

    page._posture_checks["port_sweep"].setChecked(True)

    assert received == [("port_sweep", True)]
    qs = QSettings("NetSentinel", "NetSentinel")
    assert qs.value("posture/port_sweep_enabled", False, type=bool) is True


def test_posture_toggle_restores_from_qsettings(monkeypatch):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue("posture/cve_recheck_enabled", True)
    monkeypatch.setattr("ui.pages.security_overview_page._THREAT_OK", False)

    from ui.pages.security_overview_page import SecurityOverviewPage
    w = SecurityOverviewPage(store=None, parent=None)
    try:
        assert w._posture_checks["cve_recheck"].isChecked() is True
    finally:
        w._refresh_timer.stop()
        w.deleteLater()
        qs.remove("posture/cve_recheck_enabled")
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()

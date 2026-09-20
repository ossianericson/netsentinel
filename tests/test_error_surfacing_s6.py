"""S6 — exports, dialogs and the remaining worker errors say what failed, why, and what next.

Behavioural counterparts (RULE-T7) to ratchet (a). Where a site holds the exception, the tests
raise a *real* one — a folder that does not exist, a file locked the way Excel locks it — and
never construct an ``Explanation`` by hand (RULE-DBG5).
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

_widgets: list = []


@pytest.fixture(autouse=True)
def _cleanup(qt_app):
    """RULE-WIN4: deleteLater() + pump, never plain refcount GC."""
    yield
    for w in _widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed
    _widgets.clear()
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _keep(widget):
    _widgets.append(widget)
    return widget


@pytest.fixture
def toasts(monkeypatch):
    """Every ToastManager.show(...) as (message, kind, kwargs)."""
    from ui.widgets.toast import ToastManager

    shown: list = []

    def _record(cls, message, kind="info", *args, **kwargs):
        shown.append((message, kind, args, kwargs))

    monkeypatch.setattr(ToastManager, "show", classmethod(_record))
    return shown


@pytest.fixture
def modals(monkeypatch):
    """Static QMessageBox.warning/critical calls — the pre-S6 failure channel."""
    calls: list = []
    for name in ("warning", "critical"):
        monkeypatch.setattr(
            QMessageBox, name,
            staticmethod(lambda *a, _n=name, **k: calls.append((_n, a, k))),
        )
    return calls


# ── 6.0 — a success must never render as a failure ──────────────────────────────

class _Host(QWidget):
    """A plain widget standing in for the mixin's Dashboard."""


def test_export_all_success_is_not_reported_as_failed(toasts, modals, monkeypatch, tmp_path):
    import modules.exporter
    from PyQt6.QtWidgets import QFileDialog
    from ui.export_mixin import _ExportMixin

    out = tmp_path / "all.zip"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr(modules.exporter, "export_all_zip", lambda store, path: path.write_bytes(b"PK"))
    host = _keep(_Host())
    host._store = object()

    _ExportMixin._on_export_all(host)

    assert modals == [], f"a successful export showed a failure dialog: {modals}"
    assert [kind for _m, kind, _a, _k in toasts] == ["success"]


def test_copy_summary_success_is_not_reported_as_failed(toasts, modals, monkeypatch):
    import modules.report_scheduler
    from ui.pages.reports_page import ReportsPage

    monkeypatch.setattr(modules.report_scheduler, "generate_status_report", lambda store: "summary")
    host = _keep(_Host())
    host._store = object()

    ReportsPage._copy_summary(host)

    assert modals == [], f"a successful copy showed a failure dialog: {modals}"
    assert QApplication.clipboard().text() == "summary"
    assert [kind for _m, kind, _a, _k in toasts] == ["success"]


def test_isp_complaint_copy_success_is_not_reported_as_failed(toasts, modals, monkeypatch):
    import modules.report_isp
    import ui.tabs_analysis_isp as isp
    from PyQt6.QtWidgets import QDialog

    monkeypatch.setattr(isp, "run_dialog", lambda dlg: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(modules.report_isp, "generate_isp_complaint_text", lambda **kw: "complaint")
    host = _keep(_Host())
    host._logger_worker = None

    isp._AnalysisIspMixin._copy_isp_complaint(host)

    assert modals == [], f"a successful copy showed a failure dialog: {modals}"
    assert QApplication.clipboard().text() == "complaint"
    assert [kind for _m, kind, _a, _k in toasts] == ["success"]


def test_network_map_png_save_success_is_confirmed(toasts, monkeypatch, tmp_path):
    from PyQt6.QtWidgets import QFileDialog
    from ui.pages.network_map_page import NetworkMapPage

    out = tmp_path / "map.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    host = _keep(_Host())

    NetworkMapPage._on_export_data(host, "data:image/png;base64,iVBORw0KGgo=")

    assert out.read_bytes() == b"\x89PNG\r\n\x1a\n"
    assert [kind for _m, kind, _a, _k in toasts] == ["success"], "the saved map was never confirmed"


# ── 6.1 — a failed save says why and offers another location (real failures, RULE-DBG5) ────

def _save_dialog_answers(monkeypatch, *paths):
    """QFileDialog.getSaveFileName returns each path in turn — one per export attempt."""
    from PyQt6.QtWidgets import QFileDialog

    queue = [str(p) for p in paths]
    asked: list = []

    def _answer(*_a, **_k):
        asked.append(True)
        return (queue.pop(0), "") if queue else ("", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(_answer))
    return asked


def _cve_host(rows=None):
    from ui.pages.cve_page import CvePage

    host = _keep(_Host())
    host._rows = rows if rows is not None else [
        {"cve_id": "CVE-2026-0001", "cvss_score": 9.8, "severity": "Critical"},
    ]
    host._export_csv = lambda: CvePage._export_csv(host)  # the retry re-runs the real method
    return host


def test_cve_export_into_a_missing_folder_explains_and_retries_elsewhere(toasts, monkeypatch, tmp_path):
    from modules.error_text import explain
    from ui.pages.cve_page import CvePage

    good = tmp_path / "cve.csv"
    asked = _save_dialog_answers(monkeypatch, tmp_path / "gone" / "cve.csv", good)
    host = _cve_host()

    CvePage._export_csv(host)

    (message, kind, _args, kwargs) = toasts[0]
    assert kind == "error"
    assert message.startswith("The CVE list could not be saved.")
    missing = FileNotFoundError(2, "", str(tmp_path / "gone" / "cve.csv"))
    assert explain(missing).why in message
    assert "cve.csv" not in message and "cve.csv" in kwargs["detail"]
    assert kwargs["action_label"] == "Choose another location"

    kwargs["action_callback"]()

    assert len(asked) == 2, "Choose another location did not reopen the save dialog"
    assert "CVE-2026-0001" in good.read_text(encoding="utf-8")
    assert [k for _m, k, _a, _kw in toasts] == ["error", "success"]


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="CreateFileW share modes are Windows-only")
def test_cve_export_over_a_file_open_in_another_program_names_that_cause(toasts, monkeypatch, tmp_path):
    """Measured (S6): the commonest export failure — the CSV is still open in Excel."""
    import ctypes
    import ctypes.wintypes as wintypes

    from ui.pages.cve_page import CvePage

    target = tmp_path / "cve.csv"
    target.write_text("old", encoding="utf-8")
    _save_dialog_answers(monkeypatch, target)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # RULE-WIN11
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.CreateFileW(str(target), 0xC0000000, 0x1, None, 3, 0, None)  # share-read only, like Excel
    try:
        CvePage._export_csv(_cve_host())
    finally:
        k32.CloseHandle(handle)

    (message, kind, _args, kwargs) = toasts[0]
    assert kind == "error" and "another program" in message
    assert "administrator" not in message.lower() and "rights" not in message.lower()
    assert kwargs["action_label"] == "Choose another location"


def test_a_bug_while_building_the_export_offers_no_new_location(toasts, monkeypatch, tmp_path):
    from ui.pages.cve_page import CvePage

    _save_dialog_answers(monkeypatch, tmp_path / "cve.csv")
    host = _cve_host(rows=[None])  # r.get(...) raises AttributeError inside the write loop

    CvePage._export_csv(host)

    (message, kind, _args, kwargs) = toasts[0]
    assert kind == "error" and message.startswith("The CVE list could not be saved.")
    assert kwargs["action_label"] == "" and "AttributeError" in kwargs["detail"]


def test_network_map_png_save_failure_is_no_longer_silent(toasts, monkeypatch, tmp_path):
    from ui.pages.network_map_page import NetworkMapPage

    asked = _save_dialog_answers(monkeypatch, tmp_path / "gone" / "map.png", tmp_path / "map.png")
    host = _keep(_Host())
    host._on_export_data = lambda url: NetworkMapPage._on_export_data(host, url)

    NetworkMapPage._on_export_data(host, "data:image/png;base64,iVBORw0KGgo=")

    (message, kind, _args, kwargs) = toasts[0]
    assert kind == "error" and message.startswith("The map image could not be saved.")
    kwargs["action_callback"]()
    assert len(asked) == 2 and (tmp_path / "map.png").exists(), "the retry did not keep the image"


# ── 6.2 — dialogs keep their channel, but read as what/why/next with the raw text behind Details ──

@pytest.fixture
def dialogs(monkeypatch):
    """Stand in for run_dialog inside show_error_dialog; optionally click a button by its text."""
    from ui import error_display

    seen: list = []
    click: dict = {"text": None}

    def _run(box):
        buttons = {b.text(): b for b in box.buttons()}
        seen.append({"text": box.text(), "informative": box.informativeText(),
                     "detail": box.detailedText(), "buttons": sorted(buttons)})
        if click["text"] is not None and click["text"] in buttons:
            click["text"], chosen = None, buttons[click["text"]]
            chosen.click()
        box.deleteLater()
        return 0

    monkeypatch.setattr(error_display, "run_dialog", _run)
    return seen, click


def _reports_host():
    from PyQt6.QtWidgets import QListWidget, QPushButton
    from ui.pages.reports_page import ReportsPage

    host = _keep(_Host())
    host._btn_pdf = QPushButton("Export PDF", host)
    host._report_list = QListWidget(host)
    host._sync_list_visibility = lambda: None
    host._export_pdf = lambda: ReportsPage._export_pdf(host)
    return host


def test_pdf_export_into_a_missing_folder_is_not_blamed_on_a_missing_engine(dialogs, monkeypatch, tmp_path):
    """Measured with Edge installed: this used to read "No PDF backend available — install Edge"."""
    from ui.pages.reports_page import ReportsPage

    seen, click = dialogs
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    asked = _save_dialog_answers(monkeypatch, tmp_path / "gone" / "report.pdf")
    click["text"] = "Choose another location"
    host = _reports_host()

    ReportsPage._export_pdf(host)

    first = seen[0]
    assert first["text"] == "The PDF report could not be saved."
    assert "folder does not exist" in first["informative"]
    assert "engine" not in first["informative"].lower() and "report.pdf" not in first["informative"]
    assert "FileNotFoundError" in first["detail"]
    assert "Choose another location" in first["buttons"]
    assert len(asked) == 2, "Choose another location did not reopen the save dialog"
    assert host._btn_pdf.isEnabled() and host._btn_pdf.text() == "Export PDF"


def test_pdf_with_no_engine_says_what_to_install(dialogs, monkeypatch, tmp_path):
    import modules.report_exporter
    from modules.report_pdf import NoPdfBackendError
    from ui.pages.reports_page import ReportsPage

    seen, _click = dialogs
    _save_dialog_answers(monkeypatch, tmp_path / "report.pdf")

    def _no_engine(path):
        raise NoPdfBackendError("Ingen PDF-motor")

    monkeypatch.setattr(modules.report_exporter, "save_pdf_report", _no_engine)

    ReportsPage._export_pdf(_reports_host())

    (box,) = seen
    assert box["text"] == "The PDF report could not be created."
    assert "Chrome" in box["informative"] and "PDF-motor" not in box["informative"]
    assert "Choose another location" not in box["buttons"]


def test_the_plugin_wizard_never_offers_another_location(dialogs, tmp_path):
    """The template goes to the fixed plugins folder: a permission failure must not suggest moving it."""
    from ui import worker_error_catalogue as WE
    from ui.error_display import show_error_dialog

    seen, _click = dialogs
    try:
        with open(tmp_path / "gone" / "plugin.py", "w", encoding="utf-8"):
            pass  # never reached: the open is what raises
    except OSError as exc:
        show_error_dialog(None, exc, WE.PLUGIN_TEMPLATE, retry=lambda: None)

    (box,) = seen
    assert box["informative"] == f"{WE.PLUGIN_TEMPLATE.why} {WE.PLUGIN_TEMPLATE.next_step}"
    assert "Choose another location" not in box["buttons"]


# ── 6.3a — the remaining worker-error slots show their catalogue text, never the raw string ──

RAW = ("[WinError 10060] Ett anslutningsförsök misslyckades eftersom den anslutna parten "
       "inte svarade på rätt sätt efter en viss tid")


class _AutoHost(QWidget):
    """A widget whose unset attributes are MagicMocks (buttons, timers, signals, workers); each
    case supplies the real QLabel the slot writes to. Only reached for names QWidget lacks."""

    def __getattr__(self, name):
        if not name.startswith("__"):
            from unittest.mock import MagicMock

            value = MagicMock(name=name)
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(name)


def _host_with(label_attr, *, set_status=None):
    from PyQt6.QtWidgets import QLabel

    host = _keep(_AutoHost())
    label = QLabel("idle", host)
    object.__setattr__(host, label_attr, label)
    if set_status is not None:
        object.__setattr__(host, "_set_status", lambda *a, **k: set_status(host, *a, **k))
    return host, label


def _slot_cases():
    from ui.pages.baseline_page import BaselinePage
    from ui.pages.diagnosis_page import DiagnosisPage
    from ui.pages.hardware_browse_mixin import _HardwareBrowseMixin
    from ui.pages.hardware_integration_page import HardwareIntegrationPage
    from ui.pages.network_doc_page import NetworkDocPage
    from ui.pages.network_map_page import NetworkMapPage
    from ui.pages.protocol_viz_page import ProtocolVizPage
    from ui.pages.service_diagnostics_page import ServiceDiagnosticsPage
    from ui.pages.speed_test_page import SpeedTestPage
    from ui.pages.threat_intel_page import ThreatIntelPage
    from ui.pages.trend_page import TrendPage
    from ui.pages.wifi_heatmap_page import WifiHeatmapPage
    from ui.pages.wifi_monitor_page import WiFiMonitorPage
    from ui.tabs_scan import _ScanTabsMixin

    return {
        "hardware_detect": (_HardwareBrowseMixin.on_hardware_detect_error, "_status_lbl", "HARDWARE_DETECT",
                            HardwareIntegrationPage._set_status),
        "community_index": (_HardwareBrowseMixin._on_community_index_error, "_browse_status", "COMMUNITY_INDEX", None),
        "community_download": (_HardwareBrowseMixin._on_community_download_error, "_browse_status",
                               "COMMUNITY_DOWNLOAD", None),
        "service_diagnostics": (ServiceDiagnosticsPage._on_error, "_status_lbl", "SERVICE_DIAGNOSTICS",
                                ServiceDiagnosticsPage._set_status),
        "speed_test": (SpeedTestPage._on_test_error, "_status_lbl", "SPEED_TEST", None),
        "wifi_heatmap_scan": (WifiHeatmapPage._on_scan_error, "_status_label", "WIFI_HEATMAP_SCAN",
                              WifiHeatmapPage._set_status),
        "wifi_monitor": (WiFiMonitorPage._on_error, "_status_lbl", "WIFI_MONITOR", WiFiMonitorPage._set_status),
        "network_doc": (NetworkDocPage._on_error, "_status_lbl", "NETWORK_DOC", None),
        "baseline_snapshot": (BaselinePage._on_scan_error, "_status_lbl", "BASELINE_SNAPSHOT", None),
        "isp_quick_test": (DiagnosisPage._on_isp_error, "_isp_detail_lbl", "ISP_QUICK_TEST", None),
        "traffic_overlay": (NetworkMapPage._on_bw_error, "_lldp_hint_label", "TRAFFIC_OVERLAY", None),
        "live_protocol": (ProtocolVizPage._on_live_error, "_canvas_subtitle", "LIVE_PROTOCOL", None),
        "threat_feed_refresh": (ThreatIntelPage._on_refresh_error, "_status_lbl", "THREAT_FEED_REFRESH", None),
        "trend_analysis": (TrendPage._on_error, "_status_lbl", "TREND_ANALYSIS", None),
        "dns_benchmark": (_ScanTabsMixin._on_dns_benchmark_error, "_dns_bench_status", "DNS_BENCHMARK", None),
    }


@pytest.mark.parametrize("case", [
    "hardware_detect", "community_index", "community_download", "service_diagnostics", "speed_test",
    "wifi_heatmap_scan", "wifi_monitor", "network_doc", "baseline_snapshot", "isp_quick_test",
    "traffic_overlay", "live_protocol", "threat_feed_refresh", "trend_analysis", "dns_benchmark",
])
def test_worker_error_slot_shows_what_why_next_and_keeps_the_raw_text(case, caplog):
    import logging

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    slot, label_attr, spec_name, set_status = _slot_cases()[case]
    spec = getattr(WE, spec_name)
    host, label = _host_with(label_attr, set_status=set_status)

    with caplog.at_level(logging.WARNING):
        slot(host, RAW)

    assert label.text() == worker_error_text(spec)
    assert "10060" not in label.text() and "anslutningsförsök" not in label.text()
    records = [r for r in caplog.records if r.name == f"netsentinel.worker_error.{spec.key}"]
    assert len(records) == 1 and RAW in records[0].getMessage(), "the raw text was lost or logged twice"


def test_prescan_error_puts_the_message_on_the_verdict_and_the_raw_text_in_the_log(caplog):
    import logging

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.plugin_page_mixin import _PluginPageMixin

    host = _keep(_AutoHost())
    statuses: list = []
    object.__setattr__(host, "_set_status", statuses.append)
    with caplog.at_level(logging.WARNING):
        _PluginPageMixin._on_prescan_error(host, RAW)

    host._verdict.update.assert_called_once_with(worker_error_text(WE.PRESCAN), "UNKNOWN")
    assert statuses == ["The pre-scan failed."]
    assert [r for r in caplog.records if r.name == "netsentinel.worker_error.prescan" and RAW in r.getMessage()]


def test_network_doc_error_log_pane_gets_the_message_not_the_raw_text():
    from PyQt6.QtWidgets import QPlainTextEdit
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.network_doc_page import NetworkDocPage

    host, _label = _host_with("_status_lbl")
    pane = QPlainTextEdit(host)
    object.__setattr__(host, "_log", pane)

    NetworkDocPage._on_error(host, RAW)

    assert worker_error_text(WE.NETWORK_DOC) in pane.toPlainText()
    assert "10060" not in pane.toPlainText()


def test_abuseipdb_error_keeps_the_local_verdict_and_appends_the_message(caplog):
    import logging

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.threat_intel_page import ThreatIntelPage

    host, label = _host_with("_lookup_result")
    label.setText("8.8.8.8: not in local feeds")
    with caplog.at_level(logging.WARNING):
        ThreatIntelPage._on_abuse_error(host, RAW)

    assert label.text() == f"8.8.8.8: not in local feeds | {worker_error_text(WE.ABUSEIPDB_LOOKUP)}"
    assert [r for r in caplog.records if r.name == "netsentinel.worker_error.abuseipdb_lookup"]

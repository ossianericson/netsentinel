"""S6b — labels, status lines and charts say what failed, why, and what next.

Behavioural counterparts (RULE-T7) to census (a) reaching zero. Where a site holds the exception, the
tests raise a *real* one — a SQLite write blocked by a real lock, a folder that does not exist, a file
that is not an image, a refused loopback connection — and never construct an ``Explanation`` by hand
(RULE-DBG5).
"""
from __future__ import annotations

import logging
import sqlite3
import sys
import threading
import time

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QLabel, QLineEdit, QListWidget, QPushButton, QWidget  # noqa: E402

from ui import styles as _s  # noqa: E402

RAW = ("[WinError 10060] Ett anslutningsförsök misslyckades eftersom den anslutna parten "
       "inte svarade på rätt sätt efter en viss tid")

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


class _AutoHost(QWidget):
    """A widget whose unset attributes are MagicMocks; each case supplies the real widgets it reads."""

    def __getattr__(self, name):
        if not name.startswith("__"):
            from unittest.mock import MagicMock

            value = MagicMock(name=name)
            object.__setattr__(self, name, value)
            return value
        raise AttributeError(name)


def _host(**attrs):
    host = _keep(_AutoHost())
    for name, value in attrs.items():
        object.__setattr__(host, name, value)
    return host


def _label(host):
    return QLabel("idle", host)


def _raiser(exc):
    def _raise(*_a, **_k):
        raise exc
    return _raise


def _records(caplog, spec):
    return [r for r in caplog.records if r.name == f"netsentinel.worker_error.{spec.key}"]


def _real_lock_error(tmp_path) -> sqlite3.OperationalError:
    """A write refused by a real exclusive transaction — sqlite_errorcode 5 (SQLITE_BUSY)."""
    path = str(tmp_path / "locked.db")
    holder = sqlite3.connect(path)
    other = sqlite3.connect(path, timeout=0)
    try:
        holder.execute("CREATE TABLE t (x)")
        holder.commit()
        holder.execute("BEGIN EXCLUSIVE")
        try:
            other.execute("INSERT INTO t VALUES (1)")
        except sqlite3.OperationalError as exc:
            return exc
        raise AssertionError("the exclusive transaction did not block a second writer")
    finally:
        holder.rollback()
        holder.close()
        other.close()


# ── File and database sites: the exception reaches explain(), opted in per site ─────────────────

def test_home_automation_save_under_a_real_lock_says_the_database_is_busy(monkeypatch, tmp_path, caplog):
    from modules.error_text import explain
    from ui import worker_error_catalogue as WE
    from ui.pages import home_automation_page as ha

    locked = _real_lock_error(tmp_path)
    host = _host(_store=object())
    label = _label(host)
    object.__setattr__(host, "_status_lbl", label)
    object.__setattr__(host, "_set_status", lambda text: ha.HomeAutomationPage._set_status(host, text))

    class _Dialog:
        def __init__(self, *_a, **_k):
            pass

        def values(self):
            return {"room": "Kitchen"}

    monkeypatch.setattr(ha, "_DeviceEditDialog", _Dialog)
    monkeypatch.setattr(ha, "run_dialog", lambda dlg: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(ha, "update_device_ha_info", _raiser(locked))
    device = {"mac": "aa:bb:cc:dd:ee:ff"}

    with caplog.at_level(logging.WARNING):
        ha.HomeAutomationPage._open_edit_dialog(host, device)

    assert explain(locked).kind == "database_busy"
    assert label.text().startswith("⚠ The device was not saved.")
    assert explain(locked).why in label.text()
    assert "locked" not in label.text(), "the raw sqlite text reached the label"
    assert "room" not in device, "a failed save updated the local cache"
    assert _records(caplog, WE.HA_SAVE)


def test_home_automation_load_failure_shows_the_fixed_text(tmp_path):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.home_automation_page import HomeAutomationPage

    try:
        sqlite3.connect(":memory:").execute("SELECT * FROM known_device")
    except sqlite3.OperationalError as exc:
        missing_table = exc

    class _Store:
        def query_ha_devices(self):
            raise missing_table

    host = _host(_store=_Store())
    label = _label(host)
    object.__setattr__(host, "_status_lbl", label)
    object.__setattr__(host, "_set_status", lambda text: HomeAutomationPage._set_status(host, text))

    HomeAutomationPage._load_devices(host)

    assert label.text() == worker_error_text(WE.HA_LOAD)
    assert host._devices == []


def test_home_automation_status_label_wraps_the_longer_explained_text(tmp_path):
    from modules.metric_store import MetricStore
    from ui.pages.home_automation_page import HomeAutomationPage

    store = MetricStore(db_path=tmp_path / "ha.db")
    try:
        page = _keep(HomeAutomationPage(store=store))
        assert page._status_lbl.wordWrap(), "a 220-character explained message would widen the page"
    finally:
        store.close()


def _save_dialog_answers(monkeypatch, *paths, method="getSaveFileName"):
    from PyQt6.QtWidgets import QFileDialog

    queue = [str(p) for p in paths]
    monkeypatch.setattr(QFileDialog, method, staticmethod(lambda *a, **k: (queue.pop(0), "") if queue else ("", "")))


def _heatmap_host():
    from ui.pages.wifi_heatmap_page import WifiHeatmapPage

    host = _host()
    label = _label(host)
    object.__setattr__(host, "_status_label", label)
    object.__setattr__(host, "_set_status", lambda *a, **k: WifiHeatmapPage._set_status(host, *a, **k))
    return host, label


def test_heatmap_png_export_into_a_missing_folder_explains_the_location(monkeypatch, tmp_path, caplog):
    from matplotlib.figure import Figure

    from modules.error_text import explain
    from ui import worker_error_catalogue as WE
    from ui.pages.wifi_heatmap_page import WifiHeatmapPage

    target = tmp_path / "gone" / "heatmap.png"
    _save_dialog_answers(monkeypatch, target)
    host, label = _heatmap_host()
    object.__setattr__(host, "_fig", Figure())

    with caplog.at_level(logging.WARNING):
        WifiHeatmapPage._on_export_png(host)

    missing = FileNotFoundError(2, "", str(target))
    assert label.text().startswith("⚠ The heatmap image could not be saved.")
    assert explain(missing).why in label.text()
    assert "heatmap.png" not in label.text() and "Exported" not in label.text()
    assert "FileNotFoundError" in _records(caplog, WE.EXPORT_HEATMAP_IMAGE)[0].getMessage()


def test_heatmap_floor_plan_that_is_not_an_image_says_so(monkeypatch, tmp_path):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.wifi_heatmap_page import WifiHeatmapPage

    fake = tmp_path / "plan.png"
    fake.write_text("this is not a PNG", encoding="utf-8")
    _save_dialog_answers(monkeypatch, fake, method="getOpenFileName")
    host, label = _heatmap_host()
    object.__setattr__(host, "_floor_plan_img", None)

    WifiHeatmapPage._on_import_floor_plan(host)

    assert label.text() == worker_error_text(WE.HEATMAP_FLOOR_PLAN)
    assert host._floor_plan_img is None


def test_heatmap_status_label_wraps_the_longer_explained_text():
    from ui.pages.wifi_heatmap_page import WifiHeatmapPage

    page = _keep(WifiHeatmapPage())
    assert page._status_label.wordWrap(), "a 220-character explained message would widen the page"


def _status_host(**attrs):
    statuses: list = []
    host = _host(_set_status=statuses.append, **attrs)
    return host, statuses


def test_export_report_into_a_missing_folder_explains_it_on_the_status_bar(monkeypatch, tmp_path, caplog):
    import modules.report_exporter
    from modules.error_text import explain
    from ui import worker_error_catalogue as WE
    from ui.export_mixin import _ExportMixin

    target = tmp_path / "gone" / "report.html"
    _save_dialog_answers(monkeypatch, target)
    monkeypatch.setattr(modules.report_exporter, "save_report", lambda out, **kw: out.write_text("x"))
    host, statuses = _status_host()

    with caplog.at_level(logging.WARNING):
        _ExportMixin._export_report(host)

    missing = FileNotFoundError(2, "", str(target))
    assert statuses == [
        f"⚠ The report could not be saved. {explain(missing).why} {explain(missing).next_step}"
    ], "a failed export also reported success, or showed the raw path"
    assert _records(caplog, WE.EXPORT_REPORT)


def test_auto_report_never_tells_the_user_to_pick_a_location_it_chose(monkeypatch, tmp_path):
    """The auto-report goes to NetSentinel's own reports folder: only disk_full may replace its text."""
    import modules.report_exporter
    import modules.utils
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.export_mixin import _ExportMixin

    monkeypatch.setattr(modules.utils, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(modules.report_exporter, "save_report",
                        lambda out, **kw: (tmp_path / "gone" / "r.html").write_text("x"))
    host, statuses = _status_host(_auto_report_pending=True, _auto_report_scan_done=True,
                                  _auto_report_diag_done=True)

    _ExportMixin._maybe_auto_report(host)

    assert statuses == [worker_error_text(WE.AUTO_REPORT)]


# ── Sites that can only fail by a bug: fixed text, raw text in the detail and the log ──────────

def _bug_cases():
    from ui.scan_enrichment import ScanEnrichmentMixin
    from ui.scan_wiring import ScanResultMixin
    from ui.tabs_analysis import _AnalysisTabsMixin
    from ui.tabs_recon import _ReconTabsMixin

    return {
        "risk_score": ("modules.risk_scorer", "score_devices", "_risk_status", "RISK_SCORE",
                       lambda h: _ReconTabsMixin._run_risk_scorer(h), {"_m1_result": {"devices": []}}),
        "root_cause": ("modules.root_cause_correlator", "correlate", "_corr_status", "ROOT_CAUSE",
                       lambda h: _AnalysisTabsMixin._run_correlator(h), {}),
        "network_grade": ("modules.network_benchmark", "grade", "_bm_verdict_label", "NETWORK_GRADE",
                          lambda h: _AnalysisTabsMixin._run_benchmark(h), {}),
        "log_chart": ("modules.log_chart", "build_figure", "_log_status_lbl", "LOG_CHART",
                      lambda h: _AnalysisTabsMixin._view_log_chart(h),
                      {"_log_chart_summary": object(), "_chart_window": None}),
        "device_filter": ("modules.nl_query", "query", "_m1_status", "DEVICE_FILTER",
                          lambda h: ScanEnrichmentMixin._filter_m1_by_nl(h, "cameras"),
                          {"_m1_result": {"devices": []}}),
        "baseline_check": ("modules.utils", "load_device_baseline", "_bl_new_lbl", "BASELINE_CHECK",
                           lambda h: ScanResultMixin._m1_check_baseline_diff(h, {"devices": []}), {}),
    }


@pytest.mark.parametrize("case", ["risk_score", "root_cause", "network_grade", "log_chart",
                                  "device_filter", "baseline_check"])
def test_a_bug_behind_a_label_shows_the_fixed_text_and_logs_the_raw_one(case, monkeypatch, caplog):
    import importlib

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    module_name, func, label_attr, spec_name, run, attrs = _bug_cases()[case]
    spec = getattr(WE, spec_name)
    monkeypatch.setattr(importlib.import_module(module_name), func, _raiser(RuntimeError(RAW)))
    host = _host(**attrs)
    label = _label(host)
    object.__setattr__(host, label_attr, label)

    with caplog.at_level(logging.WARNING):
        run(host)

    assert label.text() == worker_error_text(spec)
    assert "10060" not in label.text()
    (record,) = _records(caplog, spec)
    assert RAW in record.getMessage() and record.exc_info, "the traceback did not reach the app log"


@pytest.mark.parametrize("method, spec_name", [("_run_iot_learn", "IOT_LEARN"), ("_run_iot_monitor", "IOT_MONITOR")])
def test_iot_start_failure_shows_the_fixed_text(method, spec_name, monkeypatch):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.tabs_analysis import _AnalysisTabsMixin

    monkeypatch.setitem(sys.modules, "modules.iot_baseline", None)  # the import in the try raises
    host = _host(_m1_result={"devices": []})
    label = _label(host)
    object.__setattr__(host, "_iot_status", label)

    getattr(_AnalysisTabsMixin, method)(host)

    assert label.text() == worker_error_text(getattr(WE, spec_name))


def test_scan_startup_failure_puts_the_message_on_the_verdict_and_what_on_the_status_bar(caplog):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.plugin_page_mixin import _PluginPageMixin

    host, statuses = _status_host(_launch_modules_impl=_raiser(RuntimeError(RAW)))

    with caplog.at_level(logging.WARNING):
        _PluginPageMixin._launch_modules(host)

    assert statuses == ["The scan could not start."]
    host._verdict.update.assert_called_once_with(worker_error_text(WE.SCAN_STARTUP), "HIGH")
    assert _records(caplog, WE.SCAN_STARTUP)


# ── IP Calculator: the user's input, not a fault ─────────────────────────────────────────────

def test_ip_calculator_invalid_input_gives_an_example_and_keeps_the_reason_as_a_tooltip(caplog):
    from ui.pages.ip_calculator_page import IpCalculatorPage

    page = _keep(IpCalculatorPage())
    page._ip_input.setText("10.0.0.300/24")

    with caplog.at_level(logging.WARNING):
        page._calculate()

    text = page._error_lbl.text()
    assert not page._error_lbl.isHidden()
    assert "192.168.1.10/24" in text, "no example of valid input"
    assert "300" not in text and "Octet" not in text, "the stdlib ValueError text reached the label"
    assert "300" in page._error_lbl.toolTip()
    assert not [r for r in caplog.records if r.name.startswith("netsentinel")], "a typo is not an app fault"

    page._ip_input.setText("10.0.0.1/24")
    page._calculate()
    assert page._error_lbl.isHidden() and page._error_lbl.toolTip() == ""


# ── Charts, list items and appended verdicts (the census-blind sinks) ─────────────────────────

def test_app_traffic_error_draws_the_message_on_the_chart(caplog):
    from matplotlib.figure import Figure

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.app_traffic_page import AppTrafficPage

    host = _host(_ax=Figure().add_subplot(111))
    label = _label(host)
    object.__setattr__(host, "_status_lbl", label)

    with caplog.at_level(logging.WARNING):
        AppTrafficPage._on_error(host, RAW)

    (text,) = host._ax.texts
    assert text.get_text() == worker_error_text(WE.APP_TRAFFIC) and text.get_wrap()
    # Derived, not re-pinned: the claim here is that the non-wrapping control-row label
    # carries only `what` while the chart carries the whole message. The wording itself
    # is held by test_worker_error_catalogue.py (S9.4 corrected it).
    assert label.text() == f"{_s.STATUS_ICON_WARN} {WE.APP_TRAFFIC.what}."
    assert RAW in _records(caplog, WE.APP_TRAFFIC)[0].getMessage()


def test_live_bandwidth_poller_error_titles_the_chart_and_redraws(caplog):
    from matplotlib.figure import Figure

    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.live_bandwidth_page import LiveBandwidthPage

    host = _host(_ax=Figure().add_subplot(111))

    with caplog.at_level(logging.WARNING):
        LiveBandwidthPage._on_poller_error(host, RAW)

    assert host._ax.get_title() == worker_error_text(WE.LIVE_BANDWIDTH)
    assert host._ax.title.get_wrap()
    host._canvas.draw_idle.assert_called()
    assert _records(caplog, WE.LIVE_BANDWIDTH)


def test_speed_test_server_list_error_item_keeps_the_raw_text_as_its_tooltip(caplog):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.speed_test_page import SpeedTestPage

    host = _host()
    servers = QListWidget(host)
    object.__setattr__(host, "_server_list", servers)
    object.__setattr__(host, "_server_hint", _label(host))

    with caplog.at_level(logging.WARNING):
        SpeedTestPage._on_fetch_error(host, RAW)

    item = servers.item(0)
    assert item.text() == worker_error_text(WE.SPEED_SERVER_LIST)
    assert "10060" in item.toolTip()
    assert _records(caplog, WE.SPEED_SERVER_LIST)


def test_abuseipdb_could_not_test_keeps_the_local_verdict_and_appends_the_message(caplog):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text
    from ui.pages.threat_intel_page import ThreatIntelPage

    host = _host()
    label = _label(host)
    label.setText("8.8.8.8: not in local feeds")
    object.__setattr__(host, "_lookup_result", label)

    with caplog.at_level(logging.WARNING):
        ThreatIntelPage._on_abuse_not_testable(host, RAW)

    assert label.text() == f"8.8.8.8: not in local feeds | {worker_error_text(WE.ABUSEIPDB_NOT_TESTABLE)}"
    assert _records(caplog, WE.ABUSEIPDB_NOT_TESTABLE)


# ── Plugin errors: protocol text is the plugin author's; only the unmatched fallback is raw ────

@pytest.mark.parametrize("message, expected", [
    ("AUTH: wrong password", "Authentication failed — wrong password"),
    ("ERR: Plugin is missing get_info() or get_status().", "Plugin is missing get_info() or get_status()."),
    ("NET: no route", "Cannot reach the device — no route"),
    ("connection refused by peer", "Cannot reach the device — check the IP address and that the device is online."),
    (RAW, None),
    ("", None),
])
def test_plugin_error_text_classifies_only_what_it_recognises(message, expected):
    from ui.widgets.hub_helpers import _classify_error, plugin_error_text

    assert plugin_error_text(message) == expected
    assert _classify_error(message) == (message if expected is None else expected), "_classify_error changed"


def test_hub_card_unrecognised_plugin_error_shows_the_fixed_text(make_card):
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    card = make_card(_FRESH_HEALTH)
    card.set_error("", raw=RAW)

    assert card._metrics_lbl.text() == worker_error_text(WE.PLUGIN_ERROR)
    card.set_error("Cannot reach the device — no route")
    assert "no route" in card._metrics_lbl.text(), "protocol text must still show as written"


@pytest.mark.parametrize("message, call", [
    (RAW, (("",), {"raw": RAW})),
    ("AUTH: bad password", (("Authentication failed — bad password",), {})),
])
def test_page_passes_only_unrecognised_plugin_errors_as_raw(message, call, monkeypatch):
    from unittest.mock import MagicMock

    import ui.pages.hardware_integration_page as hw

    monkeypatch.setattr(hw, "_record_error", lambda *_a: {})
    card = MagicMock()
    host = _host(_cards={"modem-1": card})

    hw.HardwareIntegrationPage._on_plugin_error(host, "modem-1", message)

    args, kwargs = call
    card.set_error.assert_called_once_with(*args, **kwargs)


class _FakeTester(QObject):
    success = pyqtSignal(dict)
    failure = pyqtSignal(str)
    message = ""

    def __init__(self, *_a, **_k):
        super().__init__()

    def start(self):
        self.failure.emit(type(self).message)

    def isRunning(self):  # noqa: N802 - QThread's name, read by the dialog's cleanup
        return False

    def wait(self, *_a):
        return True


@pytest.mark.parametrize("message, expected", [
    (RAW, None),
    # S9.1: the glyph is derived, never spelled out. This case pinned "✗" while the
    # RAW case above went through show_worker_error's "⚠" -- so the test held the
    # inconsistency in place as the contract.
    ("AUTH: bad password", f"{_s.STATUS_ICON_WARN}  Authentication failed — bad password"),
])
def test_credential_dialog_failure_translates_or_explains(message, expected, monkeypatch):
    import keyring

    import ui.widgets.credential_dialog as cd
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    _FakeTester.message = message
    monkeypatch.setattr(cd, "_PluginConnectionTester", _FakeTester)
    monkeypatch.setattr(keyring, "delete_password", lambda *_a: None)
    shown: list = []

    def _drive(dlg):
        ip_edit, pw_edit = dlg.findChildren(QLineEdit)[:2]
        ip_edit.setText("192.168.1.1")
        pw_edit.setText("secret")
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Test & Add").click()
        for _ in range(5):
            QApplication.instance().processEvents()
        shown.extend(lbl.text() for lbl in dlg.findChildren(QLabel) if lbl.wordWrap() and lbl.text()[:1] in "⚠✗")
        dlg.deleteLater()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(cd, "run_dialog", _drive)
    parent = _keep(QWidget())

    cd.show_credential_dialog(parent, "Modem", "192.168.1.1", "Password")

    assert shown == [expected if expected is not None else worker_error_text(WE.PLUGIN_CONNECTION_TEST)]


@pytest.mark.parametrize("body, expected", [
    ("def get_info():\n    raise RuntimeError('boom 10060')\n\ndef get_status():\n    return {}\n", "boom 10060"),
    ("def get_info():\n    raise RuntimeError('AUTH: wrong password')\n\ndef get_status():\n    return {}\n",
     "AUTH: wrong password"),
    ("x = 1\n", "ERR: Plugin is missing get_info() or get_status()."),
])
def test_connection_tester_emits_the_plugin_text_for_the_dialog_to_classify(body, expected, monkeypatch, tmp_path):
    import keyring

    from ui.widgets.hub_card import _PluginConnectionTester

    monkeypatch.setattr(keyring, "set_password", lambda *_a: None)
    plugin = tmp_path / "boom_plugin.py"
    plugin.write_text(body, encoding="utf-8")
    tester = _PluginConnectionTester(str(plugin), "192.168.1.1", "pw")
    _widgets.append(tester)
    failures: list = []
    tester.failure.connect(failures.append)

    tester.run()  # synchronously, on this thread

    assert failures == [expected]


# ── 6.3c: the update check runs off the GUI thread ─────────────────────────────────────────

def _update_host():
    from ui.tabs_help import _HelpTabsMixin

    class _Host(QWidget, _HelpTabsMixin):
        def __init__(self):
            super().__init__()
            self._update_lbl = QLabel("", self)
            self.available: list = []

        def _on_update_available(self, latest):
            self.available.append(latest)

    return _keep(_Host())


def _pump_until(predicate, timeout_s=10.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_s
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return predicate()


def _join_update_worker(host):
    worker = getattr(host, "_update_check_worker", None)
    try:
        if worker is not None:
            worker.wait(5000)
    except RuntimeError:
        pass  # already deleted via finished -> deleteLater
    for _ in range(3):
        QApplication.instance().processEvents()


def test_update_check_does_not_block_the_gui_thread_and_explains_a_failure(monkeypatch, caplog):
    import urllib.request

    import modules.utils
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    monkeypatch.setattr(modules.utils, "is_store_app", lambda: False)
    real_urlopen = urllib.request.urlopen
    release = threading.Event()
    calls: list = []

    def _blocking_refused(*_a, **_k):
        calls.append(True)
        release.wait(10)
        return real_urlopen("http://127.0.0.1:9/", timeout=5)  # a real refused connection

    monkeypatch.setattr(urllib.request, "urlopen", _blocking_refused)
    host = _update_host()

    try:
        with caplog.at_level(logging.WARNING):
            host._check_for_updates()
            host._check_for_updates()  # a second click while the first is still running
            assert host._update_lbl.text() == "Checking…", "the click blocked until the request finished"
            release.set()
            assert _pump_until(lambda: host._update_lbl.text() != "Checking…")
    finally:
        release.set()
        _join_update_worker(host)

    text = host._update_lbl.text()
    assert text == worker_error_text(WE.UPDATE_CHECK)
    assert "port" not in text.lower() and "host name" not in text.lower()
    assert len(calls) == 1, "a second click started a second request"
    assert _records(caplog, WE.UPDATE_CHECK)


def test_update_check_success_still_offers_the_update(monkeypatch):
    import io
    import urllib.request

    import modules.utils

    monkeypatch.setattr(modules.utils, "is_store_app", lambda: False)

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *_a, **_k: _Response(b'{"tag_name": "v99.0.0"}'))
    host = _update_host()
    try:
        host._check_for_updates()
        assert _pump_until(lambda: host._update_lbl.text() != "Checking…")
    finally:
        _join_update_worker(host)

    assert "Update available: v99.0.0" in host._update_lbl.text()
    assert host.available == ["99.0.0"]


_FRESH_HEALTH = {
    "success": 0, "errors": 0, "consecutive": 0,
    "last_ok": 0.0, "last_err": "", "disabled": False,
}


@pytest.fixture
def make_card():
    """A real HubCard with its health store patched (RULE-WIN6), deleted with RULE-WIN4 cleanup."""
    from unittest.mock import patch

    created = []

    def _factory(health):
        with patch("ui.widgets.hub_card._load_health", return_value=dict(health)):
            from ui.widgets.hub_card import HubCard
            card = HubCard("/fake/plugin.py", {"name": "Test", "type": "other", "ip": "192.168.1.1"}, None)
        created.append(card)
        return card

    yield _factory
    for card in created:
        try:
            card._tick_timer.stop()
        except (AttributeError, RuntimeError):
            pass  # no timer, or already deleted
        _widgets.append(card)

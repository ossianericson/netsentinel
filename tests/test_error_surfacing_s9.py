"""S9 / S10 — consistency, and the surfaces a headless run leaves behind.

Behavioural counterparts to the S9 triage
(``docs/internal/error-surfacing-audit-2026-09-15.md`` §6 S9/S10). Every case drives the
real production function and asserts on what a person would actually read — a tile's own
label, the glyph a dialog writes, which of the two channels a site chose, the line that
lands in the Windows Event Log.

  * 9.1a — ``monitor_overview_page``: the storm tile wrote the internal risk vocabulary
    (``Storm``/``Warn``/``Clean``) while the Broadcast Storm page rendered
    ``risk_to_label()`` for the very same level. F8 flagged "Warn".
  * 9.1b — ``credential_dialog``: the same connection failure carried ``✗`` when the
    plugin's text was recognised and ``⚠`` when it was not.
  * 9.2  — three ``QMessageBox.information`` sites that decide nothing: a PDF export that
    succeeded, an export with no rows, and a refusal to export from the wrong tab. The
    log export was the sharper half — the *non-event* was the loudest thing in the method
    and the write that actually happened said nothing at all (RULE-SURF2).
  * 9.4  — ``WE.APP_TRAFFIC``: ``AppTrafficClassifier.run()`` has exactly two error paths
    and both are capability gaps, but the entry described a different failure and ended in
    "Start monitoring again", which cannot fix a missing driver.
  * 10.1a — ``svc``/``cli``/``app``: four headless sinks handed the user a raw exception.
    The census could not see any of them — it knows Qt widget writes, and the Windows
    Event Log and ``print(file=sys.stderr)`` are neither.
"""
from __future__ import annotations

import io
import sys
import threading
from contextlib import redirect_stderr
from pathlib import Path

import pytest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from ui import styles as _s

_widgets: list = []

#: Unrecognised plugin failure text, localized by Windows exactly as a user gets it.
#: ``plugin_error_text`` returns None for it, so the dialog falls through to
#: ``show_worker_error`` — the other of the two branches 9.1b compares.
UNCLASSIFIED_PLUGIN_ERROR = (
    "[WinError 10060] Ett anslutningsforsok misslyckades eftersom den anslutna parten "
    "inte svarade korrekt efter en viss tidsperiod"
)


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


@pytest.fixture()
def toasts(monkeypatch):
    """Every toast a path raises, as (message, kind)."""
    from ui.widgets.toast import ToastManager

    shown: list = []
    monkeypatch.setattr(
        ToastManager, "show",
        classmethod(lambda _cls, message, kind="info", *_a, **_kw: shown.append((message, kind))),
    )
    return shown


@pytest.fixture()
def modals(monkeypatch):
    """Every modal a path raises, as (which, title)."""
    raised: list = []

    for which in ("information", "warning"):
        monkeypatch.setattr(
            QMessageBox, which,
            staticmethod(
                lambda *args, _w=which, **_kw: (
                    raised.append((_w, args[1] if len(args) > 1 else "")),
                    QMessageBox.StandardButton.Ok,
                )[1]
            ),
        )
    return raised


# ── 9.1a: the storm tile speaks the user's vocabulary, not the scanner's ─────

#: The internal scan risk levels. None of these may reach a user as a label
#: (architecture reference, "Risk levels — two separate systems"; RULE-A3).
INTERNAL_RISK_WORDS = {"STORM", "WARN", "WARNING", "CLEAN", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}


@pytest.fixture()
def overview_page():
    from ui.pages.monitor_overview_page import MonitorOverviewPage

    return _keep(MonitorOverviewPage())


@pytest.mark.parametrize("level", ["STORM", "WARNING", "CLEAN"])
def test_9_1a_storm_tile_never_shows_an_internal_risk_word(overview_page, level):
    overview_page.set_storm_status(level)

    headline = overview_page._tile_storm._value_lbl.text()

    assert headline.upper() not in INTERNAL_RISK_WORDS, (
        f"{level} draws {headline!r} — the internal risk vocabulary, verbatim"
    )


@pytest.mark.parametrize("level", ["STORM", "WARNING", "CLEAN"])
def test_9_1a_storm_tile_agrees_with_the_broadcast_storm_page(overview_page, level):
    """The two surfaces describe one measurement; they must use one translator."""
    from ui.tabs_helpers import risk_to_label

    overview_page.set_storm_status(level)

    assert overview_page._tile_storm._sub_lbl.text() == risk_to_label(level)


def test_9_1a_storm_tile_still_distinguishes_the_three_levels(overview_page):
    """Consistency must not cost the tile its job: three levels, three headlines."""
    headlines = []
    for level in ("STORM", "WARNING", "CLEAN"):
        overview_page.set_storm_status(level)
        headlines.append(overview_page._tile_storm._value_lbl.text())

    assert len(set(headlines)) == 3, headlines


# ── 9.1b: one failure, one glyph ─────────────────────────────────────────────

class _FakeTester:
    """Stands in for the real ``_PluginConnectionTester``, failing on demand."""

    message = ""

    def __init__(self, *_a, **_kw):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Signals(QObject):
            success = pyqtSignal(dict)
            failure = pyqtSignal(str)

        self._sig = _Signals()
        self.success = self._sig.success
        self.failure = self._sig.failure

    def start(self):
        self.failure.emit(type(self).message)

    def isRunning(self):  # noqa: N802 - QThread's name, read by the dialog's cleanup
        return False

    def wait(self, *_a):
        return True


def _dialog_status_for(message, monkeypatch) -> str:
    """Drive the real credential dialog to a failure and return the status it writes."""
    import keyring

    import ui.widgets.credential_dialog as cd

    _FakeTester.message = message
    monkeypatch.setattr(cd, "_PluginConnectionTester", _FakeTester)
    monkeypatch.setattr(keyring, "delete_password", lambda *_a: None)
    written: list = []

    def _drive(dlg):
        ip_edit, pw_edit = dlg.findChildren(QLineEdit)[:2]
        ip_edit.setText("192.168.1.1")
        pw_edit.setText("secret")
        next(b for b in dlg.findChildren(QPushButton) if b.text() == "Test & Add").click()
        for _ in range(5):
            QApplication.instance().processEvents()
        written.extend(
            lbl.text().strip() for lbl in dlg.findChildren(QLabel)
            if lbl.wordWrap() and lbl.text().strip()
            and not lbl.text().strip()[0].isalnum()
        )
        dlg.deleteLater()
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(cd, "run_dialog", _drive)
    cd.show_credential_dialog(_keep(QWidget()), "Modem", "192.168.1.1", "Password")
    assert written, "the dialog wrote no glyph-prefixed status at all"
    return written[-1]


def test_9_1b_a_recognised_and_an_unrecognised_failure_carry_the_same_glyph(monkeypatch):
    recognised = _dialog_status_for("AUTH: bad password", monkeypatch)
    unrecognised = _dialog_status_for(UNCLASSIFIED_PLUGIN_ERROR, monkeypatch)

    assert recognised[0] == unrecognised[0], (
        f"same failure, two glyphs: {recognised[0]!r} vs {unrecognised[0]!r}"
    )


def test_9_1b_that_shared_glyph_is_the_one_every_other_failure_uses(monkeypatch):
    """``show_worker_error`` sets the app-wide convention; the dialog must not invent one."""
    assert _dialog_status_for("AUTH: bad password", monkeypatch)[0] == _s.STATUS_ICON_WARN


# ── 9.2: modal only where there is a decision ────────────────────────────────

def test_9_2a_a_successful_pdf_export_confirms_with_a_toast(tmp_path, monkeypatch,
                                                            toasts, modals):
    from PyQt6.QtWidgets import QFileDialog

    import modules.report_exporter as report_exporter
    from ui.pages.reports_page import ReportsPage

    target = tmp_path / "report.pdf"
    host = _keep(QWidget())
    host._btn_pdf = QPushButton("Export PDF", host)
    host._report_list = QListWidget(host)
    host._sync_list_visibility = lambda: None
    host._export_pdf = lambda: None
    monkeypatch.setattr(report_exporter, "save_pdf_report",
                        lambda p: Path(p).write_bytes(b"%PDF-1.4"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *_a, **_k: (str(target), "")))

    ReportsPage._export_pdf(host)

    assert target.exists()
    assert modals == [], f"a successful export stopped the user with {modals}"
    assert [kind for _m, kind in toasts] == ["success"]
    assert target.name in toasts[0][0]


def test_9_2a_a_broken_confirmation_cannot_report_a_finished_export_as_failed(
        tmp_path, monkeypatch):
    """RULE-SURF1's inverse corollary — the S6.0 defect, one moved line away from returning.

    A confirmation written inside the ``try`` that guards the work is guarded by the same
    handler, so a confirmation that raises turns a finished export into a failure dialog.
    """
    from PyQt6.QtWidgets import QFileDialog

    import modules.report_exporter as report_exporter
    from ui.pages import reports_page
    from ui.widgets.toast import ToastManager

    target = tmp_path / "report.pdf"
    host = _keep(QWidget())
    host._btn_pdf = QPushButton("Export PDF", host)
    host._report_list = QListWidget(host)
    host._sync_list_visibility = lambda: None
    host._export_pdf = lambda: None
    failures: list = []

    def _explode(_cls, *_a, **_kw):
        raise AttributeError("show_toast")

    monkeypatch.setattr(ToastManager, "show", classmethod(_explode))
    monkeypatch.setattr(report_exporter, "save_pdf_report",
                        lambda p: Path(p).write_bytes(b"%PDF-1.4"))
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *_a, **_k: (str(target), "")))
    monkeypatch.setattr(reports_page, "show_error_dialog",
                        lambda *a, **k: failures.append(a))

    raised: list = []
    try:
        reports_page.ReportsPage._export_pdf(host)
    except AttributeError as exc:
        raised.append(exc)

    assert target.exists()
    # Assert the defect first: inside the try, the AttributeError is swallowed into a
    # failure dialog, so a bare pytest.raises would fail on the wrong line and say so.
    assert failures == [], f"a finished export was reported as a failure: {failures}"
    assert raised, "the confirmation's own error must surface, not vanish"


def _log_panel_host(tmp_path) -> QWidget:
    host = _keep(QWidget())
    host._search_box = QLineEdit(host)
    host._is_source_enabled = lambda _k: True
    host._entry_matches = lambda _e, _f: True
    host._table = QTableWidget(0, 3, host)
    host._table.setHorizontalHeaderLabels(["Time", "Source", "Event"])
    host._export_visible = lambda: None
    host._entries = []
    return host


def test_9_2b_an_export_with_no_matching_rows_is_a_toast_not_a_modal(tmp_path, toasts, modals):
    from ui.pages.log_source_panel import _LogSourcePanelMixin

    host = _log_panel_host(tmp_path)

    _LogSourcePanelMixin._export_visible(host)

    assert modals == [], f"a non-event stopped the user with {modals}"
    assert len(toasts) == 1 and toasts[0][1] == "info", toasts


def test_9_2b_an_export_that_wrote_a_file_says_so(tmp_path, monkeypatch, toasts, modals):
    """The half that was silent: RULE-SURF2 puts the loudness on the event, not the non-event."""
    from PyQt6.QtWidgets import QFileDialog

    from ui.pages.log_source_panel import _LogSourcePanelMixin

    target = tmp_path / "filtered.csv"
    host = _log_panel_host(tmp_path)
    host._entries = [{"source_key": "rtt", "row": ("12:00", "RTT", "ok")}]
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *_a, **_k: (str(target), "")))

    _LogSourcePanelMixin._export_visible(host)

    assert target.exists()
    assert [kind for _m, kind in toasts] == ["success"], toasts
    assert target.name in toasts[0][0]


def test_9_2b_a_failed_export_still_uses_its_dialog(tmp_path, monkeypatch, toasts):
    """S6 decision 2 holds: this site's failure channel does not change."""
    from PyQt6.QtWidgets import QFileDialog

    from ui.pages import log_source_panel as panel

    shown: list = []
    monkeypatch.setattr(panel, "show_error_dialog",
                        lambda *a, **k: shown.append(a[2] if len(a) > 2 else None))
    host = _log_panel_host(tmp_path)
    host._entries = [{"source_key": "rtt", "row": ("12:00", "RTT", "ok")}]
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *_a, **_k: (str(tmp_path / "gone" / "x.csv"), "")))

    panel._LogSourcePanelMixin._export_visible(host)

    assert len(shown) == 1
    assert [kind for _m, kind in toasts] == []


def test_9_2c_the_map_export_refusal_is_a_toast_that_names_the_next_step(toasts, modals):
    from ui.pages.network_map_page import NetworkMapPage

    host = _keep(QWidget())
    host._web_available = True
    host._inner_tab = QTabWidget(host)
    host._inner_tab.addTab(QWidget(host), "Interactive")
    host._inner_tab.addTab(QWidget(host), "Static")
    host._inner_tab.setCurrentIndex(1)
    host._run_js = lambda _js: None

    NetworkMapPage._on_export(host)

    assert modals == []
    assert len(toasts) == 1 and toasts[0][1] == "warning", toasts
    assert "Interactive" in toasts[0][0]


def test_9_2c_the_map_export_still_runs_on_the_interactive_tab(toasts, modals):
    """The refusal's sibling: a real export must not have become a toast too."""
    from ui.pages.network_map_page import NetworkMapPage

    ran: list = []
    host = _keep(QWidget())
    host._web_available = True
    host._inner_tab = QTabWidget(host)
    host._inner_tab.addTab(QWidget(host), "Interactive")
    host._inner_tab.setCurrentIndex(0)
    host._run_js = ran.append

    NetworkMapPage._on_export(host)

    assert ran and "exportPng" in ran[0]
    assert toasts == [] and modals == []


# ── 9.4: the capability gap the entry never mentioned ────────────────────────

def test_9_4_app_traffic_names_the_capability_its_producer_actually_needs():
    from ui import worker_error_catalogue as WE
    from ui.error_display import worker_error_text

    message = worker_error_text(WE.APP_TRAFFIC).lower()

    assert "npcap" in message and "administrator" in message, message


def test_9_4_app_traffic_no_longer_tells_a_driverless_user_to_just_retry():
    from ui import worker_error_catalogue as WE

    assert WE.APP_TRAFFIC.next_step != "Start monitoring again."


def test_9_4_the_page_draws_that_text_for_the_real_producer_message():
    """RULE-T7 — the real slot, fed the string ``AppTrafficClassifier`` really emits."""
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure

    from ui.pages.app_traffic_page import AppTrafficPage

    figure = Figure()
    host = _keep(QWidget())
    host._ax = figure.add_subplot(111)
    host._canvas = FigureCanvasQTAgg(figure)
    host._stop_worker = lambda: None
    host._status_lbl = QLabel(host)

    AppTrafficPage._on_error(
        host,
        "Failed to start packet capture. Run as Administrator/root with Npcap installed.",
    )

    drawn = host._ax.texts[-1].get_text().lower()
    assert "npcap" in drawn and "administrator" in drawn, drawn


# ── 10.1a: the four headless sinks ───────────────────────────────────────────

def _event_log_line(exc, monkeypatch, tmp_path) -> str:
    """Drive the real ``SvcDoRun`` to its error path and return what it wrote."""
    import win32event

    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    import svc

    written: list = []

    class _EventLog:
        EVENTLOG_INFORMATION_TYPE = 4
        EVENTLOG_WARNING_TYPE = 2
        PYS_SERVICE_STARTED = 1
        PYS_SERVICE_STOPPED = 2

        def LogMsg(self, *args):  # noqa: N802 - servicemanager's own name
            written.append(("LogMsg", args))

        def LogErrorMsg(self, text):  # noqa: N802
            written.append(("LogErrorMsg", text))

        def LogWarningMsg(self, text):  # noqa: N802
            written.append(("LogWarningMsg", text))

    def _raise(stop_event):
        raise exc

    monkeypatch.setattr(svc, "servicemanager", _EventLog())
    monkeypatch.setattr(svc, "_run_logger", _raise)
    service = object.__new__(svc._NetSentinelLoggerService)
    service._win32_stop = win32event.CreateEvent(None, 0, 0, None)
    service._thread_stop = threading.Event()

    service.SvcDoRun()
    win32event.SetEvent(service._win32_stop)

    errors = [text for kind, text in written if kind == "LogErrorMsg"]
    assert errors, f"nothing reached the Event Log: {written}"
    return errors[0]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows service / Event Log")
def test_10_1a_the_event_log_carries_a_next_step_not_the_raw_exception(monkeypatch, tmp_path):
    from modules.error_text import explain

    exc = PermissionError(13, "Access is denied")

    line = _event_log_line(exc, monkeypatch, tmp_path)

    assert explain(exc).next_step in line, line
    assert "Access is denied" not in line, "the raw text belongs in the app log, not the entry"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows service / Event Log")
def test_10_1a_the_event_log_still_names_the_service_and_that_it_failed(monkeypatch, tmp_path):
    line = _event_log_line(PermissionError(13, "Access is denied"), monkeypatch, tmp_path)

    assert "NetSentinel" in line


@pytest.mark.skipif(sys.platform != "win32", reason="Windows service / Event Log")
def test_10_1a_the_raw_exception_goes_to_the_app_log_with_its_traceback(monkeypatch, tmp_path,
                                                                        caplog):
    import logging

    caplog.set_level(logging.WARNING)

    _event_log_line(PermissionError(13, "Access is denied"), monkeypatch, tmp_path)

    records = [r for r in caplog.records if r.exc_info]
    assert records, "no traceback was recorded anywhere"
    assert "Access is denied" in records[-1].exc_text or "Access is denied" in str(
        records[-1].exc_info[1]
    )


def test_10_1a_cli_output_directory_failure_explains_itself(tmp_path):
    import cli
    from modules.error_text import explain

    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    # Ask the OS what it really raises here rather than guessing: Windows answers
    # FileExistsError(WinError 183), POSIX NotADirectoryError, and the two classify
    # differently. The expectation is derived, never hard-coded to one platform.
    try:
        (blocker / "sub").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        expected_next_step = explain(exc).next_step
    else:
        pytest.skip("this platform allows a directory beneath a file")
    buf = io.StringIO()

    with pytest.raises(SystemExit) as exit_info, redirect_stderr(buf):
        cli._resolve_output(str(blocker / "sub" / "out.json"))

    text = buf.getvalue()
    assert exit_info.value.code == 1
    assert expected_next_step in text, text
    assert str(blocker) in text, "the user still needs to know which directory"
    assert "WinError" not in text and "Errno" not in text, text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows service control manager")
def test_10_1a_svc_status_failure_explains_itself(monkeypatch):
    import win32serviceutil

    import svc

    def _refuse(_name):
        raise OSError(1060, "The specified service does not exist as an installed service.")

    monkeypatch.setattr(win32serviceutil, "QueryServiceStatus", staticmethod(_refuse))
    buf = io.StringIO()

    with pytest.raises(SystemExit), redirect_stderr(buf):
        svc._cmd_status()

    text = buf.getvalue()
    assert "does not exist as an installed service" not in text, text
    assert "netsentinel-svc install" in text.lower() or "install" in text.lower()


def test_10_1a_headless_report_failure_leads_with_an_explanation(monkeypatch, tmp_path):
    import app as app_mod
    import modules.utils as utils

    def _no_adapter():
        raise RuntimeError("no usable network adapter")

    monkeypatch.setattr(utils, "get_local_ip", _no_adapter)
    monkeypatch.setattr(sys, "argv", ["app.py", "--report", "--no-flush-caches",
                                      "--output", str(tmp_path / "r.html")])
    buf = io.StringIO()

    with pytest.raises(SystemExit), redirect_stderr(buf):
        app_mod._headless()

    first = next(ln for ln in buf.getvalue().splitlines() if ln.strip())
    assert "no usable network adapter" not in first, first
    assert "Traceback" in buf.getvalue(), "the traceback is the diagnostic; keep it"


# ── the census can now see this class of sink ────────────────────────────────

def test_10_1a_the_census_counts_headless_sinks_in_entry_points():
    from tools.check_error_surfacing import find_raw_exception_ui_sinks

    sources = {
        "svc.py": (
            "def f(servicemanager):\n"
            "    try:\n        g()\n"
            "    except Exception as exc:\n"
            "        servicemanager.LogErrorMsg(f'boom: {exc}')\n"
        ),
        "cli.py": (
            "import sys\n"
            "def f():\n"
            "    try:\n        g()\n"
            "    except OSError as exc:\n"
            "        print(f'boom: {exc}', file=sys.stderr)\n"
        ),
    }

    hits = find_raw_exception_ui_sinks(sources)

    assert sorted(h.path for h in hits) == ["cli.py", "svc.py"]


def test_10_1a_a_print_outside_an_entry_point_is_a_developers_not_a_users():
    """Scoped like ``_UI_ONLY_SINK_ATTRS`` (owner decision S6.4): area, not shape."""
    from tools.check_error_surfacing import find_raw_exception_ui_sinks

    sources = {
        "modules/thing.py": (
            "def f():\n"
            "    try:\n        g()\n"
            "    except Exception as exc:\n        print(f'boom: {exc}')\n"
        ),
    }

    assert find_raw_exception_ui_sinks(sources) == []

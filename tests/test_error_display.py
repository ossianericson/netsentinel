"""S5.1 — ``ui/error_display.py::show_worker_error``: what, why and next on the label; raw text one hover away.

RULE-A2 / D5. A worker's ``error`` signal carries only a ``str``, often OS-localized, so the
message comes from a fixed per-site catalogue entry and the raw text becomes *detail*: a
tooltip and a Copy action while the label still shows the message, and one app-log record.

The raw sample below is a real sv-SE Windows bind failure — the shape S0.2 observed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt  # noqa: E402
from PyQt6.QtGui import QContextMenuEvent, QHelpEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

RAW = ("[WinError 10048] Endast en användning av varje socketadress "
       "(protokoll/nätverksadress/port) är normalt tillåten")


@dataclass(frozen=True)
class _Spec:
    key: str = "test_site"
    what: str = "The test scan failed"
    why: str = "The test probe hit an error."
    next_step: str = "Run it again."


SPEC = _Spec()
_labels: list = []


@pytest.fixture(autouse=True)
def _cleanup_labels(qt_app):
    """RULE-WIN4: deleteLater() + pump."""
    yield
    for lbl in _labels:
        try:
            lbl.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed
    _labels.clear()
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _label(text: str = "idle") -> QLabel:
    lbl = QLabel(text)
    _labels.append(lbl)
    return lbl


def _tooltip_event() -> QHelpEvent:
    return QHelpEvent(QEvent.Type.ToolTip, QPoint(2, 2), QPoint(2, 2))


def _context_event() -> QContextMenuEvent:
    return QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(2, 2), QPoint(2, 2))


@pytest.fixture
def shown_tooltips(monkeypatch):
    """Capture QToolTip.showText instead of drawing a real tooltip window."""
    from ui import error_display

    shown: list = []

    class _FakeToolTip:
        @staticmethod
        def showText(pos, text, widget=None):  # noqa: N802 - Qt's name
            shown.append(text)

    monkeypatch.setattr(error_display, "QToolTip", _FakeToolTip)
    return shown


@pytest.fixture
def menu_actions(monkeypatch):
    """Replace the blocking menu.exec() with one that records and triggers nothing."""
    from ui import error_display

    opened: list = []

    def _record(menu, pos):
        opened.append(menu.actions())

    monkeypatch.setattr(error_display, "_exec_menu", _record)
    return opened


def test_label_shows_what_why_and_next_never_the_raw_text():
    from ui.error_display import show_worker_error, worker_error_text

    lbl = _label()
    show_worker_error(lbl, RAW, SPEC)

    assert lbl.text() == worker_error_text(SPEC)
    assert SPEC.what in lbl.text() and SPEC.why in lbl.text() and SPEC.next_step in lbl.text()
    assert "10048" not in lbl.text() and "socketadress" not in lbl.text()


def test_raw_text_is_the_tooltip_while_the_message_is_shown(shown_tooltips):
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, RAW, SPEC)

    handled = QApplication.sendEvent(lbl, _tooltip_event())

    assert handled is True
    assert len(shown_tooltips) == 1 and "socketadress" in shown_tooltips[0]


def test_raw_tooltip_is_html_escaped(shown_tooltips):
    """RULE-UX7: routed through safe_tooltip, so a raw '<' cannot become markup."""
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, "bad <b>token</b>", SPEC)
    QApplication.sendEvent(lbl, _tooltip_event())

    assert "<b>token</b>" not in shown_tooltips[0]
    assert "&lt;b&gt;" in shown_tooltips[0]


def test_detail_goes_away_once_another_writer_replaces_the_message(shown_tooltips):
    """The next status write ends the error: no stale raw tooltip on a 'Scanning…' label."""
    from ui.error_display import show_worker_error

    lbl = _label()
    lbl.setToolTip("the label's own tooltip")
    show_worker_error(lbl, RAW, SPEC)
    lbl.setText("Scanning ports…")

    QApplication.sendEvent(lbl, _tooltip_event())

    assert shown_tooltips == [], "a replaced message still served its raw tooltip"


def test_copy_error_details_copies_what_and_raw(menu_actions):
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, RAW, SPEC)

    handled = QApplication.sendEvent(lbl, _context_event())

    assert handled is True and len(menu_actions) == 1
    (copy,) = menu_actions[0]
    assert copy.text() == "Copy error details"
    QApplication.clipboard().setText("")
    copy.trigger()
    assert QApplication.clipboard().text() == f"{SPEC.what}\n{RAW}"


def test_no_menu_once_the_message_is_replaced(menu_actions):
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, RAW, SPEC)
    lbl.setText("SMB enumeration idle.")

    QApplication.sendEvent(lbl, _context_event())

    assert menu_actions == []


def test_repeated_errors_reuse_one_detail_filter():
    """One filter per label however often it fails — nothing accumulates (RULE-WIN8)."""
    from ui.error_display import show_worker_error

    lbl = _label()
    for i in range(5):
        show_worker_error(lbl, f"{RAW} #{i}", SPEC)

    children = lbl.findChildren(QObject, options=Qt.FindChildOption.FindDirectChildrenOnly)
    assert len(children) == 1


def test_the_newest_raw_text_wins(shown_tooltips):
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, "first cause", SPEC)
    show_worker_error(lbl, "second cause", SPEC)
    QApplication.sendEvent(lbl, _tooltip_event())

    assert "second cause" in shown_tooltips[0] and "first cause" not in shown_tooltips[0]


def test_each_shown_error_is_logged_once_under_its_own_key(caplog):
    """D4 record. A per-site logger, because the S2.3 limiter keys on logger + template."""
    from ui.error_display import show_worker_error

    lbl = _label()
    with caplog.at_level(logging.WARNING):
        show_worker_error(lbl, RAW, SPEC)

    records = [r for r in caplog.records if r.name.startswith("netsentinel.worker_error")]
    assert len(records) == 1
    assert records[0].name == "netsentinel.worker_error.test_site"
    assert records[0].levelno == logging.WARNING
    assert RAW in records[0].getMessage()


def test_an_app_health_condition_spec_is_accepted():
    """The syslog and SNMP pages reuse the strip's wording (one source of truth)."""
    from modules.app_health_catalogue import SNMP_TRAP_RECEIVER
    from ui.error_display import show_worker_error

    lbl = _label()
    show_worker_error(lbl, RAW, SNMP_TRAP_RECEIVER)

    assert SNMP_TRAP_RECEIVER.what in lbl.text()
    assert "10048" not in lbl.text()


# ── S6 — an exception in hand: explain() may supply why/next, but only where the site opts in ──
#
# RULE-DBG5: every exception below is raised by the real operating system (a folder that does not
# exist); no test builds an Explanation by hand, so these prove the helper populates it.

@dataclass(frozen=True)
class _FileSpec:
    key: str = "test_export"
    what: str = "The test file could not be saved"
    why: str = "Writing the test file failed."
    next_step: str = "Try again."
    explains: frozenset = frozenset({"path_not_found", "permission_denied", "disk_full", "invalid_path"})


FILE_SPEC = _FileSpec()


def _real_missing_folder_error(tmp_path) -> OSError:
    try:
        open(tmp_path / "gone" / "export.csv", "w", encoding="utf-8")
    except OSError as exc:
        return exc
    raise AssertionError("the folder unexpectedly exists")


def test_an_exception_voices_its_explanation_when_the_spec_lists_its_kind(tmp_path):
    from modules.error_text import explain
    from ui.error_display import show_worker_error

    exc = _real_missing_folder_error(tmp_path)
    lbl = _label()
    show_worker_error(lbl, exc, FILE_SPEC)

    assert FILE_SPEC.what in lbl.text()
    assert explain(exc).why in lbl.text() and FILE_SPEC.why not in lbl.text()
    assert "export.csv" not in lbl.text(), "the raw path reached the message"


def test_an_exception_whose_kind_the_spec_does_not_list_keeps_the_fixed_text(tmp_path):
    """explain() is context-free: a site that did not opt in never borrows its wording."""
    from modules.error_text import explain
    from ui.error_display import show_worker_error, worker_error_text

    exc = _real_missing_folder_error(tmp_path)
    lbl = _label()
    show_worker_error(lbl, exc, SPEC)

    assert lbl.text() == worker_error_text(SPEC)
    assert explain(exc).why not in lbl.text()


def test_a_string_raw_is_never_explained_even_when_the_spec_opts_in():
    from ui.error_display import show_worker_error, worker_error_text

    lbl = _label()
    show_worker_error(lbl, "[Errno 2] Filen eller katalogen finns inte", FILE_SPEC)

    assert lbl.text() == worker_error_text(FILE_SPEC)


def test_an_exception_detail_names_its_type_and_the_log_keeps_the_traceback(tmp_path, caplog, shown_tooltips):
    from ui.error_display import show_worker_error

    exc = _real_missing_folder_error(tmp_path)
    lbl = _label()
    with caplog.at_level(logging.WARNING):
        show_worker_error(lbl, exc, FILE_SPEC)
    QApplication.sendEvent(lbl, _tooltip_event())

    assert shown_tooltips and "FileNotFoundError" in shown_tooltips[0]
    (record,) = [r for r in caplog.records if r.name == "netsentinel.worker_error.test_export"]
    assert record.exc_info is not None and record.exc_info[1] is exc


# ── export_failed: an error toast whose next step is a button ─────────────────────

@pytest.fixture
def toasts(monkeypatch):
    from ui.widgets.toast import ToastManager

    shown: list = []

    def _record(cls, message, kind="info", action_label="", action_callback=None, detail=""):
        shown.append({"message": message, "kind": kind, "action_label": action_label,
                      "action_callback": action_callback, "detail": detail})

    monkeypatch.setattr(ToastManager, "show", classmethod(_record))
    return shown


def test_export_failed_offers_another_location_for_a_location_failure(tmp_path, toasts, caplog):
    from modules.error_text import explain
    from ui.error_display import export_failed

    exc = _real_missing_folder_error(tmp_path)
    retried: list = []
    with caplog.at_level(logging.WARNING):
        export_failed(exc, FILE_SPEC, retry=lambda: retried.append(True))

    (toast,) = toasts
    assert toast["kind"] == "error"
    assert toast["message"].startswith(FILE_SPEC.what) and explain(exc).why in toast["message"]
    assert "export.csv" not in toast["message"] and "export.csv" in toast["detail"]
    assert toast["action_label"] == "Choose another location"
    toast["action_callback"]()
    assert retried == [True]
    assert [r for r in caplog.records if r.name == "netsentinel.worker_error.test_export"]


def test_export_failed_offers_no_new_location_for_a_bug(toasts):
    """A bug building the CSV is not fixed by picking a folder — no button, the fixed text."""
    from ui.error_display import export_failed

    export_failed(KeyError("mac"), FILE_SPEC, retry=lambda: None)

    (toast,) = toasts
    assert toast["action_label"] == "" and toast["action_callback"] is None
    assert FILE_SPEC.why in toast["message"]
    assert "KeyError" in toast["detail"]


# ── show_error_dialog: plain text, raw text behind Show Details ────────────────────

@pytest.fixture
def dialogs(monkeypatch):
    """Stand in for the blocking run_dialog: record the box, optionally click a button by text."""
    from ui import error_display

    seen: list = []
    click: dict = {"text": None}

    def _run(box):
        buttons = {b.text(): b for b in box.buttons()}
        seen.append({"title": box.windowTitle(), "text": box.text(),
                     "informative": box.informativeText(), "detail": box.detailedText(),
                     "buttons": sorted(buttons)})
        if click["text"] is not None:
            buttons[click["text"]].click()
        box.deleteLater()
        return 0

    monkeypatch.setattr(error_display, "run_dialog", _run)
    return seen, click


def test_error_dialog_puts_the_raw_text_behind_details(tmp_path, dialogs):
    from modules.error_text import explain
    from ui.error_display import show_error_dialog

    seen, _click = dialogs
    exc = _real_missing_folder_error(tmp_path)
    parent = _label()
    show_error_dialog(parent, exc, FILE_SPEC)

    (box,) = seen
    assert box["text"].startswith(FILE_SPEC.what)
    assert explain(exc).why in box["informative"]
    assert "export.csv" not in box["text"] + box["informative"]
    assert "FileNotFoundError" in box["detail"] and "export.csv" in box["detail"]
    assert "Choose another location" not in box["buttons"], "no retry was offered by the caller"


def test_error_dialog_retry_runs_after_the_dialog_closes(tmp_path, dialogs):
    from ui.error_display import show_error_dialog

    seen, click = dialogs
    click["text"] = "Choose another location"
    retried: list = []
    show_error_dialog(_label(), _real_missing_folder_error(tmp_path), FILE_SPEC,
                      retry=lambda: retried.append(len(seen)))

    assert retried == [1], "the retry did not run once, after the dialog"


def test_error_dialog_offers_no_retry_for_a_bug(dialogs):
    from ui.error_display import show_error_dialog

    seen, _click = dialogs
    show_error_dialog(_label(), KeyError("mac"), FILE_SPEC, retry=lambda: None)

    assert "Choose another location" not in seen[0]["buttons"]

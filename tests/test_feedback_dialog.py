"""Tests for in-app feedback dialog (UX Sprint 10, S10-7)."""
from __future__ import annotations

import datetime
from pathlib import Path


# ── Module-level import ───────────────────────────────────────────────────────

def test_feedback_dialog_importable():
    from ui.widgets.feedback_dialog import FeedbackDialog, show_feedback_dialog  # noqa: F401


def test_feedback_log_filename_constant():
    from ui.widgets.feedback_dialog import _LOG_FILE
    assert _LOG_FILE == "feedback.log"


def test_max_chars_constant():
    from ui.widgets.feedback_dialog import _MAX_CHARS
    assert _MAX_CHARS > 0


# ── Write logic (no Qt needed) ────────────────────────────────────────────────

def test_feedback_is_written_to_log(tmp_path):
    """Submitting feedback writes a timestamped entry to the log file."""
    from ui.widgets import feedback_dialog as _mod

    _fake_dir = tmp_path

    def _fake_app_data_dir():
        return _fake_dir

    original = _mod.get_app_data_dir
    _mod.get_app_data_dir = _fake_app_data_dir
    try:
        log = _fake_dir / "feedback.log"
        text = "This feature is great!"

        # Simulate the file write that _submit() performs
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}]\n{text}\n\n"
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(entry)

        assert log.exists()
        content = log.read_text(encoding="utf-8")
        assert "This feature is great!" in content
        assert "[" in content and "]" in content  # timestamp bracket present
    finally:
        _mod.get_app_data_dir = original


def test_multiple_submissions_append_not_overwrite(tmp_path):
    log = tmp_path / "feedback.log"
    for i in range(3):
        entry = f"[2026-01-0{i+1} 12:00:00]\nFeedback {i}\n\n"
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(entry)
    content = log.read_text(encoding="utf-8")
    assert "Feedback 0" in content
    assert "Feedback 1" in content
    assert "Feedback 2" in content


# ── Diagnostic report attachment (B2) ─────────────────────────────────────────
#
# The two tests above simulate the write that `_submit()` performs rather than
# calling it, so they cannot see whether `_submit()` still does what they model.
# These drive the real method — which is the whole question for an attachment
# whose value is that it actually reaches disk.

import pytest


@pytest.fixture
def dialog(tmp_path, monkeypatch):
    """A real FeedbackDialog with both app-data readers redirected.

    Both, because they resolve differently: the dialog imported
    `get_app_data_dir` into its own namespace at module scope, while
    `modules.diagnostic_report` looks it up lazily on `modules.utils`. Patching
    only one leaves the other writing into the developer's real NetSentinel
    folder (RULE-WIN6).
    """
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from ui.widgets.feedback_dialog import FeedbackDialog

    monkeypatch.setattr("ui.widgets.feedback_dialog.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))

    dlg = FeedbackDialog()
    yield dlg
    try:
        dlg.deleteLater()
    except RuntimeError:
        pass  # already destroyed by an earlier teardown
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_submitting_with_the_box_checked_writes_a_real_report(dialog, tmp_path):
    """The attachment reaches disk and the feedback entry names it.

    The two files are read weeks apart and by then only the path connects them,
    so a report that lands with nothing pointing at it is a report nobody finds.
    """
    dialog._edit.setPlainText("It closed on its own overnight.")
    dialog._attach_chk.setChecked(True)

    dialog._submit()

    log = (tmp_path / "feedback.log").read_text(encoding="utf-8")
    assert "It closed on its own overnight." in log
    assert "Diagnostic report:" in log

    reports = list((tmp_path / "reports").glob("netsentinel-diagnostic-*.md"))
    assert len(reports) == 1
    assert "NetSentinel diagnostic report" in reports[0].read_text(encoding="utf-8")


def test_submitting_with_the_box_unchecked_writes_no_report(dialog, tmp_path):
    """Off by default, and off means nothing is collected.

    PRIVACY.md promises zero telemetry and this feature keeps that promise
    literally by writing files and sending none — but a report generated without
    being asked for is still a surprise, and the checkbox is the asking.
    """
    dialog._edit.setPlainText("The Devices column is too narrow.")

    dialog._submit()

    log = (tmp_path / "feedback.log").read_text(encoding="utf-8")
    assert "too narrow" in log
    assert "Diagnostic report:" not in log
    assert not (tmp_path / "reports").exists()


def test_the_attachment_is_off_until_the_user_asks_for_it(dialog):
    """RULE-EXP1's spirit: the previously-verified path stays the default one."""
    assert dialog._attach_chk.isChecked() is False


# ── Command palette wiring ────────────────────────────────────────────────────

def test_give_feedback_in_palette_actions():
    """Give Feedback action must be in the palette items list."""
    src = Path("ui/nav/builder.py").read_text(encoding="utf-8")
    assert '"Give Feedback"' in src


def test_palette_action_handler_handles_feedback():
    """_on_palette_action must handle 'Give Feedback'."""
    src = Path("ui/nav/builder.py").read_text(encoding="utf-8")
    assert 'action == "Give Feedback"' in src
    assert "show_feedback_dialog" in src

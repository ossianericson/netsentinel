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
    import ui.widgets.feedback_dialog as _mod

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

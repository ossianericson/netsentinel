"""In-app feedback dialog (UX Sprint 10, S10-7) and the B2 diagnostic-report host.

Opens a simple modal where the user can type a note about the app.
Feedback is written to a local log file only — no network calls, no telemetry.

File location: get_app_data_dir() / "feedback.log"
Format: timestamped plain-text entries, one per submission.

The "attach a diagnostic report" checkbox lives here rather than in a dialog of
its own because this dialog is already the right host: already local-only,
already reachable from Ctrl+K, and already the place a user goes to say something
is wrong. A second dialog would be a second thing to find. The report itself is
built by `modules/diagnostic_report.py`, which redacts before it writes; nothing
here decides what is safe to include.
"""
from __future__ import annotations

import datetime

from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit,
    QVBoxLayout,
)

from modules.diagnostic_report import REDACTION_NOTE
from modules.utils import get_app_data_dir
from ui import styles as _s
from ui.dialog_utils import run_dialog

_LOG_FILE = "feedback.log"
_MAX_CHARS = 2000


def write_diagnostic_report() -> str | None:
    """Build and save a diagnostic report. Returns its path, or None on failure.

    Runs on the GUI thread deliberately: it reads a bounded tail of four logs
    (~64 KB total) plus a handful of cached locale probes, so it sits far below
    RULE-UX2's 500 ms threshold, and a worker would add a thread to a modal the
    user is about to close.

    Shared by both surfaces that offer a report so the two cannot drift — the
    checkbox in this dialog and the "Create diagnostic report" button on the
    unclean-exit strip produce the identical file.
    """
    from PyQt6.QtWidgets import QApplication

    from modules.diagnostic_report import write_report

    app = QApplication.instance()
    version = app.applicationVersion() if app is not None else ""
    try:
        return write_report(app_version=version)
    except Exception:
        return None  # RULE-A2: callers report this in plain English, never as a traceback


class FeedbackDialog(QDialog):
    """Modal feedback entry dialog — writes to feedback.log, no external calls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Give Feedback")
        self.setModal(True)
        self.setMinimumWidth(460)
        _s.themed_ss(self, "QDialog {{ background:{BG_CARD}; }}"
            "QLabel  {{ color:{TEXT_PRIMARY}; background:transparent; }}")
        self._build()

    def _build(self) -> None:
        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(20, 16, 20, 16)
        vlay.setSpacing(10)

        title = QLabel("Share feedback about NetSentinel")
        _s.themed_ss(title, "font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};")
        vlay.addWidget(title)

        hint = QLabel(
            "Your feedback is saved locally to <tt>feedback.log</tt> in your NetSentinel data folder. "
            "Nothing is sent over the network."
        )
        hint.setWordWrap(True)
        _s.themed_ss(hint, "font-size:11px; color:{TEXT_SECONDARY};")
        vlay.addWidget(hint)

        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText("What's working well? What could be better?")
        self._edit.setMinimumHeight(120)
        self._edit.setMaximumHeight(200)
        _s.themed_ss(self._edit, "QPlainTextEdit {{"
            "  background:{BG_CARD}; color:{TEXT_PRIMARY};"
            "  border:1px solid {BORDER_MED}; border-radius:4px;"
            "  padding:6px; font-size:12px;"
            "}}"
            "QPlainTextEdit:focus {{ border-color:{ACCENT}; }}")
        self._edit.textChanged.connect(self._on_text_changed)
        vlay.addWidget(self._edit)

        self._char_lbl = QLabel(f"0 / {_MAX_CHARS}")
        _s.themed_ss(self._char_lbl, "font-size:10px; color:{TEXT_SECONDARY};")
        vlay.addWidget(self._char_lbl)

        self._attach_chk = QCheckBox("Attach a diagnostic report")
        self._attach_chk.setToolTip(_s.safe_tooltip(
            "Saves a separate file next to your reports containing this PC's "
            "locale and encoding settings, any sessions that ended unexpectedly, "
            "and the tail of the app's own error logs.\n\n"
            "IP addresses, MAC addresses, Wi-Fi names, your device names and your "
            "Windows username are removed before the file is written. Nothing is "
            "sent anywhere."
        ))
        vlay.addWidget(self._attach_chk)

        attach_hint = QLabel(
            "Saved locally and redacted. Attach this if the app crashed, froze, "
            "or closed on its own."
        )
        attach_hint.setWordWrap(True)
        _s.themed_ss(attach_hint, "font-size:10px; color:{TEXT_SECONDARY};")
        vlay.addWidget(attach_hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = btns.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Submit")
        ok_btn.setEnabled(False)
        _s.themed_ss(ok_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:4px; padding:5px 16px; font-weight:bold; }}"
            "QPushButton:hover   {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            "QPushButton:disabled {{ background:{BORDER}; color:{TEXT_SECONDARY}; }}")
        cancel_btn = btns.button(QDialogButtonBox.StandardButton.Cancel)
        _s.themed_ss(cancel_btn, "QPushButton {{ background:{BG_CARD}; color:{ACCENT};"
            " border:1px solid {ACCENT}; border-radius:4px; padding:5px 16px; }}"
            "QPushButton:hover   {{ background:{BG_CARD}; color:{ACCENT_LITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT}; color:{WHITE}; }}")
        self._ok_btn = ok_btn
        btns.accepted.connect(self._submit)
        btns.rejected.connect(self.reject)
        vlay.addWidget(btns)

    def _on_text_changed(self) -> None:
        text = self._edit.toPlainText()
        n = len(text)
        self._char_lbl.setText(f"{n} / {_MAX_CHARS}")
        if n > _MAX_CHARS:
            # Truncate silently rather than blocking the user
            cursor = self._edit.textCursor()
            self._edit.setPlainText(text[:_MAX_CHARS])
            self._edit.setTextCursor(cursor)
        self._ok_btn.setEnabled(n > 0)

    def _submit(self) -> None:
        text = self._edit.toPlainText().strip()
        if not text:
            return

        report_path = write_diagnostic_report() if self._attach_chk.isChecked() else None

        try:
            log_path = get_app_data_dir() / _LOG_FILE
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"[{ts}]\n{text}\n"
            if report_path:
                # Named in the feedback entry so the note and the report can still
                # be matched up later; the two files are read weeks apart.
                entry += f"Diagnostic report: {report_path}\n"
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(entry + "\n")
        except Exception:
            pass  # non-fatal — feedback is best-effort

        if self._attach_chk.isChecked():
            if report_path:
                QMessageBox.information(
                    self,
                    "Diagnostic report saved",
                    "Your feedback was saved, along with a diagnostic report at:\n\n"
                    f"{report_path}\n\n" + REDACTION_NOTE,
                )
            else:
                QMessageBox.warning(
                    self,
                    "Diagnostic report not saved",
                    "Your feedback was saved, but the diagnostic report could not "
                    "be written — the NetSentinel data folder may be full or "
                    "read-only. Your feedback itself is unaffected.",
                )
        self.accept()


def show_feedback_dialog(parent=None) -> None:
    """Open the feedback dialog. Call from command palette action handler."""
    dlg = FeedbackDialog(parent)
    run_dialog(dlg)

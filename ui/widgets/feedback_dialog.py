"""In-app feedback dialog (UX Sprint 10, S10-7).

Opens a simple modal where the user can type a note about the app.
Feedback is written to a local log file only — no network calls, no telemetry.

File location: get_app_data_dir() / "feedback.log"
Format: timestamped plain-text entries, one per submission.
"""
from __future__ import annotations

import datetime

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout,
)

from modules.utils import get_app_data_dir
from ui import styles as _s
from ui.dialog_utils import run_dialog

_LOG_FILE = "feedback.log"
_MAX_CHARS = 2000


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
        try:
            log_path = get_app_data_dir() / _LOG_FILE
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = f"[{ts}]\n{text}\n\n"
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(entry)
        except Exception:
            pass  # non-fatal — feedback is best-effort
        self.accept()


def show_feedback_dialog(parent=None) -> None:
    """Open the feedback dialog. Call from command palette action handler."""
    dlg = FeedbackDialog(parent)
    run_dialog(dlg)

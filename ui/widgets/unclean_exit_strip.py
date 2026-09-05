"""UncleanExitStrip — "NetSentinel closed unexpectedly last time" (B1).

The piece that makes A1-A3 worth having. Those write session records, an
environment fingerprint and four crash sinks into `%LOCALAPPDATA%`, and until
now nothing in the app ever mentioned that any of it existed — the only
"open folder" affordance anywhere in the UI is the reports folder. A user whose
app was killed for memory saw exactly what they saw before: nothing.

This is one dismissible strip on Home with one button. Never modal, never
blocking: the app has already recovered by the time it appears, and a modal on
launch would punish the user for a crash that is not their fault.

Modelled on `ui/widgets/environment_banner.py` — same 28px collapsed row, same
`ui/context_banners.py` dismissal store, same dismiss-icon wiring. What differs
is the **dismissal key**, which is derived from the specific session that died
rather than being a single flag: dismissing the strip must silence *this* crash,
not the next one. See `_dismiss_key()`.
"""

from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ui import styles as _s
from ui.context_banners import mark_banner_seen, should_show_banner
from ui.widgets.device_detail_pane import _wire_close_icon


def _dismiss_key(record: dict) -> str:
    """A dismissal key that identifies one death, not "unclean exits" in general.

    Keyed on the record's start time, so dismissing today's crash does not
    pre-dismiss next week's. A record whose `started_at` is missing — the file
    was truncated by the very kill this exists to catch — falls back to a shared
    key rather than being un-dismissable, which would leave a strip the user
    cannot get rid of.
    """
    started = record.get("started_at")
    if isinstance(started, (int, float)):
        return f"unclean_exit_{int(started)}"
    return "unclean_exit_unknown"


def _describe(record: dict) -> str:
    """One plain-English line: when it happened, and where the user was.

    `last_page` is the only thing that will ever say *where* they were when the
    OS took the process (RULE-A1: plain English first). It is absent when the
    session died before the first navigation, and the sentence has to still read
    correctly when it is.
    """
    started = record.get("started_at")
    when = "last time"
    if isinstance(started, (int, float)):
        stamp = datetime.datetime.fromtimestamp(started)
        when = "today" if stamp.date() == datetime.date.today() else stamp.strftime("%d %b")
        when = f"{when} at {stamp.strftime('%H:%M')}"

    page = str(record.get("last_page") or "").strip()
    where = f", while you were on {page}" if page else ""
    return f"NetSentinel closed unexpectedly {when}{where}."


class UncleanExitStrip(QFrame):
    """Dismissible strip offering a diagnostic report. Starts hidden.

    Usage mirrors EnvironmentBanner: add it to the layout unconditionally, then
    call `set_sessions()` once the previous run's records have been read.
    """

    report_created = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._record: dict | None = None
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        row = QWidget()
        row.setFixedHeight(28)
        _s.themed_ss(row, "QWidget {{ background:{ADMIN_WARN_BG};"
            " border:none; border-bottom:1px solid {ADMIN_WARN_BORDER}; }}")
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(10, 0, 10, 0)
        row_lay.setSpacing(8)

        icon = QLabel("⚠")
        _s.themed_ss(icon, "font-size:12px; color:{ADMIN_WARN_FG};"
            " background:transparent; border:none;")

        self._title_lbl = QLabel("")
        _s.themed_ss(self._title_lbl, "font-size:11px; color:{ADMIN_WARN_FG};"
            " background:transparent; border:none;")

        self._report_btn = QPushButton("Create diagnostic report")
        self._report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._report_btn.setToolTip(_s.safe_tooltip(
            "Saves a file describing this PC's locale and encoding settings, the "
            "sessions that ended unexpectedly, and the tail of the app's own "
            "error logs.\n\n"
            "Addresses, MAC addresses, Wi-Fi names, your device names and your "
            "Windows username are removed before it is written. Nothing is sent "
            "anywhere."
        ))
        # padding named explicitly: the global QPushButton rule contributes
        # 5px 14px, which is too tall for a 28px strip (RULE-QSS5).
        _s.themed_ss(self._report_btn, "QPushButton {{ background:transparent;"
            " color:{ADMIN_WARN_FG}; border:1px solid {ADMIN_WARN_BORDER};"
            " border-radius:3px; font-size:10px; padding:1px 8px; }}"
            "QPushButton:hover   {{ background:{BG_HOVER}; color:{ADMIN_WARN_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ADMIN_WARN_FG}; }}")
        self._report_btn.clicked.connect(self._create_report)

        self._dismiss_btn = QPushButton()
        self._dismiss_btn.setFixedSize(18, 18)
        self._dismiss_btn.setFlat(True)
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(self._dismiss_btn)
        _s.themed_ss(self._dismiss_btn, lambda: _s.qss_dismiss_button(9))
        self._dismiss_btn.clicked.connect(self._dismiss)

        row_lay.addWidget(icon)
        row_lay.addWidget(self._title_lbl)
        row_lay.addStretch()
        row_lay.addWidget(self._report_btn)
        row_lay.addWidget(self._dismiss_btn)
        outer.addWidget(row)

    def _dismiss(self) -> None:
        if self._record is not None:
            mark_banner_seen(_dismiss_key(self._record))
        self.setVisible(False)

    def _create_report(self) -> None:
        """Write the report and say where it went.

        Not a silent success: a file the user is not told about is the same
        write-only sink this strip exists to surface.
        """
        from modules.diagnostic_report import REDACTION_NOTE
        from ui.widgets.feedback_dialog import write_diagnostic_report

        path = write_diagnostic_report()
        if path:
            self.report_created.emit(path)
            QMessageBox.information(
                self,
                "Diagnostic report saved",
                f"Saved to:\n\n{path}\n\n" + REDACTION_NOTE,
            )
            self._dismiss()
        else:
            QMessageBox.warning(
                self,
                "Diagnostic report not saved",
                "The report could not be written — the NetSentinel data folder "
                "may be full or read-only.",
            )

    def set_sessions(self, records: list | None) -> None:
        """Show the strip for the most recent unclean session, or hide it.

        Takes the whole list rather than one record because the caller has the
        list — `session_record.find_unclean_sessions()` returns them newest
        first — and because only the newest is worth naming: the report the
        button produces carries every one of them anyway.
        """
        self._record = None
        if not records:
            self.setVisible(False)
            return
        record = records[0]
        if not isinstance(record, dict) or not should_show_banner(_dismiss_key(record)):
            self.setVisible(False)
            return
        self._record = record
        self._title_lbl.setText(_describe(record))
        self.setVisible(True)

"""Show a failure as what failed, why, and what next — raw text one hover away (S5, S6).

RULE-A2 / D5. A worker's ``error`` signal carries only a ``str``, usually built from an
exception that no longer exists and often in the OS's language, so the message cannot be
chosen by reading it. Each site names a fixed entry (``ui/worker_error_catalogue.py``, or an
app-health ``ConditionSpec`` for the listener pages) and this module draws it:

* the message reads ``what. why next_step`` — never the raw string;
* the raw string is **detail**: a label's tooltip and right-click *Copy error details* action
  for as long as the label still shows the message, a toast's tooltip, a dialog's
  *Show Details*;
* one app-log record per shown error (D4), under ``netsentinel.worker_error.<key>``. The logger
  is per site because the S2.3 repeat limiter keys on logger + template: a shared logger would
  let one site's burst suppress a different site's failure.

**An exception in hand (S6).** A site that caught the exception passes the exception itself as
``raw``. ``modules/error_text.explain()`` then classifies it by structure, and its why/next
replace the entry's own — but only for kinds the entry lists in ``explains``. ``explain()`` is
context-free: its wording is right for a file write and wrong for, say, a clipboard copy, so a
site opts in to the kinds that fit it. Anything else, and every ``str`` raw, keeps the entry's
fixed text. Passing ``str(exc)`` instead of ``exc`` silently loses the explanation.

**The detail follows the label, not the caller.** These labels are also the workers'
``status`` sinks; whichever write replaces the message ends the error, and the tooltip and Copy
action go with it. No scan-start path has to remember to clear anything.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMenu, QMessageBox, QToolTip, QWidget

from modules.error_text import explain
from ui.dialog_utils import run_dialog
from ui.styles import STATUS_ICON_WARN, safe_tooltip

__all__ = [
    "ErrorText", "LOCATION_KINDS", "show_worker_error", "worker_error_text", "record_worker_error",
    "export_failed", "show_error_dialog",
]

_DETAIL_NAME = "nsWorkerErrorDetail"

#: ``error_text`` kinds that mean "this location cannot take the file". Only for these is
#: choosing another location the next step; a bug in the code writing the file is not fixed by it.
LOCATION_KINDS = frozenset({"permission_denied", "disk_full", "path_not_found", "invalid_path"})

_CHOOSE_ANOTHER_LOCATION = "Choose another location"


class ErrorText(Protocol):
    """Anything with the four fields — a ``WorkerErrorSpec`` or an app-health ``ConditionSpec``.

    An optional ``explains`` set of ``error_text`` kinds is read with ``getattr``.
    """

    @property
    def key(self) -> str:
        """Stable identifier for the entry."""

    @property
    def what(self) -> str:
        """One line naming what failed."""

    @property
    def why(self) -> str:
        """One line saying why, in the user's terms."""

    @property
    def next_step(self) -> str:
        """One line saying what to do about it."""


@dataclass(frozen=True)
class _Resolved:
    why: str
    next_step: str
    detail: str
    #: The ``error_text`` kind whose wording is shown; "" when the entry's own text is.
    kind: str


def _resolve(spec: ErrorText, raw: object) -> _Resolved:
    if not isinstance(raw, BaseException):
        return _Resolved(spec.why, spec.next_step, "" if raw is None else str(raw), "")
    detail = f"{type(raw).__name__}: {raw}" if str(raw) else type(raw).__name__
    explanation = explain(raw)
    if explanation.kind in getattr(spec, "explains", frozenset()):
        return _Resolved(explanation.why, explanation.next_step, detail, explanation.kind)
    return _Resolved(spec.why, spec.next_step, detail, "")


def worker_error_text(spec: ErrorText, raw: object = None) -> str:
    """The message itself. Also used directly by a sink that cannot hold a tooltip (a log pane)."""
    resolved = _resolve(spec, raw)
    return f"{STATUS_ICON_WARN} {spec.what}. {resolved.why} {resolved.next_step}"


def record_worker_error(spec: ErrorText, raw: object) -> None:
    """Write the raw text to the app log under the site's own logger — with the traceback, if any."""
    logger = logging.getLogger(f"netsentinel.worker_error.{spec.key}")
    if isinstance(raw, BaseException):
        logger.warning("%s: %s", spec.what, _resolve(spec, raw).detail, exc_info=raw)
    else:
        logger.warning("%s: %s", spec.what, raw)


def show_worker_error(label: QLabel, raw: object, spec: ErrorText) -> None:
    """Put ``spec``'s message on ``label``; keep ``raw`` as tooltip, Copy action and log record."""
    resolved = _resolve(spec, raw)
    text = f"{STATUS_ICON_WARN} {spec.what}. {resolved.why} {resolved.next_step}"
    label.setText(text)
    _detail_for(label).hold(text, spec.what, resolved.detail)
    record_worker_error(spec, raw)


def export_failed(exc: BaseException, spec: ErrorText,
                  retry: Optional[Callable[[], None]] = None) -> None:
    """An error toast for a failed save. ``retry`` re-runs the export (its own file dialog) and is
    offered as "Choose another location" only when the location is what failed."""
    from ui.widgets.toast import ToastManager  # deferred: toast pulls in widget modules

    resolved = _resolve(spec, exc)
    offer = retry is not None and resolved.kind in LOCATION_KINDS
    record_worker_error(spec, exc)
    ToastManager.show(
        f"{spec.what}. {resolved.why} {resolved.next_step}", "error",
        action_label=_CHOOSE_ANOTHER_LOCATION if offer else "",
        action_callback=retry if offer else None,
        detail=resolved.detail,
    )


def show_error_dialog(parent: Optional[QWidget], raw: object, spec: ErrorText,
                      retry: Optional[Callable[[], None]] = None) -> None:
    """A modal failure for a site whose channel is already a dialog: plain text, raw text behind
    *Show Details*, and "Choose another location" when ``retry`` is given and the location failed.
    The retry runs after the dialog has closed."""
    resolved = _resolve(spec, raw)
    record_worker_error(spec, raw)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(spec.what)
    box.setText(f"{spec.what}.")
    box.setInformativeText(f"{resolved.why} {resolved.next_step}")
    if resolved.detail:
        box.setDetailedText(resolved.detail)
    retry_button = None
    if retry is not None and resolved.kind in LOCATION_KINDS:
        retry_button = box.addButton(_CHOOSE_ANOTHER_LOCATION, QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    clicked: list = []
    box.buttonClicked.connect(clicked.append)
    run_dialog(box)  # RULE-WIN8: deleteLater() after exec
    if retry is not None and retry_button is not None and retry_button in clicked:
        retry()


def _detail_for(label: QLabel) -> "_ErrorDetail":
    existing = label.findChild(QObject, _DETAIL_NAME, Qt.FindChildOption.FindDirectChildrenOnly)
    if isinstance(existing, _ErrorDetail):
        return existing
    return _ErrorDetail(label)


def _exec_menu(menu: QMenu, pos: QPoint) -> None:
    """The one blocking call, kept apart so tests can stand in for it."""
    menu.exec(pos)


class _ErrorDetail(QObject):
    """Serves the raw text as tooltip and Copy action while the label still shows the message.

    Parented to the label and installed once per label, so it lives and dies with it (RULE-WIN8)
    and repeated failures reuse it. No timer (RULE-WIN18).
    """

    def __init__(self, label: QLabel) -> None:
        super().__init__(label)
        self.setObjectName(_DETAIL_NAME)
        self._label = label
        self._shown = ""
        self._what = ""
        self._raw = ""
        label.installEventFilter(self)

    def hold(self, shown: str, what: str, raw: str) -> None:
        self._shown, self._what, self._raw = shown, what, raw

    def _active(self) -> bool:
        return bool(self._raw) and self._label.text() == self._shown

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt's name
        if not self._active():
            return False
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            QToolTip.showText(event.globalPos(), safe_tooltip(self._raw), self._label)
            return True
        if kind == QEvent.Type.ContextMenu:
            menu = QMenu(self._label)
            menu.addAction("Copy error details", self._copy)
            try:
                _exec_menu(menu, event.globalPos())
            finally:
                menu.deleteLater()  # RULE-WIN8: parented to a long-lived label
            return True
        return False

    def _copy(self) -> None:
        QApplication.clipboard().setText(f"{self._what}\n{self._raw}")

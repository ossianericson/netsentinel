"""AppHealthStrip — "NetSentinel can't see X", on Home under the freshness row (S4.1, D2).

One row per app-health condition (``modules.app_health``): what stopped working, why that
matters, what to do next, and an "Open …" button to the page where it can be fixed. The
raw error text is kept to the tooltip (RULE-A2). A condition disappears the moment its
producer next succeeds; there is no dismiss, because a condition that is still true should
still be on screen, and one that stopped being true is already gone.

**Loudness (owner decision 2026-09-17).** ``Info`` conditions never open the strip on their
own. Those listeners — syslog on UDP 514, SNMP traps on UDP 162 — bind at every launch
whether or not anyone sends to them, so a strip that opened for them would warn most users
about a port they have never heard of. They are listed behind "Show N more" once the strip
is already open for something that matters, and on their own page.

Rendering is event-driven: ``set_conditions()`` is called on transitions only, from
``ui/app_health_bridge.py``. There is no timer (RULE-WIN18), which is why rows show the
clock time a condition started rather than a relative age that would go stale.
"""
from __future__ import annotations

import datetime
from typing import List, Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.app_health import Condition
from ui import styles as _s

__all__ = ["AppHealthStrip"]

#: Style-token name per severity (RULE-A3's set). Info is deliberately not a warning colour.
_SEVERITY_TOKEN = {
    "Critical": "RED",
    "High": "RED",
    "Warning": "AMBER",
    "Info": "TEXT_SECONDARY",
}

_MAX_ROWS = 3


def _since(ts: float) -> str:
    stamp = datetime.datetime.fromtimestamp(ts)
    if stamp.date() == datetime.date.today():
        return f"since {stamp.strftime('%H:%M')}"
    return f"since {stamp.strftime('%d %b %H:%M')}"


class _ConditionRow(QFrame):
    """One condition: severity dot · what / why + next · Open <page>."""

    navigate_to = pyqtSignal(str)

    def __init__(self, condition: Condition, parent=None) -> None:
        super().__init__(parent)
        self.condition = condition
        self.setObjectName("appHealthRow")
        token = _SEVERITY_TOKEN.get(condition.severity, "TEXT_SECONDARY")
        _s.themed_ss(self, lambda t=token: (
            f"QFrame#appHealthRow {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-left:3px solid {getattr(_s, t)}; border-radius:3px; }}"
        ))

        tip = f"{condition.source} — {condition.severity}, {_since(condition.first_seen)}"
        if condition.detail:
            tip += f"\n\nDetails: {condition.detail}"
        self.setToolTip(_s.safe_tooltip(tip))

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 8, 5)
        row.setSpacing(8)

        dot = QLabel("●")
        _s.themed_ss(dot, lambda t=token: (
            f"font-size:10px; color:{getattr(_s, t)}; background:transparent; border:none;"
        ))
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(1)
        self.what_label = QLabel(condition.what)
        _s.themed_ss(self.what_label, "font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
                                      " background:transparent; border:none;")
        text.addWidget(self.what_label)
        self.body_label = QLabel(f"{condition.why} {condition.next_step}")
        self.body_label.setWordWrap(True)
        _s.themed_ss(self.body_label, "font-size:10px; color:{TEXT_SECONDARY};"
                                      " background:transparent; border:none;")
        text.addWidget(self.body_label)
        row.addLayout(text, 1)

        self.cta_button: QPushButton | None = None
        if condition.cta_label:
            btn = QPushButton(f"Open {condition.cta_label}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # padding named: the global QPushButton rule's 5px 14px is too tall here (RULE-QSS5)
            _s.themed_ss(btn, "QPushButton {{ background:transparent; color:{ACCENT};"
                " border:1px solid {BORDER}; border-radius:3px; font-size:10px; padding:2px 8px; }}"
                "QPushButton:hover   {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}"
                "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
            label = condition.cta_label
            btn.clicked.connect(lambda _=False, lbl=label: self.navigate_to.emit(lbl))
            row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)
            self.cta_button = btn


class AppHealthStrip(QFrame):
    """Home strip listing active app-health conditions. Starts hidden."""

    navigate_to = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("appHealthStrip")
        self.setVisible(False)
        _s.themed_ss(self, "QFrame#appHealthStrip {{ background:{BG_DARK}; border:none;"
                           " border-bottom:1px solid {BORDER}; }}")
        self._conditions: List[Condition] = []
        self._expanded = False
        self._rows: List[_ConditionRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 6, 14, 6)
        outer.setSpacing(4)
        self._rows_host = QWidget()
        self._rows_host.setObjectName("appHealthRows")
        _s.themed_ss(self._rows_host, "QWidget#appHealthRows {{ background:transparent; }}")
        self._rows_lay = QVBoxLayout(self._rows_host)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(4)
        outer.addWidget(self._rows_host)

        self._more_btn = QPushButton("")
        self._more_btn.setFlat(True)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._more_btn, "QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            " border:none; font-size:10px; padding:0 2px; text-align:left; }}"
            "QPushButton:hover   {{ background:transparent; color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:transparent; color:{TEXT_PRIMARY}; }}")
        self._more_btn.clicked.connect(self._toggle_more)
        outer.addWidget(self._more_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self._more_btn.setVisible(False)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_conditions(self, conditions: Sequence[Condition]) -> None:
        """Replace what is shown. ``conditions`` is ``AppHealth.active()``'s order."""
        self._conditions = list(conditions)
        self._rebuild()

    def rows(self) -> List[_ConditionRow]:
        """The rows currently drawn (testable accessor, RULE-T7)."""
        return list(self._rows)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _toggle_more(self) -> None:
        self._expanded = not self._expanded
        self._rebuild()

    def _rebuild(self) -> None:
        for row in self._rows:
            self._rows_lay.removeWidget(row)
            row.deleteLater()  # parented to the strip: dropping the handle frees nothing (RULE-WIN8)
        self._rows = []

        primary = [c for c in self._conditions if c.severity != "Info"]
        if not primary:
            self._expanded = False
            self._more_btn.setVisible(False)
            self.setVisible(False)
            return

        extra = primary[_MAX_ROWS:] + [c for c in self._conditions if c.severity == "Info"]
        shown = primary[:_MAX_ROWS] + (extra if self._expanded else [])
        for condition in shown:
            row = _ConditionRow(condition)
            row.navigate_to.connect(self.navigate_to)
            self._rows_lay.addWidget(row)
            self._rows.append(row)

        if extra:
            self._more_btn.setText("Show fewer" if self._expanded else f"Show {len(extra)} more")
        else:
            self._expanded = False
        self._more_btn.setVisible(bool(extra))
        self.setVisible(True)

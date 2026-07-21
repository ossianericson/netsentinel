"""
notif_dep_card.py — _NotifDepMixin: alert dependency tree configuration card.

When a parent device (gateway/switch) goes down, suppress HOST_DOWN alerts for
all registered children.  Eliminates alert storms from a single upstream outage.

Inheriting class must provide:
  self._alert_engine   — AlertEngine instance (may be None)
  self._store          — MetricStore instance (may be None)
  self.navigate_to     — pyqtSignal(str)

Persistence: QSettings key ``"alerts/dependencies"`` stores a JSON list of
``{"parent": "IP", "children": ["IP", ...]}`` objects.

Wiring: notify_dep_changed is emitted on every save; app.py connects it to
AlertEngine.set_dependency_map() so the live engine updates immediately.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from ui.dialog_utils import run_dialog

_QS_KEY = "alerts/dependencies"


def _load_deps() -> list[dict]:
    """Load dependency list from QSettings; return [] on error."""
    qs = QSettings("NetSentinel", "NetSentinel")
    raw = qs.value(_QS_KEY, "[]")
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass  # corrupt QSettings — start fresh
    return []


def _save_deps(deps: list[dict]) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_QS_KEY, json.dumps(deps))


# ── Add-dependency dialog ─────────────────────────────────────────────────────

class _AddDepDialog(QDialog):
    """Simple dialog: parent IP + comma-separated child IPs."""

    def __init__(self, known_ips: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Alert Dependency")
        self.setMinimumWidth(380)
        self.setModal(True)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 16, 16, 16)

        intro = QLabel(
            "When the <b>parent</b> device is unreachable, NetSentinel will suppress "
            "HOST_DOWN alerts for all listed <b>children</b>."
        )
        intro.setWordWrap(True)
        _s.themed_ss(intro, "color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(intro)

        lay.addWidget(_field_lbl("Parent IP (gateway / switch)"))
        self._parent_edit = QLineEdit()
        self._parent_edit.setPlaceholderText("e.g. 192.168.1.1")
        self._parent_edit.setFixedHeight(26)
        lay.addWidget(self._parent_edit)

        lay.addWidget(_field_lbl("Child IPs (comma-separated)"))
        self._children_edit = QLineEdit()
        self._children_edit.setPlaceholderText("e.g. 192.168.1.10, 192.168.1.11")
        self._children_edit.setFixedHeight(26)
        lay.addWidget(self._children_edit)

        if known_ips:
            hint = QLabel(f"Known devices: {', '.join(known_ips[:12])}" +
                          (" …" if len(known_ips) > 12 else ""))
            hint.setWordWrap(True)
            _s.themed_ss(hint, "color:{TEXT_MUTED}; font-size:10px;")
            lay.addWidget(hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def get_values(self) -> tuple[str, list[str]]:
        parent = self._parent_edit.text().strip()
        children = [c.strip() for c in self._children_edit.text().split(",") if c.strip()]
        return parent, children


def _field_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:10px;")
    return lbl


# ── Mixin ─────────────────────────────────────────────────────────────────────

class _NotifDepMixin:
    """Mixin providing the Alert Dependency Trees card for NotificationsPage.

    The consuming class must declare:
        notify_dep_changed = pyqtSignal(str, list)
    on its own class body (pyqtSignal cannot be defined in a plain mixin).
    """

    def _build_dep_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        _s.themed_ss(card, "QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:0px;}}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Title bar
        tb = QFrame()
        tb.setFixedHeight(32)
        _s.themed_ss(tb, "background:{BG_CARD};border-bottom:1px solid {BORDER};")
        tbl_lay = QHBoxLayout(tb)
        tbl_lay.setContentsMargins(12, 0, 12, 0)
        _title = QLabel("Alert Dependency Trees")
        _s.themed_ss(_title, "color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        tbl_lay.addWidget(_title)
        tbl_lay.addStretch()

        _add_btn = QPushButton("+ Add")
        _add_btn.setFixedHeight(22)
        _add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(_add_btn, "QPushButton{{background:{ACCENT};color:{WHITE};font-size:10px;font-weight:600;"
            "border:none;border-radius:3px;padding:0 10px;}}"
            "QPushButton:hover{{background:{ACCENT_DARK};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
        _add_btn.clicked.connect(self._dep_add)
        tbl_lay.addWidget(_add_btn)
        cl.addWidget(tb)

        # Body
        body = QWidget()
        _s.themed_ss(body, "background:{BG_CARD};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 14)
        bl.setSpacing(8)

        desc = QLabel(
            "When a <b>parent</b> device (router, switch) goes DOWN, suppress HOST_DOWN alerts "
            "for all its registered <b>children</b>. "
            "Prevents 30+ alerts firing from a single upstream outage."
        )
        desc.setWordWrap(True)
        _s.themed_ss(desc, "color:{TEXT_SECONDARY};font-size:11px;")
        bl.addWidget(desc)

        _tbl_qss = (
            "QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            "gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            "QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            "font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            "QTableWidget::item{{padding:2px 5px;}}"
        )
        self._dep_table = QTableWidget(0, 3)
        self._dep_table.setHorizontalHeaderLabels(["Parent IP", "Children (suppressed)", "Added"])
        self._dep_table.horizontalHeader().setStretchLastSection(False)
        self._dep_table.horizontalHeader().setSectionResizeMode(
            1, self._dep_table.horizontalHeader().ResizeMode.Stretch
        )
        self._dep_table.verticalHeader().setVisible(False)
        self._dep_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dep_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._dep_table.setAlternatingRowColors(True)
        self._dep_table.verticalHeader().setDefaultSectionSize(24)
        self._dep_table.setFixedHeight(160)
        _s.themed_ss(self._dep_table, _tbl_qss)
        self._dep_table.setColumnWidth(0, 130)
        self._dep_table.setColumnWidth(2, 110)
        self._dep_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._dep_table.customContextMenuRequested.connect(self._dep_context_menu)
        bl.addWidget(self._dep_table)

        self._dep_empty_lbl = QLabel(
            "No dependencies defined yet — add one to suppress child alerts when a parent device goes offline."
        )
        self._dep_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dep_empty_lbl.setWordWrap(True)
        _s.themed_ss(self._dep_empty_lbl, "color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none; padding:8px 0;")
        bl.addWidget(self._dep_empty_lbl)

        btn_row = QHBoxLayout()
        _remove_btn = QPushButton("Remove selected")
        _remove_btn.setFixedHeight(24)
        _s.themed_ss(_remove_btn, "QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 12px;font-size:11px;}}"
            "QPushButton:hover{{color:{RED};border-color:{RED};}}"
            "QPushButton:pressed{{color:{TEXT_PRIMARY};}}")
        _remove_btn.clicked.connect(self._dep_remove_selected)
        btn_row.addWidget(_remove_btn)
        btn_row.addStretch()
        bl.addLayout(btn_row)

        cl.addWidget(body)
        self._dep_refresh_table()
        self._dep_card_widget = card
        return card

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _dep_refresh_table(self) -> None:
        deps = _load_deps()
        self._dep_table.setRowCount(0)
        self._dep_empty_lbl.setVisible(len(deps) == 0)
        for entry in deps:
            row = self._dep_table.rowCount()
            self._dep_table.insertRow(row)
            children = entry.get("children", [])
            added_ts = entry.get("added_ts", 0)
            added_str = (time.strftime("%Y-%m-%d", time.localtime(added_ts))
                         if added_ts else "—")
            for col, val in enumerate([
                entry.get("parent", ""),
                ", ".join(children),
                added_str,
            ]):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._dep_table.setItem(row, col, it)
            self._dep_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, entry)

    def _dep_add(self) -> None:
        known_ips: list[str] = []
        if self._store:
            try:
                devs = self._store.get_known_devices()
                known_ips = sorted(
                    d.ip for d in devs.values() if getattr(d, "ip", None)
                )
            except Exception:
                pass  # non-fatal

        dlg = _AddDepDialog(known_ips, parent=self)
        if run_dialog(dlg) != QDialog.DialogCode.Accepted:
            return
        parent, children = dlg.get_values()
        if not parent or not children:
            return

        deps = _load_deps()
        for entry in deps:
            if entry.get("parent") == parent:
                merged = list(set(entry["children"]) | set(children))
                entry["children"] = merged
                break
        else:
            deps.append({"parent": parent, "children": children,
                         "added_ts": int(time.time())})
        _save_deps(deps)
        self._dep_refresh_table()
        self._dep_push_to_engine(parent, children)

    def _dep_remove_selected(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._dep_table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            return
        deps = _load_deps()
        for row in rows:
            item = self._dep_table.item(row, 0)
            if item is None:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, dict):
                parent = entry.get("parent", "")
                deps = [d for d in deps if d.get("parent") != parent]
                if self._alert_engine and parent:
                    self._alert_engine.set_dependency_map(parent, [])
        _save_deps(deps)
        self._dep_refresh_table()

    def _dep_context_menu(self, pos) -> None:
        row = self._dep_table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        _s.themed_ss(menu, "QMenu{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            "font-size:11px;}}"
            "QMenu::item:selected{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}")
        act_remove = menu.addAction("Remove dependency")
        chosen = menu.exec(self._dep_table.viewport().mapToGlobal(pos))
        if chosen == act_remove:
            self._dep_table.selectRow(row)
            self._dep_remove_selected()

    def _dep_push_to_engine(self, parent: str, children: list[str]) -> None:
        if self._alert_engine and parent:
            self._alert_engine.set_dependency_map(parent, children)
        self.notify_dep_changed.emit(parent, children)

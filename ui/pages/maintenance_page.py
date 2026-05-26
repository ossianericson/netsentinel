"""
MaintenancePage — UI for managing maintenance windows.

Allows users to define time-bounded suppression windows per host (or all hosts).
While a window is active, alerts for the covered hosts are silently dropped.

Features:
  - KPI tiles: active windows, next expiry, suppressed alerts
  - Windows table: label, hosts, start, end, status (Active / Scheduled / Expired)
  - Add / Edit / Delete / Disable controls
  - Suppression log (last 500 suppressed alerts)
  - Persistence via QSettings key "maintenance/windows_json"
  - Auto-purge windows expired > 7 days ago on page load

Architecture rules:
  • All colours from ui/styles — no hardcoded hex values.
  • MaintenanceWindowManager injected via set_manager().
  • QSettings used for persistence.
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QDateTime

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BG_DARK,
    BORDER, CARD_HDR_BORDER, CARD_RADIUS, GREEN, RED, RED_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from modules.maintenance_window import (
    MaintenanceWindow, MaintenanceWindowManager,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _page_header(title: str, subtitle: str = "") -> QFrame:
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {BORDER}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:{CARD_RADIUS};}}"
    )
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    tb = QFrame()
    tb.setFixedHeight(32)
    tb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)
    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(8)
    cl.addWidget(body)
    return card, bl


def _kpi_tile(label: str, value: str, accent: str = ACCENT) -> QWidget:
    w = QFrame()
    w.setStyleSheet(
        f"QFrame{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-left:3px solid {accent};min-width:110px;}}"
    )
    vl = QVBoxLayout(w)
    vl.setContentsMargins(10, 8, 10, 8)
    vl.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;font-weight:bold;")
    val = QLabel(value)
    val.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:22px;font-weight:bold;")
    val.setObjectName("kpi_val")
    vl.addWidget(lbl)
    vl.addWidget(val)
    return w


def _btn(text: str, primary: bool = False, danger: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(26)
    if primary:
        b.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:2px;padding:0 14px;font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
            f"QPushButton:disabled{{background:{BORDER};color:{TEXT_SECONDARY};}}"
        )
    elif danger:
        b.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{RED};border:1px solid {RED};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{background:{RED};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{RED};color:{WHITE};}}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};background:{BG_CARD};}}"
            f"QPushButton:pressed{{color:{ACCENT};border-color:{ACCENT};background:{BG_CARD};}}"
            f"QPushButton:disabled{{color:{BORDER};}}"
        )
    return b


def _window_status(w: MaintenanceWindow) -> tuple[str, str]:
    """Return (status_text, color)."""
    now = int(time.time())
    if not w.active:
        return "Disabled", TEXT_SECONDARY
    if w.end_ts < now:
        return "Expired", TEXT_SECONDARY
    if w.start_ts > now:
        return "Scheduled", AMBER
    return "Active", GREEN


# ── Add/Edit dialog ───────────────────────────────────────────────────────────

class _WindowDialog(QDialog):
    """Modal dialog for creating or editing a MaintenanceWindow."""

    def __init__(self, window: Optional[MaintenanceWindow] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Maintenance Window" if window is None else "Edit Maintenance Window")
        self.setFixedWidth(460)
        self.setStyleSheet(f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;")

        form = QFormLayout(self)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self._label = QLineEdit(window.label if window else "")
        self._label.setPlaceholderText("e.g. Router firmware upgrade")
        self._label.setStyleSheet(
            f"QLineEdit{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 6px;font-size:11px;}}"
        )
        form.addRow("Label:", self._label)

        self._hosts = QLineEdit(", ".join(window.hosts) if window else "")
        self._hosts.setPlaceholderText("192.168.1.1, 10.0.0.1  (blank = all hosts)")
        self._hosts.setStyleSheet(self._label.styleSheet())
        form.addRow("Hosts:", self._hosts)

        now_qt = QDateTime.currentDateTime()
        self._start = QDateTimeEdit(now_qt)
        self._start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._start.setCalendarPopup(True)
        if window:
            self._start.setDateTime(QDateTime.fromSecsSinceEpoch(window.start_ts))
        form.addRow("Start:", self._start)

        end_default = QDateTime.fromSecsSinceEpoch(
            window.end_ts if window else int(time.time()) + 3600
        )
        self._end = QDateTimeEdit(end_default)
        self._end.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._end.setCalendarPopup(True)
        form.addRow("End:", self._end)

        self._active = QCheckBox("Enabled")
        self._active.setChecked(window.active if window else True)
        form.addRow("", self._active)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _validate(self):
        if not self._label.text().strip():
            QMessageBox.warning(self, "Validation", "Label is required.")
            return
        if self._end.dateTime() <= self._start.dateTime():
            QMessageBox.warning(self, "Validation", "End time must be after start time.")
            return
        self.accept()

    def get_window(self, existing_id: str = "") -> MaintenanceWindow:
        hosts_raw = self._hosts.text().strip()
        hosts = [h.strip() for h in hosts_raw.split(",") if h.strip()] if hosts_raw else []
        return MaintenanceWindow(
            id=existing_id or "",
            label=self._label.text().strip(),
            hosts=hosts,
            start_ts=self._start.dateTime().toSecsSinceEpoch(),
            end_ts=self._end.dateTime().toSecsSinceEpoch(),
            active=self._active.isChecked(),
        )


# ── Main page ─────────────────────────────────────────────────────────────────

class MaintenancePage(QWidget):
    """Maintenance window management page."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._manager: Optional[MaintenanceWindowManager] = None

        # Auto-refresh timer (updates Active/Scheduled/Expired status every minute)
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self._refresh_table)
        self._timer.start()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(_page_header(
            "Maintenance Windows",
            "Suppress alerts for selected hosts during planned maintenance",
        ))

        self._kpi_active    = _kpi_tile("Active",     "—", GREEN)
        self._kpi_scheduled = _kpi_tile("Scheduled",  "—", AMBER)
        self._kpi_suppressed = _kpi_tile("Suppressed", "—", RED)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        for w in (self._kpi_active, self._kpi_scheduled, self._kpi_suppressed):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        outer.addLayout(kpi_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)
        il.addWidget(self._build_windows_card())
        il.addWidget(self._build_log_card())
        il.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    # ── Windows card ──────────────────────────────────────────────────────────

    def _build_windows_card(self) -> QWidget:
        card, bl = _card("Maintenance Windows")

        self._win_table = QTableWidget(0, 6)
        self._win_table.setHorizontalHeaderLabels(
            ["Label", "Hosts", "Start", "End", "Duration", "Status"]
        )
        self._win_table.horizontalHeader().setStretchLastSection(False)
        self._win_table.horizontalHeader().setSectionResizeMode(
            0, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )
        self._win_table.verticalHeader().setVisible(False)
        self._win_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._win_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._win_table.setAlternatingRowColors(True)
        self._win_table.setFixedHeight(200)
        self._win_table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((0, 140, 130, 130, 70), range(1, 6)):
            self._win_table.setColumnWidth(col, w)
        bl.addWidget(self._win_table)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        btn_add    = _btn("+ Add Window", primary=True)
        btn_edit   = _btn("Edit")
        btn_delete = _btn("Delete", danger=True)
        btn_add.clicked.connect(self._add_window)
        btn_edit.clicked.connect(self._edit_window)
        btn_delete.clicked.connect(self._delete_window)
        action_row.addWidget(btn_add)
        action_row.addWidget(btn_edit)
        action_row.addWidget(btn_delete)
        action_row.addStretch()
        bl.addLayout(action_row)
        return card

    # ── Suppression log card ──────────────────────────────────────────────────

    def _build_log_card(self) -> QWidget:
        card, bl = _card("Suppression Log")

        self._log_table = QTableWidget(0, 5)
        self._log_table.setHorizontalHeaderLabels(
            ["Time", "Window", "Host", "Severity", "Alert"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(True)
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setAlternatingRowColors(True)
        self._log_table.setFixedHeight(180)
        self._log_table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((110, 140, 120, 70), range(4)):
            self._log_table.setColumnWidth(col, w)
        bl.addWidget(self._log_table)

        btn_row = QHBoxLayout()
        btn_refresh = _btn("Refresh Log")
        btn_clear   = _btn("Clear Log")
        btn_refresh.clicked.connect(self._refresh_log)
        btn_clear.clicked.connect(self._clear_log)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        bl.addLayout(btn_row)
        return card

    # ── Manager injection ─────────────────────────────────────────────────────

    def set_manager(self, manager: MaintenanceWindowManager) -> None:
        self._manager = manager
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        if self._manager is None:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("maintenance/windows_json", self._manager.to_json())

    def _load(self) -> None:
        if self._manager is None:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("maintenance/windows_json", "[]")
        self._manager.load_from_json(raw)
        self._manager.purge_expired(older_than_days=7)
        self._refresh_table()
        self._update_kpis()

    # ── Table refresh ─────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh_table(self) -> None:
        if self._manager is None:
            return
        from PyQt6.QtGui import QColor
        self._win_table.setRowCount(0)
        for w in self._manager.get_windows():
            row = self._win_table.rowCount()
            self._win_table.insertRow(row)
            hosts_str  = ", ".join(w.hosts) if w.hosts else "(all hosts)"
            start_str  = time.strftime("%Y-%m-%d %H:%M", time.localtime(w.start_ts))
            end_str    = time.strftime("%Y-%m-%d %H:%M", time.localtime(w.end_ts))
            dur_str    = f"{w.duration_minutes} min"
            status, color = _window_status(w)
            for col, val in enumerate([w.label, hosts_str, start_str, end_str, dur_str, status]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, w.id)
                if col == 5:
                    item.setForeground(QColor(color))
                self._win_table.setItem(row, col, item)
        self._update_kpis()

    def _update_kpis(self) -> None:
        if self._manager is None:
            return
        now = int(time.time())
        windows = self._manager.get_windows()
        active    = sum(1 for w in windows if w.is_currently_active)
        scheduled = sum(1 for w in windows if w.active and w.start_ts > now)
        suppressed = len(self._manager.get_suppression_log())
        for tile, val, col in [
            (self._kpi_active,     str(active),    GREEN if active else TEXT_SECONDARY),
            (self._kpi_scheduled,  str(scheduled), AMBER if scheduled else TEXT_SECONDARY),
            (self._kpi_suppressed, str(suppressed), RED if suppressed else TEXT_SECONDARY),
        ]:
            lbl = tile.findChild(QLabel, "kpi_val")
            if lbl:
                lbl.setText(val)
                lbl.setStyleSheet(f"color:{col};font-size:22px;font-weight:bold;")

    # ── CRUD actions ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def _add_window(self) -> None:
        dlg = _WindowDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        w = dlg.get_window()
        if self._manager:
            self._manager.add_window(w)
            self._save()
            self._refresh_table()

    @pyqtSlot()
    def _edit_window(self) -> None:
        wid = self._selected_window_id()
        if not wid or self._manager is None:
            return
        existing = next((w for w in self._manager.get_windows() if w.id == wid), None)
        if existing is None:
            return
        dlg = _WindowDialog(window=existing, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dlg.get_window(existing_id=wid)
        self._manager.update_window(updated)
        self._save()
        self._refresh_table()

    @pyqtSlot()
    def _delete_window(self) -> None:
        wid = self._selected_window_id()
        if not wid or self._manager is None:
            return
        reply = QMessageBox.question(
            self, "Delete Window", "Delete the selected maintenance window?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._manager.remove_window(wid)
        self._save()
        self._refresh_table()

    def _selected_window_id(self) -> Optional[str]:
        rows = self._win_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self._win_table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    # ── Log actions ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh_log(self) -> None:
        if self._manager is None:
            return
        from PyQt6.QtGui import QColor
        entries = self._manager.get_suppression_log()
        self._log_table.setRowCount(0)
        _sev_color = {"CRITICAL": RED, "WARNING": AMBER, "INFO": ACCENT}
        for e in reversed(entries):
            row = self._log_table.rowCount()
            self._log_table.insertRow(row)
            ts_str = time.strftime("%H:%M:%S", time.localtime(e.ts))
            for col, val in enumerate([ts_str, e.window_label, e.host, e.severity, e.message]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 3:
                    item.setForeground(QColor(_sev_color.get(e.severity, TEXT_PRIMARY)))
                self._log_table.setItem(row, col, item)

    @pyqtSlot()
    def _clear_log(self) -> None:
        if self._manager:
            self._manager.clear_suppression_log()
        self._log_table.setRowCount(0)
        self._update_kpis()

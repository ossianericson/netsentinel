"""
SyslogPage — live syslog viewer (T3#14).

Shows a live table of received syslog messages with:
  • KPI tiles: Total, Critical (EMERG/ALERT/CRIT), Errors (ERR/WARNING), Info
  • Live table: Time / Source IP / Severity / Facility / Hostname / App / Message
  • Severity filter dropdown + text search bar
  • Double-click row → full raw message detail dialog
  • Max 1000 rows (prunes oldest when cap reached)

Architecture rules:
  • Light content area, cards, no dark backgrounds
  • 24px row height
  • No blocking I/O on main thread
  • parent=w at all widget constructions (RULE 17)
"""

from __future__ import annotations

import datetime

from PyQt6.QtCore    import Qt, pyqtSlot
from PyQt6.QtGui     import QColor
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QTableWidgetItem, QVBoxLayout, QWidget,
    QFrame, QTextEdit,
)
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard

from ui.tabs_helpers import _table
from ui import styles as _s
from ui.dialog_utils import run_dialog


# ── Shared helpers ────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    outer = QFrame()
    outer.setObjectName("card")
    _s.themed_ss(outer, "QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}")
    outer_lay = QVBoxLayout(outer)
    outer_lay.setContentsMargins(0, 0, 0, 0)
    outer_lay.setSpacing(0)

    title_bar = QLabel(title)
    _s.themed_ss(title_bar, "QLabel {{ background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};"
        " padding:4px 12px; font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; }}")
    outer_lay.addWidget(title_bar)

    body = QWidget()
    _s.themed_ss(body, "background:{BG_CARD}; border:none;")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)
    outer_lay.addWidget(body)
    return outer, body_lay


def _kpi_tile(label: str, value: str = "0", accent_name: str = "ACCENT") -> tuple[QWidget, QLabel]:
    tile = QWidget()
    _s.themed_ss(tile, lambda a=accent_name: (
        f"QWidget {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
        f" border-left:3px solid {getattr(_s, a)}; }}"
    ))
    tile.setMinimumWidth(110)
    tile.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(8, 4, 8, 4)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    _s.themed_ss(lbl, "font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    _s.themed_ss(val, "font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── Severity colour coding ────────────────────────────────────────────────────
# Token NAME strings (resolved live via getattr(_s, name)) — a bare-token dict
# would freeze at import and never follow a theme switch.

_SEV_COLOUR = {
    0: "RED",    # EMERG
    1: "RED",    # ALERT
    2: "RED",    # CRIT
    3: "AMBER",  # ERR
    4: "AMBER",  # WARNING
    5: "TEXT_SECONDARY",  # NOTICE
    6: "TEXT_SECONDARY",  # INFO
    7: "TEXT_SECONDARY",  # DEBUG
}


def _sev_color(sev: int) -> str:
    """Live theme colour for a syslog severity level."""
    return getattr(_s, _SEV_COLOUR.get(sev, "TEXT_SECONDARY"))


# ── Detail dialog ─────────────────────────────────────────────────────────────

class _MsgDetailDialog(QDialog):
    def __init__(self, row_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Syslog Message Detail")
        self.setMinimumSize(560, 300)

        lay = QVBoxLayout(self)

        info = (
            f"Time:     {datetime.datetime.fromtimestamp(row_data.get('ts', 0)).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Source:   {row_data.get('src_ip', '')}:{row_data.get('src_port', '')}\n"
            f"Severity: {row_data.get('severity_name', '')}  "
            f"Facility: {row_data.get('facility_name', '')}\n"
            f"Hostname: {row_data.get('hostname', '')}  "
            f"App: {row_data.get('app_name', '')}  "
            f"PID: {row_data.get('procid', '')}\n"
            f"Message:  {row_data.get('message', '')}"
        )

        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText(info)
        _s.themed_ss(detail, "QTextEdit {{ font-size:11px; color:{TEXT_PRIMARY}; "
            "background:{BG_CARD}; border:1px solid {BORDER}; }}")
        lay.addWidget(QLabel("Raw message:"))
        raw_box = QTextEdit()
        raw_box.setReadOnly(True)
        raw_box.setPlainText(row_data.get("raw", ""))
        raw_box.setMaximumHeight(80)
        _s.themed_ss(raw_box, "QTextEdit {{ font-size:11px; color:{TEXT_SECONDARY}; "
            "font-family:Consolas,monospace; background:{BG_CARD}; border:1px solid {BORDER}; }}")
        lay.addWidget(detail)
        lay.addWidget(raw_box)

        close_btn = QPushButton("Close")
        _s.themed_ss(close_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " padding:4px 16px; font-size:11px; border-radius:4px; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


# ── Main page ─────────────────────────────────────────────────────────────────

_MAX_ROWS = 1000


class SyslogPage(QWidget):
    """Live syslog viewer page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total      = 0
        self._crit_count = 0
        self._err_count  = 0
        self._info_count = 0
        self._all_rows: list[dict] = []   # full buffer for filter
        self._filter_sev: int = -1        # -1 = all
        self._filter_text: str = ""
        self._setup_ui()

    # ── UI build ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        _s.themed_ss(self, "QWidget {{ background:{BG_DARK}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Page title
        title = QLabel("Syslog Receiver")
        _s.themed_ss(title, "font-size:18px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent;")
        sub = QLabel("Passive UDP listener — receives syslog from routers, switches, and Linux hosts (RFC 3164 / RFC 5424).")
        _s.themed_ss(sub, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        root.addWidget(title)
        root.addWidget(sub)

        # Status bar
        self._status_lbl = QLabel("Not listening.")
        _s.themed_ss(self._status_lbl, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        root.addWidget(self._status_lbl)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        tile_total, self._kpi_total = _kpi_tile("Total Messages")
        tile_crit,  self._kpi_crit  = _kpi_tile("Critical",        "0", "RED")
        tile_err,   self._kpi_err   = _kpi_tile("Errors/Warnings",  "0", "AMBER")
        tile_info,  self._kpi_info  = _kpi_tile("Info/Debug",       "0", "GREEN")
        for parent_tile in (tile_total, tile_crit, tile_err, tile_info):
            kpi_row.addWidget(parent_tile)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # Filter bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        sev_label = QLabel("Severity:")
        _s.themed_ss(sev_label, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        self._sev_filter = QComboBox()
        self._sev_filter.addItem("All severities", -1)
        for sev_id, sev_name in [
            (0, "EMERG"), (1, "ALERT"), (2, "CRIT"),
            (3, "ERR"),   (4, "WARNING"), (5, "NOTICE"),
            (6, "INFO"),  (7, "DEBUG"),
        ]:
            self._sev_filter.addItem(sev_name, sev_id)
        _s.themed_ss(self._sev_filter, "QComboBox {{ font-size:11px; border:1px solid {BORDER};"
            " background:{BG_CARD}; color:{TEXT_PRIMARY}; padding:2px 8px; }}")
        self._sev_filter.currentIndexChanged.connect(self._on_filter_changed)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search hostname, app, message…")
        _s.themed_ss(self._search_box, "QLineEdit {{ font-size:11px; border:1px solid {BORDER};"
            " background:{BG_CARD}; color:{TEXT_PRIMARY}; padding:2px 8px; }}")
        self._search_box.textChanged.connect(self._on_filter_changed)

        clear_btn = QPushButton("Clear")
        _s.themed_ss(clear_btn, "QPushButton {{ font-size:11px; border:1px solid {BORDER};"
            " background:{BG_CARD}; color:{TEXT_PRIMARY}; padding:2px 12px; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        clear_btn.clicked.connect(self._clear)

        filter_row.addWidget(sev_label)
        filter_row.addWidget(self._sev_filter)
        filter_row.addWidget(self._search_box)
        filter_row.addWidget(clear_btn)
        filter_row.addStretch()
        root.addLayout(filter_row)

        # Log table card
        card, body_lay = _card("Live Syslog Feed")
        self._table = _table(["Time", "Source IP", "Severity", "Facility", "Hostname", "App", "Message"])
        self._table.setColumnWidth(0, 140)
        self._table.setColumnWidth(1, 110)
        self._table.setColumnWidth(2, 75)
        self._table.setColumnWidth(3, 75)
        self._table.setColumnWidth(4, 120)
        self._table.setColumnWidth(5, 100)
        self._table.doubleClicked.connect(self._on_row_dbl_click)

        def _sys_copy_message():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 6)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _sys_copy_host():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 4) or self._table.item(r, 1)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _sys_filter_host():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 4) or self._table.item(r, 1)
                if it:
                    self._search_box.setText(it.text())

        install_copy_menu(self._table, [
            ("separator",     None),
            ("Copy message",  _sys_copy_message),
            ("Copy host",     _sys_copy_host),
            ("separator",     None),
            ("Filter by host", _sys_filter_host),
        ])

        # ── Table / empty state stack inside the card ─────────────────────────
        from PyQt6.QtWidgets import QStackedWidget
        self._table_stack = QStackedWidget()

        _empty_card = EmptyStateCard(
            icon="◉",
            title="Syslog Receiver",
            what_it_shows=(
                "Live syslog messages from routers, switches, and Linux hosts — "
                "timestamp, severity, source, app name, and message text."
            ),
            why_it_matters=(
                "Syslog is the earliest warning of hardware failures, authentication "
                "attempts, and configuration changes across your infrastructure."
            ),
            btn_label="Waiting for messages…",
        )
        # The CTA has no action — the page is already listening; disable it
        _empty_card.findChild(QPushButton).setEnabled(False)

        self._table_stack.addWidget(_empty_card)  # index 0 — no messages yet
        self._table_stack.addWidget(self._table)  # index 1 — messages present
        body_lay.addWidget(self._table_stack)

        root.addWidget(card, stretch=1)

        # Store row data for double-click detail
        self._row_data_cache: list[dict] = []

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_message_received(self, msg: dict) -> None:
        """Called by SyslogWorker.message_received signal."""
        self._total += 1
        sev = msg.get("severity", 6)
        if sev <= 2:
            self._crit_count += 1
        elif sev <= 4:
            self._err_count += 1
        else:
            self._info_count += 1

        self._all_rows.append(msg)
        # Cap buffer
        if len(self._all_rows) > _MAX_ROWS:
            self._all_rows = self._all_rows[-_MAX_ROWS:]

        self._update_kpis()
        self._apply_filter()

    @pyqtSlot(str)
    def on_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    @pyqtSlot(str)
    def on_error(self, text: str) -> None:
        self._status_lbl.setText(
            f"Syslog receiver error — {text}. "
            "Check that UDP port 514 is not blocked by another application or firewall."
        )
        _s.themed_ss(self._status_lbl, "font-size:11px; color:{AMBER}; background:transparent;")

    # ── Filter / table rebuild ────────────────────────────────────────────────

    def _on_filter_changed(self) -> None:
        self._filter_sev  = self._sev_filter.currentData()
        self._filter_text = self._search_box.text().lower()
        self._apply_filter()

    def _apply_filter(self) -> None:
        rows = self._all_rows
        if self._filter_sev is not None and self._filter_sev >= 0:
            rows = [r for r in rows if r.get("severity", 6) == self._filter_sev]
        if self._filter_text:
            ft = self._filter_text
            rows = [r for r in rows if (
                ft in r.get("hostname", "").lower()
                or ft in r.get("app_name", "").lower()
                or ft in r.get("message", "").lower()
                or ft in r.get("src_ip", "").lower()
            )]

        self._row_data_cache = rows
        self._rebuild_table(rows)

    def _rebuild_table(self, rows: list[dict]) -> None:
        self._table_stack.setCurrentIndex(1 if rows else 0)
        if not rows:
            return

        self._table.setRowCount(0)
        for r in rows[-_MAX_ROWS:]:
            self._add_row(r)
        # Scroll to bottom (most recent)
        self._table.scrollToBottom()

    def _add_row(self, r: dict) -> None:
        row_idx = self._table.rowCount()
        self._table.insertRow(row_idx)

        ts_str = datetime.datetime.fromtimestamp(r.get("ts", 0)).strftime("%Y-%m-%d %H:%M:%S")
        sev    = r.get("severity", 6)
        colour = _sev_color(sev)

        cells = [
            ts_str,
            r.get("src_ip", ""),
            r.get("severity_name", ""),
            r.get("facility_name", ""),
            r.get("hostname", ""),
            r.get("app_name", ""),
            r.get("message", ""),
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            item.setForeground(QColor(colour) if col == 2 else QColor(_s.TEXT_PRIMARY))
            self._table.setItem(row_idx, col, item)

    def _update_kpis(self) -> None:
        self._kpi_total.setText(str(self._total))
        self._kpi_crit.setText(str(self._crit_count))
        self._kpi_err.setText(str(self._err_count))
        self._kpi_info.setText(str(self._info_count))

    def _clear(self) -> None:
        self._all_rows.clear()
        self._row_data_cache.clear()
        self._total = self._crit_count = self._err_count = self._info_count = 0
        self._update_kpis()
        self._table.setRowCount(0)
        self._table_stack.setCurrentIndex(0)

    def _on_row_dbl_click(self, index) -> None:
        row = index.row()
        if 0 <= row < len(self._row_data_cache):
            dlg = _MsgDetailDialog(self._row_data_cache[row], parent=self)
            run_dialog(dlg)

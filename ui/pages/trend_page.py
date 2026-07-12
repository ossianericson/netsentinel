"""
TrendPage — Predictive trend alerting UI.

Shows linear-regression forecasts for RTT, packet loss, and jitter for every
monitored host. Highlights hosts whose metrics are projected to breach
configured thresholds within a user-selected time horizon.

Architecture rules:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread (QThread for analysis run).
  • MetricStore injected via constructor.
"""
from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ui import styles as _s
from ui.table_utils import kpi_tile as _shared_kpi_tile
from modules.trend_analyser import TrendReport, run_full_trend_report
from ui.widgets.context_menu import install_copy_menu


# ── Mini sparkline widget (VIZ-3) ─────────────────────────────────────────────

class _MiniSparkline(QWidget):
    """80×18 QPainter sparkline for use in the trend table Trend column."""

    def __init__(self, points: list, color_name: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(80, 18)
        self._points = list(points)
        self._color_name = color_name

    def paintEvent(self, event) -> None:
        pts = self._points
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("transparent"))
        if len(pts) < 2:
            painter.end()
            return
        w, h   = self.width(), self.height()
        pad    = 2
        uw, uh = w - 2 * pad, h - 2 * pad
        mn, mx = min(pts), max(pts)
        span   = mx - mn if mx != mn else 1.0

        def _x(i):  return pad + (i / (len(pts) - 1)) * uw
        def _y(v):  return pad + (1.0 - (v - mn) / span) * uh

        from PyQt6.QtCore import QPointF
        path = QPainterPath()
        path.moveTo(QPointF(_x(0), _y(pts[0])))
        for i, v in enumerate(pts[1:], 1):
            path.lineTo(QPointF(_x(i), _y(v)))
        pen = QPen(QColor(getattr(_s, self._color_name)), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()


# ── Background worker ─────────────────────────────────────────────────────────

class _TrendWorker(QThread):
    result_ready = pyqtSignal(object)   # TrendReport
    error        = pyqtSignal(str)

    def __init__(self, store, window_hours: float, parent=None):
        super().__init__(parent)
        self._store = store
        self._window_hours = window_hours

    def run(self):
        try:
            report = run_full_trend_report(self._store, window_hours=self._window_hours)
            self.result_ready.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _page_header(title: str, subtitle: str = "") -> QFrame:
    container = QFrame()
    container.setObjectName("pageHeader")
    _s.themed_ss(container, "QFrame#pageHeader {{ background: transparent; border: none;"
        " border-bottom: 1px solid {BORDER}; }}")
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    _s.themed_ss(t, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;")
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        _s.themed_ss(s, "color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;")
        vbox.addWidget(s)
    return container


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    _s.themed_ss(card, "QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:{CARD_RADIUS};}}")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    tb = QFrame()
    tb.setFixedHeight(32)
    _s.themed_ss(tb, "background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    _s.themed_ss(lbl, "color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)
    body = QWidget()
    _s.themed_ss(body, "background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(8)
    cl.addWidget(body)
    return card, bl




_SEV_COLOR_NAMES = {"CRITICAL": "RED", "WARNING": "AMBER", "INFO": "ACCENT", "CLEAN": "GREEN"}
_METRIC_LABEL = {"rtt_ms": "RTT (ms)", "loss_pct": "Loss (%)", "jitter_ms": "Jitter (ms)"}


def _sev_color(severity: str) -> str:
    return getattr(_s, _SEV_COLOR_NAMES.get(severity, "TEXT_PRIMARY"))


class TrendPage(QWidget):
    """Predictive trend alerting page."""

    navigate_to    = pyqtSignal(str)
    report_ready   = pyqtSignal(object)  # TrendReport — for OverviewPage.on_trend_result()
    scan_requested = pyqtSignal()

    def __init__(self, store=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._store = store
        self._worker: Optional[_TrendWorker] = None
        self._last_report: Optional[TrendReport] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Predictive Trend Alerting", subtitle="Forecasts when your network metrics will cross alert thresholds based on recent trends.")
        _hdr.show_first_visit_banner(
            "trend_forecast",
            "Forecasts use linear regression over recent history, so a device trending "
            "toward failure shows an estimated time-to-threshold — treat it as an early "
            "warning, not a guarantee.",
        )
        outer.addWidget(_hdr)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        _kh, self._kpi_hosts_lbl    = _shared_kpi_tile("Hosts Analysed", "—")
        _kc, self._kpi_critical_lbl = _shared_kpi_tile("Critical",        "—", _s.RED)
        _kw, self._kpi_warnings_lbl = _shared_kpi_tile("Warnings",        "—", _s.AMBER)
        _kl, self._kpi_clean_lbl    = _shared_kpi_tile("Clean",           "—", _s.GREEN)
        for w in (_kh, _kc, _kw, _kl):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        outer.addLayout(kpi_row)

        # RECUR-4: this-week vs last-week RTT headline
        self._headline_lbl = QLabel("")
        self._headline_lbl.setVisible(False)
        _s.themed_ss(self._headline_lbl, "font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; padding:8px 14px;")
        outer.addWidget(self._headline_lbl)

        # ── Content stack: page 0 = empty state, page 1 = analysis controls ─────
        self._trend_stack = QStackedWidget()

        from ui.widgets.empty_state_card import EmptyStateCard
        _empty = EmptyStateCard(
            icon="▲",
            title="No trend data yet",
            what_it_shows=(
                "Linear-regression forecasts for RTT, packet loss, and jitter — "
                "showing which hosts are trending toward failure and when."
            ),
            why_it_matters=(
                "Run scans daily for at least 3 days and enable the Network Logger "
                "to build the baseline needed for accurate forecasts."
            ),
            btn_label="Start Logger →",
        )
        _empty.clicked.connect(lambda: self.navigate_to.emit("Network Logger"))
        self._trend_stack.addWidget(_empty)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        inner = QWidget()
        _s.themed_ss(inner, "background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)
        il.addWidget(self._build_controls())
        il.addWidget(self._build_results_card())
        il.addStretch()
        scroll.setWidget(inner)
        self._trend_stack.addWidget(scroll)

        outer.addWidget(self._trend_stack, 1)

    # ── Controls card ─────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        row = QWidget()
        _s.themed_ss(row, "background:{BG_DARK};")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        lbl = QLabel("Analysis window:")
        _s.themed_ss(lbl, "color:{TEXT_SECONDARY};font-size:11px;")
        hl.addWidget(lbl)

        self._window_combo = QComboBox()
        for label, hours in [("6 hours", 6), ("12 hours", 12), ("24 hours", 24),
                              ("3 days", 72), ("7 days", 168)]:
            self._window_combo.addItem(label, hours)
        self._window_combo.setCurrentIndex(2)  # default 24 h
        self._window_combo.setFixedHeight(26)
        _s.themed_ss(self._window_combo, "QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 6px;font-size:11px;}}"
            "QComboBox::drop-down{{border:none;}}"
            "QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            "border:1px solid {BORDER};selection-background-color:{ACCENT};}}")
        hl.addWidget(self._window_combo)

        self._btn_run = QPushButton("▶  Run Analysis")
        self._btn_run.setFixedHeight(26)
        _s.themed_ss(self._btn_run, "QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            "border-radius:2px;padding:0 16px;font-size:11px;font-weight:bold;}}"
            "QPushButton:hover{{background:{ACCENT_DARK};}}"
            "QPushButton:disabled{{background:{BORDER};color:{TEXT_SECONDARY};}}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._btn_run.clicked.connect(self._run_analysis)
        hl.addWidget(self._btn_run)

        self._status_lbl = QLabel(
            "Enable Network RTT logging in Network Logger to build forecast data."
        )
        _s.themed_ss(self._status_lbl, "color:{TEXT_SECONDARY};font-size:10px;")
        hl.addWidget(self._status_lbl)

        self._btn_log_hub = QPushButton("Open Network Logger →")
        self._btn_log_hub.setFlat(True)
        self._btn_log_hub.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._btn_log_hub, "QPushButton{{color:{ACCENT};font-size:10px;background:transparent;"
            "border:none;padding:0 0 0 4px;}}"
            "QPushButton:hover{{color:{ACCENT_DARK};}}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        self._btn_log_hub.clicked.connect(lambda: self.navigate_to.emit("Network Logger"))
        hl.addWidget(self._btn_log_hub)
        hl.addStretch()
        return row

    # ── Results card ──────────────────────────────────────────────────────────

    def _build_results_card(self) -> QWidget:
        card, bl = _card("Trend Forecast — All Hosts")

        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["Host", "Metric", "Current", "Trend/h", "Threshold", "ETA", "Verdict", "Trend"]
        )
        _hdr_tips = {
            1: "Metric being tracked: RTT (round-trip time), Loss (packet loss %), or Jitter (variation in RTT).",
            2: ("Current measured value.\n"
                "RTT: Good < 20 ms · Acceptable 20–100 ms · Poor > 100 ms\n"
                "Loss: Good 0% · Acceptable < 1% · Poor ≥ 1%\n"
                "Jitter: Good < 5 ms · Acceptable 5–20 ms · Poor > 20 ms"),
            3: "Rate of change per hour (linear regression slope). Positive = getting worse.",
            4: "The configured alert threshold. When the projected value exceeds this, a verdict is raised.",
            5: "Estimated time until the metric breaches its threshold at the current trend rate.",
            6: "CRITICAL = breach imminent.  WARNING = trending up.  CLEAN = stable or improving.",
        }
        for col, tip in _hdr_tips.items():
            item = self._table.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(
            0, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )
        self._table.setColumnWidth(7, 90)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(300)
        _s.themed_ss(self._table, "QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            "gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            "QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            "font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            "QTableWidget::item{{padding:2px 5px;}}")
        for w, col in zip((130, 80, 70, 70, 80, 80), range(6)):
            self._table.setColumnWidth(col, w)

        def _trend_copy_metric():
            r = self._table.currentRow()
            if r >= 0:
                host_it   = self._table.item(r, 0)
                metric_it = self._table.item(r, 1)
                parts = [it.text() for it in (host_it, metric_it) if it]
                if parts:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(" — ".join(parts))

        def _trend_export_row():
            r = self._table.currentRow()
            if r < 0:
                return
            headers = [self._table.horizontalHeaderItem(c).text()
                       for c in range(self._table.columnCount())
                       if self._table.horizontalHeaderItem(c)]
            values  = [(self._table.item(r, c).text()
                        if self._table.item(r, c) else "")
                       for c in range(len(headers))]
            from PyQt6.QtWidgets import QApplication as _QApp
            _QApp.clipboard().setText(",".join(headers) + "\n" + ",".join(values))

        install_copy_menu(self._table, [
            ("separator",    None),
            ("Copy metric",  _trend_copy_metric),
            ("separator",    None),
            ("Export row",   _trend_export_row),
        ])

        bl.addWidget(self._table)

        note = QLabel(
            "R² < 0.5 = noisy data / no clear trend.  "
            "ETA shown only when the trend is rising toward the threshold within 30 days."
        )
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        return card

    # ── Analysis runner ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_analysis(self):
        if self._worker and self._worker.isRunning():
            return
        if self._store is None:
            self._status_lbl.setText("No data store connected.")
            return
        self._btn_run.setEnabled(False)
        self._btn_run.setText("⏳ Analysing…")
        hours = self._window_combo.currentData()
        self._worker = _TrendWorker(self._store, window_hours=hours, parent=None)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(object)
    def _on_result(self, report: TrendReport):
        self._trend_stack.setCurrentIndex(1)
        self._last_report = report
        self.report_ready.emit(report)
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶  Run Analysis")
        self._populate_table(report)
        self._update_kpis(report)
        self._update_rtt_headline()
        self._btn_log_hub.setVisible(False)
        hosts = len({r.host for r in report.results})
        ts_str = time.strftime("%H:%M:%S", time.localtime(report.ts))
        self._status_lbl.setText(
            f"Last run: {ts_str} — {hosts} host(s), {len(report.results)} metric(s) analysed"
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._update_rtt_headline()

    def _update_rtt_headline(self) -> None:
        """RECUR-4: compute this-week vs last-week RTT average and update headline label.

        G11: single SQL aggregate (query_rtt_weekly_avg()) instead of a
        per-host 14-day raw-row scan — this used to pull every RTT sample in
        the window into Python on every showEvent, on the main thread.
        """
        if self._store is None:
            return
        try:
            result = self._store.query_rtt_weekly_avg()
        except Exception:
            return
        if not result:
            self._headline_lbl.setVisible(False)
            return

        this_avg = result["this_avg"]
        last_avg = result["last_avg"]

        if last_avg is not None:
            delta = this_avg - last_avg
            if delta > 5:
                arrow, color_name = "↑", "AMBER" if delta < 20 else "RED"
            elif delta < -5:
                arrow, color_name = "↓", "GREEN"
            else:
                arrow, color_name = "→", "GREEN"
            diff_str = f" ({arrow} {abs(delta):.0f}ms vs. last week)"
        else:
            color_name = "GREEN" if this_avg < 50 else "AMBER" if this_avg < 150 else "RED"
            diff_str = " (no prior week data)"

        self._headline_lbl.setText(
            f"RTT this week: {this_avg:.0f}ms avg{diff_str}"
        )
        _s.themed_ss(self._headline_lbl, lambda cn=color_name: (
            f"font-size:13px; font-weight:bold; color:{getattr(_s, cn)};"
            f" background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-radius:4px; padding:8px 14px;"
        ))
        self._headline_lbl.setVisible(True)

    @pyqtSlot(str)
    def _on_error(self, err: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶  Run Analysis")
        self._status_lbl.setText(f"Analysis error: {err}")

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_table(self, report: TrendReport):
        from PyQt6.QtGui import QColor
        self._table.setRowCount(0)
        for r in report.results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            sev_color = _sev_color(r.severity)

            unit = {"rtt_ms": "ms", "loss_pct": "%", "jitter_ms": "ms"}.get(r.metric, "")
            trend_str = f"+{r.slope_per_hour:.3f}" if r.slope_per_hour >= 0 else f"{r.slope_per_hour:.3f}"

            if r.eta_hours is None:
                eta_str = "—"
            elif r.eta_hours < 1:
                eta_str = f"<1 h"
            elif r.eta_hours < 48:
                eta_str = f"{r.eta_hours:.1f} h"
            else:
                eta_str = f"{r.eta_hours/24:.1f} d"

            for col, val in enumerate([
                r.host,
                _METRIC_LABEL.get(r.metric, r.metric),
                f"{r.current_value:.1f}{unit}",
                f"{trend_str}{unit}/h",
                f"{r.threshold:.0f}{unit}",
                eta_str,
                r.severity,
            ]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 6:
                    item.setForeground(QColor(sev_color))
                    item.setFont(__import__("PyQt6.QtGui", fromlist=["QFont"]).QFont(
                        "Segoe UI", 9, __import__("PyQt6.QtGui", fromlist=["QFont"]).QFont.Weight.Bold
                    ))
                self._table.setItem(row, col, item)

            # Colour ETA cell by severity
            if r.eta_hours is not None and r.severity in ("CRITICAL", "WARNING"):
                eta_item = self._table.item(row, 5)
                if eta_item:
                    eta_item.setForeground(QColor(sev_color))

            # VIZ-3: sparkline widget in col 7
            if r.points:
                spark_color_name = "GREEN" if r.direction in ("STABLE", "FALLING") else "RED"
                sparkline = _MiniSparkline(r.points, spark_color_name)
                self._table.setCellWidget(row, 7, sparkline)
            else:
                self._table.setItem(row, 7, QTableWidgetItem("—"))

    def _update_kpis(self, report: TrendReport):
        hosts = len({r.host for r in report.results})
        crit  = len(report.critical)
        warn  = len(report.warnings)
        clean = len([r for r in report.results if r.severity == "CLEAN"])
        self._kpi_hosts_lbl.set_value(hosts)
        self._kpi_critical_lbl.set_value(crit)
        self._kpi_warnings_lbl.set_value(warn)
        self._kpi_clean_lbl.set_value(clean)
        _s.themed_ss(self._kpi_critical_lbl, lambda has=bool(crit): (
            f"font-size:22px; font-weight:700; color:{_s.RED if has else _s.TEXT_SECONDARY};"
            " border:none; background:transparent;"
        ))
        _s.themed_ss(self._kpi_warnings_lbl, lambda has=bool(warn): (
            f"font-size:22px; font-weight:700; color:{_s.AMBER if has else _s.TEXT_SECONDARY};"
            " border:none; background:transparent;"
        ))

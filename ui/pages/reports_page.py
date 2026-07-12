"""
ReportsPage — UI for scheduled auto-report generation (T2#9).

Shows:
  • Schedule configuration (interval, output directory, enable/disable)
  • "Generate Now" button
  • Recent reports list (last N)

Conforms to the NetSentinel enterprise UI design system:
  • Light content area (BG_DARK)
  • Cards with WHITE background, 1px BORDER border, 0px radius
  • Table header TH_BG / white, 11px rows, zebra striping
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore    import Qt, QUrl, pyqtSlot
from PyQt6.QtGui     import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSizePolicy, QSpinBox,
    QVBoxLayout, QWidget, QCheckBox,
)

from modules.metric_store      import MetricStore
from ui import styles as _s
from ui.styles                 import (
    ACCENT, BG_CARD, BG_DARK, BG_HOVER,
    BORDER, CARD_HDR_BORDER, CARD_RADIUS,
    INPUT_PLACEHOLDER,
    TABLE_ROW_BORDER, TABLE_SEL, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    """Return a card container + its body layout."""
    outer = QWidget()
    outer.setStyleSheet(
        f"QWidget {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
    )
    outer_lay = QVBoxLayout(outer)
    outer_lay.setContentsMargins(0, 0, 0, 0)
    outer_lay.setSpacing(0)

    # Title bar
    title_bar = QLabel(title)
    title_bar.setStyleSheet(
        f"QLabel {{ background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER};"
        f" padding:4px 12px; font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; }}"
    )
    outer_lay.addWidget(title_bar)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD}; border:none;")
    body_lay = QVBoxLayout(body)
    body_lay.setContentsMargins(12, 10, 12, 10)
    body_lay.setSpacing(8)
    outer_lay.addWidget(body)

    return outer, body_lay


def _kpi_tile(label: str, value: str = "—") -> tuple[QWidget, QLabel]:
    tile = QWidget()
    tile.setStyleSheet(
        f"QWidget {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {ACCENT}; padding:4px 8px; }}"
    )
    tile.setMinimumWidth(120)
    tile.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(6, 4, 6, 4)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── Page ──────────────────────────────────────────────────────────────────────

class ReportsPage(QWidget):
    """
    Auto-report schedule configuration and history viewer.
    Receives the ReportSchedulerWorker reference from app.py after the
    page is registered in the dashboard.
    """

    def __init__(self, store: MetricStore, report_worker=None, parent=None):
        super().__init__(parent)
        self._store  = store
        self._worker = report_worker   # may be set later via set_worker()
        self._error_count = 0
        self._setup_ui()

    def set_worker(self, worker) -> None:
        """Inject the worker after construction (called from app.py)."""
        self._worker = worker

    # ── UI ────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QWidget#ReportsPage {{ background:{BG_DARK}; }}")
        self.setObjectName("ReportsPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Page title
        from ui.widgets.page_header import PageHeaderBar
        _hdr = PageHeaderBar("Auto-Report Generation", subtitle="Automatically generates and emails network health reports on a schedule.")
        _hdr.show_first_visit_banner(
            "auto_report",
            "Set a schedule once and a formatted health report — grade, devices, alerts — "
            "is generated and optionally emailed without you needing to open the app.",
        )
        root.addWidget(_hdr)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        tile_total,  self._kpi_total   = _kpi_tile("Reports Generated", "0")
        tile_errors, self._kpi_errors  = _kpi_tile("Errors", "0")
        tile_last,   self._kpi_last    = _kpi_tile("Last Report", "—")
        kpi_row.addWidget(tile_total)
        kpi_row.addWidget(tile_errors)
        kpi_row.addWidget(tile_last)
        kpi_row.addStretch()
        root.addLayout(kpi_row)

        # ── Sparkline preview chart (POLISH-14) ───────────────────────────────
        preview_card, preview_lay = _card("Network Health — Last 7 Days")
        self._preview_fig = Figure(facecolor=_s.CHART_BG, figsize=(6, 1.4), dpi=96)
        self._preview_ax = self._preview_fig.add_subplot(111)
        self._preview_fig.set_tight_layout({"pad": 0.4})  # applied once; avoids per-redraw accumulation
        self._preview_canvas = FigureCanvas(self._preview_fig)
        _s.themed_ss(self._preview_canvas, "background:{CHART_BG}; border:none;")
        self._preview_canvas.setFixedHeight(140)
        self._preview_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preview_lay.addWidget(self._preview_canvas)
        self._preview_status = QLabel("Loading…")
        self._preview_status.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
        )
        self._preview_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_lay.addWidget(self._preview_status)
        root.addWidget(preview_card)
        self._load_preview_chart()

        # Schedule config card
        cfg_card, cfg_lay = _card("Schedule Configuration")

        # Enable checkbox
        self._chk_enabled = QCheckBox("Enable automatic report generation")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        cfg_lay.addWidget(self._chk_enabled)

        # Interval row
        int_row = QHBoxLayout()
        int_row.setSpacing(8)
        int_lbl = QLabel("Generate every")
        int_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._spin_hours = QSpinBox()
        self._spin_hours.setRange(1, 8760)
        self._spin_hours.setValue(24)
        self._spin_hours.setFixedWidth(70)
        self._spin_hours.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        int_row.addWidget(int_lbl)
        int_row.addWidget(self._spin_hours)
        int_row.addWidget(QLabel("hours"))
        int_row.addStretch()
        cfg_lay.addLayout(int_row)

        # Output dir row
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_lbl = QLabel("Output directory")
        dir_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._txt_dir = QLineEdit(str(Path.home() / "NetSentinel-Reports"))
        self._txt_dir.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;"
        )
        self._btn_browse = QPushButton("Browse…")
        self._btn_browse.setFixedHeight(26)
        self._btn_browse.setStyleSheet(
            f"font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            f" background:{BG_CARD}; padding:0 10px;"
        )
        self._btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(dir_lbl)
        dir_row.addWidget(self._txt_dir, 1)
        dir_row.addWidget(self._btn_browse)
        cfg_lay.addLayout(dir_row)

        # Apply + Generate Now
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_apply = QPushButton("Apply Settings")
        self._btn_apply.setFixedHeight(34)
        self._btn_apply.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{WHITE}; background:{ACCENT};"
            f" border:none; padding:0 18px; border-radius:4px;"
        )
        self._btn_apply.clicked.connect(self._apply_settings)
        self._btn_now = QPushButton("Generate Now")
        self._btn_now.setFixedHeight(34)
        self._btn_now.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{ACCENT}; background:{BG_CARD};"
            f" border:1px solid {ACCENT}; padding:0 18px; border-radius:4px;"
        )
        self._btn_now.clicked.connect(self._generate_now)
        self._btn_pdf = QPushButton("Export PDF")
        self._btn_pdf.setFixedHeight(34)
        self._btn_pdf.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{ACCENT}; background:{BG_CARD};"
            f" border:1px solid {ACCENT}; padding:0 18px; border-radius:4px;"
        )
        self._btn_pdf.clicked.connect(self._export_pdf)
        self._btn_copy = QPushButton("Copy Summary")
        self._btn_copy.setFixedHeight(34)
        self._btn_copy.setStyleSheet(
            f"font-size:12px; color:{TEXT_SECONDARY}; background:transparent;"
            f" border:1px solid {BORDER}; padding:0 14px; border-radius:4px;"
        )
        self._btn_copy.clicked.connect(self._copy_summary)
        self._btn_open_folder = QPushButton("Open Folder ›")
        self._btn_open_folder.setFixedHeight(34)
        self._btn_open_folder.setStyleSheet(
            f"font-size:12px; color:{TEXT_SECONDARY}; background:transparent;"
            f" border:1px solid {BORDER}; padding:0 14px; border-radius:4px;"
        )
        self._btn_open_folder.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(self._btn_now)
        btn_row.addWidget(self._btn_pdf)
        btn_row.addWidget(self._btn_copy)
        btn_row.addWidget(self._btn_open_folder)
        btn_row.addStretch()
        cfg_lay.addLayout(btn_row)

        root.addWidget(cfg_card)

        # Recent reports card
        hist_card, hist_lay = _card("Recent Reports")
        self._report_list = QListWidget()
        self._report_list.setStyleSheet(
            f"QListWidget {{ font-size:11px; color:{TEXT_PRIMARY}; border:none;"
            f" background:{BG_CARD}; }}"
            f"QListWidget::item {{ padding:4px 8px; border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
            f"QListWidget::item:hover {{ background:{BG_HOVER}; }}"
            f"QListWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        )
        self._report_list.setFixedHeight(220)
        self._report_list.itemDoubleClicked.connect(self._open_report)
        hist_lay.addWidget(self._report_list)
        self._lbl_empty = QLabel("No reports generated yet. Click \"Generate Now\" to create one.")
        self._lbl_empty.setStyleSheet(f"font-size:11px; color:{INPUT_PLACEHOLDER}; padding:8px;")
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hist_lay.addWidget(self._lbl_empty)
        root.addWidget(hist_card)

        root.addStretch()
        self._sync_list_visibility()

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def on_report_saved(self, path: str) -> None:
        """Called when the worker emits report_saved(path)."""
        self._btn_now.setEnabled(True)
        self._btn_now.setText("Generate Now")
        item = QListWidgetItem(path)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setForeground(Qt.GlobalColor.darkGreen if Path(path).exists() else Qt.GlobalColor.gray)
        self._report_list.insertItem(0, item)
        # Update KPI
        count = int(self._kpi_total.text()) + 1 if self._kpi_total.text().isdigit() else 1
        self._kpi_total.setText(str(count))
        ts = Path(path).stem.replace("netsentinel-report-", "")
        self._kpi_last.setText(ts.replace("_", " ") if ts else "now")
        self._sync_list_visibility()

    @pyqtSlot(str)
    def on_worker_error(self, msg: str) -> None:
        self._error_count += 1
        self._kpi_errors.setText(str(self._error_count))

    # ── Preview chart (POLISH-14) ─────────────────────────────────────────────

    def refresh_theme(self) -> None:
        """Live theme switch: re-read the figure facecolor and re-render the
        sparkline preview (canvas background re-applies via themed_ss)."""
        self._preview_fig.set_facecolor(_s.CHART_BG)
        self._load_preview_chart()

    def _load_preview_chart(self) -> None:
        """Render sparklines for device count and grade over the last 7 days."""
        ax = self._preview_ax
        ax.cla()
        ax.set_facecolor(_s.CHART_PLOT_BG)
        self._preview_fig.set_facecolor(_s.CHART_BG)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(_s.CHART_GRID)
        ax.spines["left"].set_color(_s.CHART_GRID)
        ax.tick_params(colors=_s.TEXT_MUTED, labelsize=8)
        ax.grid(True, color=_s.CHART_GRID, linewidth=0.6, linestyle="-")

        try:
            device_dates, device_counts, grade_dates, grade_scores = (
                self._query_preview_data()
            )
        except Exception:
            device_dates = device_counts = grade_dates = grade_scores = []

        if len(device_counts) >= 2 or len(grade_scores) >= 2:
            if len(device_counts) >= 2:
                ax.plot(device_dates, device_counts, color=_s.ACCENT,
                        linewidth=1.5, label="Devices", marker="o", markersize=3)
            if len(grade_scores) >= 2:
                ax2 = ax.twinx()
                ax2.set_facecolor(_s.CHART_PLOT_BG)
                ax2.spines["top"].set_visible(False)
                ax2.spines["right"].set_color(_s.CHART_GRID)
                ax2.tick_params(colors=_s.TEXT_MUTED, labelsize=8)
                ax2.plot(grade_dates, grade_scores, color=_s.GREEN,
                         linewidth=1.5, label="Grade", marker="s", markersize=3)
                ax2.set_ylim(0, 100)
                ax2.set_ylabel("Grade", color=_s.GREEN, fontsize=8)
            ax.set_ylabel("Devices", color=_s.ACCENT, fontsize=8)
            self._preview_status.setVisible(False)
        else:
            ax.text(0.5, 0.5, "No data yet — run a scan to populate.",
                    ha="center", va="center", transform=ax.transAxes,
                    color=_s.TEXT_MUTED, fontsize=9)
            self._preview_status.setVisible(False)

        self._preview_canvas.draw()

    def _query_preview_data(self):
        """Query MetricStore for device counts and grades over 7 days."""
        import datetime as _dt
        device_dates, device_counts = [], []
        grade_dates, grade_scores = [], []
        if self._store is None:
            return device_dates, device_counts, grade_dates, grade_scores
        try:
            cutoff = _dt.datetime.now() - _dt.timedelta(days=7)
            rows = self._store.query_scan_history(since_ts=cutoff.timestamp())
            for row in rows:
                ts = row.get("ts") or row.get("timestamp")
                if ts:
                    dt = _dt.datetime.fromtimestamp(float(ts))
                    cnt = row.get("device_count") or row.get("devices")
                    if cnt is not None:
                        device_dates.append(dt)
                        device_counts.append(int(cnt))
                    grade = row.get("grade_score") or row.get("grade")
                    if grade is not None:
                        grade_dates.append(dt)
                        grade_scores.append(float(grade))
        except Exception:
            pass  # non-fatal
        return device_dates, device_counts, grade_dates, grade_scores

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select output directory", self._txt_dir.text(),
            options=QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontUseNativeDialog,
        )
        if d:
            self._txt_dir.setText(d)

    def _apply_settings(self) -> None:
        if not self._worker:
            return
        from modules.report_scheduler import ReportConfig
        config = ReportConfig(
            output_dir     = Path(self._txt_dir.text()),
            interval_hours = float(self._spin_hours.value()),
            enabled        = self._chk_enabled.isChecked(),
        )
        self._worker.set_config(config)

    def _generate_now(self) -> None:
        self._btn_now.setEnabled(False)
        self._btn_now.setText("Generating…")
        if not self._worker:
            # No worker yet — generate inline (e.g., during smoke test)
            try:
                from modules.report_scheduler import ReportConfig, ReportScheduler
                config = ReportConfig(
                    output_dir     = Path(self._txt_dir.text()),
                    interval_hours = float(self._spin_hours.value()),
                    enabled        = True,
                )
                sched = ReportScheduler(store=self._store, config=config,
                                        on_saved=lambda p: self.on_report_saved(str(p)))
                sched.generate_now()
            except Exception:
                pass  # non-fatal
            self._btn_now.setEnabled(True)
            self._btn_now.setText("Generate Now")
            return
        self._worker.trigger_now()

    def _open_report(self, item: QListWidgetItem) -> None:
        import subprocess, sys
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).exists():
            if sys.platform == "win32":
                import os
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

    def _open_output_folder(self) -> None:
        folder = Path(self._txt_dir.text())
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _export_pdf(self) -> None:
        """Generate a PDF report and prompt the user where to save it."""
        default_name = "netsentinel-report.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", str(Path.home() / default_name),
            "PDF Files (*.pdf)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return

        self._btn_pdf.setEnabled(False)
        self._btn_pdf.setText("Generating…")
        self._btn_pdf.repaint()
        try:
            from modules.report_exporter import save_pdf_report
            save_pdf_report(Path(path))
            QMessageBox.information(
                self, "PDF Exported",
                f"Report saved to:\n{path}"
            )
            # Also add to the recent list
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._report_list.insertItem(0, item)
            self._sync_list_visibility()
        except RuntimeError as exc:
            QMessageBox.warning(self, "PDF Export Failed", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "PDF Export Error", f"Unexpected error: {exc}")
        finally:
            self._btn_pdf.setEnabled(True)
            self._btn_pdf.setText("Export PDF")

    def _copy_summary(self) -> None:
        try:
            from modules.report_scheduler import generate_status_report
            text = generate_status_report(self._store)
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(text)
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast("Network summary copied to clipboard", "info")
        except Exception as exc:
            QMessageBox.warning(self, "Copy Failed", str(exc))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sync_list_visibility(self) -> None:
        has_items = self._report_list.count() > 0
        self._report_list.setVisible(has_items)
        self._lbl_empty.setVisible(not has_items)

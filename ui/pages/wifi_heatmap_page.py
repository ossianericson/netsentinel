"""
WiFi Signal Strength Heatmap Page.

Layout
──────
  Toolbar: Import Floor Plan | New Survey | Load Survey | Save Survey |
           [AP selector] | Render Heatmap | Clear Samples | Export PNG

  Main splitter:
    Left (320px): survey controls + sample list
    Right:        matplotlib canvas (floor plan + heatmap overlay + sample dots)

Workflow
────────
  1. Import a PNG/JPG floor plan.
  2. "Add Sample" or click directly on the canvas while in sampling mode.
     The page fires a WiFi scan (QThread).  When complete the crosshair
     cursor is shown and the user clicks their position on the floor plan.
  3. After ≥ 3 samples, "Render Heatmap" draws the IDW-interpolated overlay.
  4. Save survey for later; Export PNG saves the rendered figure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.wifi_heatmap import (
    HEATMAP_VMAX,
    HEATMAP_VMIN,
    HeatmapSurvey,
    dbm_to_quality,
    interpolate_heatmap,
    list_surveys,
    load_survey,
    save_survey,
    surveys_dir,
)
from modules.wifi_scanner import scan as wifi_scan
from ui import styles as _s
from ui.styles import (
    ACCENT, ACCENT_DARK,
    BG_CARD, BG_HOVER, BORDER,
    CARD_HDR_BORDER, CARD_RADIUS, INPUT_PLACEHOLDER, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)
from ui.tabs_helpers import _table
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard


# ── Worker ────────────────────────────────────────────────────────────────────

class _ScanWorker(QThread):
    """Runs wifi_scanner.scan() off the main thread."""
    result_ready = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            result = wifi_scan()
            self.result_ready.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    """Return (card_widget, inner_layout) following RULE 5."""
    card = QWidget()
    card.setObjectName("heatmapCard")
    card.setStyleSheet(
        f"QWidget#heatmapCard {{"
        f"  background:{BG_CARD};"
        f"  border:1px solid {BORDER};"
        f"  border-radius:{CARD_RADIUS};"
        f"}}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    header = QLabel(title)
    header.setFixedHeight(32)
    header.setStyleSheet(
        f"background:{BG_CARD}; color:{TEXT_PRIMARY};"
        f"font-weight:600; font-size:11px;"
        f"padding:0 12px;"
        f"border-bottom:1px solid {CARD_HDR_BORDER};"
    )
    outer.addWidget(header)

    inner_w = QWidget()
    inner_w.setStyleSheet(f"background:{BG_CARD};")
    inner = QVBoxLayout(inner_w)
    inner.setContentsMargins(8, 8, 8, 8)
    inner.setSpacing(6)
    outer.addWidget(inner_w)
    return card, inner


def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f"  border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ background:{INPUT_PLACEHOLDER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    return b


# ── Main page ─────────────────────────────────────────────────────────────────

class WifiHeatmapPage(QWidget):
    """Interactive WiFi signal-strength heatmap on a user-supplied floor plan."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._survey: Optional[HeatmapSurvey] = None
        self._scan_worker: Optional[_ScanWorker] = None
        self._pending_pos: Optional[tuple[float, float]] = None
        self._sampling_mode: bool = False   # True = next canvas click records a sample
        self._floor_plan_img: Optional[np.ndarray] = None
        self._overlay_active: bool = False   # True once a heatmap layer is rendered
        self._cid: Optional[int] = None     # matplotlib button_press connection id

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Page title
        title = QLabel("WiFi Signal Heatmap")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        sub = QLabel(
            "Import a floor plan, walk around clicking your position after each scan "
            "to build a coverage map, then render the heatmap."
        )
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        # Toolbar row (always visible — has Import / Load buttons)
        root.addWidget(self._build_toolbar())

        # Main stack: index 0 = empty state, index 1 = survey content
        self._main_stack = QStackedWidget()

        empty = EmptyStateCard(
            icon="⬡",
            title="No floor plan loaded",
            what_it_shows="Interactive WiFi signal-strength heatmap overlaid on your floor plan.",
            why_it_matters="Walk around with the app open to map signal coverage across every room.",
            btn_label="Import Floor Plan",
        )
        empty.clicked.connect(self._on_import_floor_plan)
        self._main_stack.addWidget(empty)

        # Content widget: status bar + splitter
        content_w = QWidget()
        content_lay = QVBoxLayout(content_w)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(4)

        self._status_label = QLabel("No survey active.  Import a floor plan to begin.")
        self._status_label.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; padding:2px 0;"
        )
        content_lay.addWidget(self._status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_canvas_panel())
        splitter.setSizes([300, 800])
        content_lay.addWidget(splitter, 1)

        self._main_stack.addWidget(content_w)
        self._main_stack.setCurrentIndex(0)
        root.addWidget(self._main_stack, 1)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background:{BG_CARD}; border:1px solid {BORDER};"
                          f"border-radius:{CARD_RADIUS};")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._btn_import   = _btn("⬡  Import Floor Plan")
        self._btn_new      = _btn("✚  New Survey")
        self._btn_load     = _btn("▶  Load Survey")
        self._btn_save     = _btn("⊟  Save Survey")
        self._btn_add      = _btn("●  Add Sample", accent=True)
        self._btn_render   = _btn("◆  Render Heatmap", accent=True)
        self._btn_clear    = _btn("✕  Clear Samples")
        self._btn_export   = _btn("↓  Export PNG")

        self._ap_combo = QComboBox()
        self._ap_combo.setFixedWidth(220)
        self._ap_combo.setFixedHeight(26)
        self._ap_combo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f"  border-radius:3px; padding:0 6px; font-size:10px; }}"
        )
        self._ap_combo.addItem("All APs (average)", userData=None)

        self._btn_import.clicked.connect(self._on_import_floor_plan)
        self._btn_new.clicked.connect(self._on_new_survey)
        self._btn_load.clicked.connect(self._on_load_survey)
        self._btn_save.clicked.connect(self._on_save_survey)
        self._btn_add.clicked.connect(self._on_add_sample)
        self._btn_render.clicked.connect(self._on_render_heatmap)
        self._btn_clear.clicked.connect(self._on_clear_samples)
        self._btn_export.clicked.connect(self._on_export_png)

        for w in (self._btn_import, self._btn_new, self._btn_load, self._btn_save):
            layout.addWidget(w)
        layout.addStretch()
        layout.addWidget(QLabel("AP:"))
        layout.addWidget(self._ap_combo)
        layout.addWidget(self._btn_add)
        layout.addWidget(self._btn_render)
        layout.addWidget(self._btn_clear)
        layout.addWidget(self._btn_export)

        self._set_buttons_enabled(False)
        self._btn_import.setEnabled(True)
        self._btn_new.setEnabled(True)
        self._btn_load.setEnabled(True)
        return bar

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(260)
        panel.setMaximumWidth(360)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(6)

        # Survey info card
        info_card, info_layout = _card("Survey")
        self._survey_name_lbl = QLabel("—")
        self._survey_name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-weight:600;")
        self._fp_lbl = QLabel("No floor plan imported.")
        self._fp_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        self._fp_lbl.setWordWrap(True)
        self._sample_count_lbl = QLabel("0 samples")
        self._sample_count_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")
        info_layout.addWidget(self._survey_name_lbl)
        info_layout.addWidget(self._fp_lbl)
        info_layout.addWidget(self._sample_count_lbl)
        lay.addWidget(info_card)

        # Samples table card
        samp_card, samp_layout = _card("Samples  (click a row to highlight on map)")
        self._sample_table = _table(["#", "dBm (avg)", "Quality", "APs seen"])
        # Interactive, not ResizeToContents (RULE-PERF1) — see threat_intel_page.py
        self._sample_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self._sample_table.horizontalHeader().setStretchLastSection(True)
        self._sample_table.setMinimumHeight(200)
        self._sample_table.itemSelectionChanged.connect(self._on_sample_selected)
        install_copy_menu(self._sample_table)
        samp_layout.addWidget(self._sample_table)

        # Delete selected sample button
        del_btn = _btn("✕  Delete Selected Sample")
        del_btn.clicked.connect(self._on_delete_sample)
        samp_layout.addWidget(del_btn)
        lay.addWidget(samp_card, 1)

        # Coverage summary card
        cov_card, cov_layout = _card("Coverage Stats")
        self._cov_table = _table(["SSID / BSSID", "Best dBm", "Quality"])
        self._cov_table.setFixedHeight(120)

        def _heat_copy_bssid():
            r = self._cov_table.currentRow()
            if r >= 0:
                it = self._cov_table.item(r, 0)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        install_copy_menu(self._cov_table, [
            ("separator",  None),
            ("Copy BSSID", _heat_copy_bssid),
        ])
        cov_layout.addWidget(self._cov_table)
        lay.addWidget(cov_card)

        return panel

    def _build_canvas_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(0)

        self._fig = Figure(facecolor=_s.BG_CARD, dpi=96)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        _s.themed_ss(self._canvas, "background:{BG_CARD}; border:none;")
        lay.addWidget(self._canvas)

        self._cid = self._canvas.mpl_connect(
            "button_press_event", self._on_canvas_click)
        self._reset_canvas()
        return panel

    # ── Canvas helpers ────────────────────────────────────────────────────────

    def refresh_theme(self) -> None:
        """Live theme switch: re-read the figure facecolor and redraw the floor
        plan (canvas background re-applies via the themed_ss registry)."""
        self._fig.set_facecolor(_s.BG_CARD)
        if self._floor_plan_img is None:
            self._reset_canvas()
        else:
            self._redraw_floor_plan(overlay=self._overlay_active)

    def _reset_canvas(self) -> None:
        self._ax.cla()
        self._ax.set_facecolor(_s.CHART_PLOT_BG)
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._ax.spines["top"].set_visible(False)
        self._ax.spines["right"].set_visible(False)
        self._ax.spines["bottom"].set_color(_s.CHART_SPINE)
        self._ax.spines["left"].set_color(_s.CHART_SPINE)
        self._ax.text(0.5, 0.5,
                      "Import a floor plan to begin.\n"
                      "Then walk around and click your position\n"
                      "after each scan.",
                      ha="center", va="center",
                      color=_s.TEXT_MUTED, fontsize=11,
                      transform=self._ax.transAxes)
        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        self._canvas.draw()

    def _redraw_floor_plan(self, overlay: bool = False) -> None:
        """Redraw the floor plan image, sample dots, and optionally the heatmap."""
        self._ax.cla()
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        for sp in self._ax.spines.values():
            sp.set_visible(False)

        if self._floor_plan_img is None:
            self._reset_canvas()
            return

        h, w = self._floor_plan_img.shape[:2]
        self._ax.imshow(
            self._floor_plan_img,
            extent=[0, 1, 1, 0],    # (left, right, bottom, top) in data coords
            aspect="auto",
            zorder=0,
        )

        if overlay and self._survey and len(self._survey.readings) >= 3:
            self._draw_heatmap_layer()

        if self._survey:
            self._draw_sample_dots()

        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        self._canvas.draw()

    def _draw_heatmap_layer(self) -> None:
        bssid = self._ap_combo.currentData()
        gx, gy, zz = interpolate_heatmap(
            self._survey.readings, bssid, resolution=100)

        # Mask extremely low / no-signal areas
        zz_masked = np.ma.masked_where(zz < HEATMAP_VMIN - 5, zz)

        self._ax.pcolormesh(
            gx, gy, zz_masked,
            cmap="RdYlGn",
            vmin=HEATMAP_VMIN,
            vmax=HEATMAP_VMAX,
            alpha=0.45,
            shading="auto",
            zorder=1,
        )

    def _draw_sample_dots(self) -> None:
        selected_rows = {i.row() for i in self._sample_table.selectedIndexes()}
        for idx, r in enumerate(self._survey.readings):
            if not r.readings:
                continue
            avg_dbm = float(np.mean(list(r.readings.values())))
            color = _dbm_color(avg_dbm)
            size = 120 if idx in selected_rows else 70
            edgecolor = _s.TEXT_PRIMARY if idx in selected_rows else "none"
            self._ax.scatter(
                r.x_frac, r.y_frac,
                s=size, c=color, zorder=3,
                edgecolors=edgecolor, linewidths=1.5,
            )
            self._ax.text(
                r.x_frac + 0.012, r.y_frac - 0.012,
                f"{avg_dbm:.0f}",
                fontsize=7, color=_s.TEXT_PRIMARY, zorder=4,
            )

    # ── Button handlers ───────────────────────────────────────────────────────

    def _on_import_floor_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Floor Plan",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            from matplotlib.image import imread
            img = imread(path)
            if img.dtype != np.uint8:
                if img.max() <= 1.0:
                    img = (img * 255).astype(np.uint8)
            self._floor_plan_img = img
        except Exception as exc:
            self._set_status(f"Could not load image: {exc}", error=True)
            return

        if self._survey is None:
            self._survey = HeatmapSurvey(
                name=Path(path).stem,
                floor_plan_path=path,
            )
            self._survey_name_lbl.setText(self._survey.name)

        self._survey.floor_plan_path = path
        self._fp_lbl.setText(Path(path).name)
        self._set_buttons_enabled(True)
        self._main_stack.setCurrentIndex(1)
        self._redraw_floor_plan()
        self._set_status("Floor plan loaded. Click '● Add Sample' or click directly on the map.")

    def _on_new_survey(self) -> None:
        self._survey = HeatmapSurvey(name="New Survey", floor_plan_path="")
        self._floor_plan_img = None
        self._sampling_mode = False
        self._refresh_sample_table()
        self._refresh_ap_combo()
        self._survey_name_lbl.setText(self._survey.name)
        self._fp_lbl.setText("No floor plan imported.")
        self._sample_count_lbl.setText("0 samples")
        self._set_buttons_enabled(False)
        self._btn_import.setEnabled(True)
        self._btn_new.setEnabled(True)
        self._btn_load.setEnabled(True)
        self._reset_canvas()
        self._main_stack.setCurrentIndex(0)
        self._set_status("New survey created. Import a floor plan to begin.")

    def _on_load_survey(self) -> None:
        surveys = list_surveys()
        if not surveys:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Survey", str(surveys_dir()), "JSON (*.json)",
                options=QFileDialog.Option.DontUseNativeDialog,
            )
            if not path:
                return
            surveys = [Path(path)]

        # If multiple files, pick via dialog
        if len(surveys) == 1:
            chosen = surveys[0]
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "Load Survey", str(surveys_dir()), "JSON (*.json)",
                options=QFileDialog.Option.DontUseNativeDialog,
            )
            if not path:
                return
            chosen = Path(path)

        try:
            self._survey = load_survey(chosen)
        except Exception as exc:
            self._set_status(f"Load failed: {exc}", error=True)
            return

        fp = Path(self._survey.floor_plan_path)
        if fp.exists():
            try:
                from matplotlib.image import imread
                img = imread(str(fp))
                if img.dtype != np.uint8:
                    if img.max() <= 1.0:
                        img = (img * 255).astype(np.uint8)
                self._floor_plan_img = img
            except Exception:
                self._floor_plan_img = None
        else:
            self._floor_plan_img = None

        self._survey_name_lbl.setText(self._survey.name)
        self._fp_lbl.setText(fp.name if self._survey.floor_plan_path else "Floor plan not found.")
        self._refresh_sample_table()
        self._refresh_ap_combo()
        self._set_buttons_enabled(bool(self._floor_plan_img))
        self._btn_import.setEnabled(True)
        self._btn_new.setEnabled(True)
        self._btn_load.setEnabled(True)
        self._btn_save.setEnabled(True)
        if self._floor_plan_img is not None:
            self._main_stack.setCurrentIndex(1)
        self._redraw_floor_plan()
        self._set_status(f"Loaded '{self._survey.name}' ({len(self._survey.readings)} samples).")

    def _on_save_survey(self) -> None:
        if not self._survey:
            return
        try:
            path = save_survey(self._survey)
            self._set_status(f"Survey saved to {path.name}")
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", error=True)

    def _on_add_sample(self) -> None:
        """Activate sampling mode: show instructions, wait for canvas click."""
        if not self._survey:
            return
        if self._scan_worker and self._scan_worker.isRunning():
            return
        self._sampling_mode = True
        self._btn_add.setText("● Scanning…")
        self._btn_add.setEnabled(False)
        self._set_status("Scanning WiFi… please wait.")
        self._scan_worker = _ScanWorker()
        self._scan_worker.result_ready.connect(self._on_scan_complete)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    @pyqtSlot(object)
    def _on_scan_complete(self, result) -> None:
        self._pending_scan_result = result
        self._btn_add.setText("● Add Sample")
        self._btn_add.setEnabled(True)
        n = len(result.networks)
        self._set_status(
            f"Scan found {n} AP{'s' if n != 1 else ''}.  "
            "Click on the floor plan to mark your position."
        )
        self._canvas.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    @pyqtSlot(str)
    def _on_scan_error(self, msg: str) -> None:
        self._sampling_mode = False
        self._btn_add.setText("● Add Sample")
        self._btn_add.setEnabled(True)
        self._set_status(f"WiFi scan failed: {msg}", error=True)
        self._canvas.unsetCursor()

    def _on_canvas_click(self, event) -> None:
        if event.inaxes != self._ax:
            return
        if event.button != 1:
            return
        if not self._sampling_mode:
            return
        if not hasattr(self, "_pending_scan_result"):
            return
        if not self._survey:
            return

        x = float(np.clip(event.xdata, 0.0, 1.0))
        y = float(np.clip(event.ydata, 0.0, 1.0))
        self._survey.add_reading(x, y, self._pending_scan_result)
        del self._pending_scan_result

        self._sampling_mode = False
        self._canvas.unsetCursor()
        self._refresh_sample_table()
        self._refresh_ap_combo()
        self._redraw_floor_plan()
        n = len(self._survey.readings)
        self._sample_count_lbl.setText(f"{n} sample{'s' if n != 1 else ''}")
        self._set_status(
            f"Sample recorded.  {n} total.  "
            + ("Click '◆ Render Heatmap' when ready." if n >= 3
               else f"Need {3 - n} more to render.")
        )

    def _on_render_heatmap(self) -> None:
        if not self._survey or len(self._survey.readings) < 3:
            self._set_status("Need at least 3 samples to render a heatmap.", error=True)
            return
        self._overlay_active = True
        self._redraw_floor_plan(overlay=True)
        self._set_status(
            f"Heatmap rendered ({len(self._survey.readings)} samples, "
            f"AP: {self._ap_combo.currentText()})."
        )

    def _on_clear_samples(self) -> None:
        if not self._survey:
            return
        self._survey.readings.clear()
        self._overlay_active = False
        self._refresh_sample_table()
        self._refresh_ap_combo()
        self._sample_count_lbl.setText("0 samples")
        self._redraw_floor_plan()
        self._set_status("All samples cleared.")

    def _on_delete_sample(self) -> None:
        if not self._survey:
            return
        rows = sorted(
            {i.row() for i in self._sample_table.selectedIndexes()}, reverse=True)
        for row in rows:
            if 0 <= row < len(self._survey.readings):
                self._survey.readings.pop(row)
        self._refresh_sample_table()
        self._refresh_ap_combo()
        self._sample_count_lbl.setText(
            f"{len(self._survey.readings)} samples")
        self._redraw_floor_plan()

    def _on_sample_selected(self) -> None:
        if self._floor_plan_img is not None:
            self._redraw_floor_plan()

    def _on_export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Heatmap",
            str(Path.home() / "wifi_heatmap.png"),
            "PNG (*.png)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            self._fig.savefig(path, dpi=150, bbox_inches="tight")
            self._set_status(f"Exported to {Path(path).name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}", error=True)

    # ── Refresh helpers ───────────────────────────────────────────────────────

    def _refresh_sample_table(self) -> None:
        self._sample_table.setRowCount(0)
        if not self._survey:
            return
        for idx, r in enumerate(self._survey.readings):
            row = self._sample_table.rowCount()
            self._sample_table.insertRow(row)

            if r.readings:
                avg_dbm = float(np.mean(list(r.readings.values())))
                quality = dbm_to_quality(avg_dbm)
                dbm_str = f"{avg_dbm:.0f} dBm"
            else:
                dbm_str = "—"
                quality = "—"

            n_aps = len(r.readings)

            items = [
                QTableWidgetItem(str(idx + 1)),
                QTableWidgetItem(dbm_str),
                QTableWidgetItem(quality),
                QTableWidgetItem(str(n_aps)),
            ]
            # Colour the dBm cell
            if r.readings:
                color = _dbm_color(avg_dbm)
                items[1].setForeground(QColor(color))

            for col, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._sample_table.setItem(row, col, item)

    def _refresh_ap_combo(self) -> None:
        current_data = self._ap_combo.currentData()
        self._ap_combo.blockSignals(True)
        self._ap_combo.clear()
        self._ap_combo.addItem("All APs (average)", userData=None)

        if self._survey:
            for bssid in self._survey.ap_bssids():
                self._ap_combo.addItem(bssid, userData=bssid)

        # Restore previous selection if still present
        idx = self._ap_combo.findData(current_data)
        if idx >= 0:
            self._ap_combo.setCurrentIndex(idx)
        self._ap_combo.blockSignals(False)

        # Also update coverage stats table
        self._refresh_coverage_table()

    def _refresh_coverage_table(self) -> None:
        self._cov_table.setRowCount(0)
        if not self._survey:
            return
        bssid_best: Dict[str, int] = {}
        for r in self._survey.readings:
            for bssid, dbm in r.readings.items():
                if bssid not in bssid_best or dbm > bssid_best[bssid]:
                    bssid_best[bssid] = dbm
        for bssid, best in sorted(bssid_best.items(), key=lambda kv: -kv[1]):
            row = self._cov_table.rowCount()
            self._cov_table.insertRow(row)
            items = [
                QTableWidgetItem(bssid),
                QTableWidgetItem(f"{best} dBm"),
                QTableWidgetItem(dbm_to_quality(best)),
            ]
            items[1].setForeground(QColor(_dbm_color(best)))
            for col, item in enumerate(items):
                self._cov_table.setItem(row, col, item)

    # ── Utility ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str, error: bool = False) -> None:
        color = RED if error else TEXT_SECONDARY
        self._status_label.setStyleSheet(
            f"color:{color}; font-size:10px; padding:2px 0;")
        self._status_label.setText(text)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in (self._btn_save, self._btn_add, self._btn_render,
                    self._btn_clear, self._btn_export):
            btn.setEnabled(enabled)


# ── Helper: dBm → CSS colour ──────────────────────────────────────────────────

def _dbm_color(dbm: float) -> str:
    if dbm >= -60:
        return _s.GREEN
    if dbm >= -75:
        return _s.AMBER
    return _s.RED

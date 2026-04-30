"""
Network Documentation Page — one-click "Document My Network".

Generates a self-contained HTML file that includes:
  • Network topology diagram (PNG snapshot from the topology widget)
  • Full device inventory table
  • Open port inventory (from last port scan, if available)
  • TLS certificate inventory (from cert monitor, if available)

The page keeps a reference to whatever data was last collected by the
dashboard and passes it to net_doc_generator.generate_network_doc().
"""

from __future__ import annotations

import datetime
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_ALT_ROW, BG_CARD, BG_DARK, BORDER, CARD_HDR_BORDER,
    GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)


# ── Background generation worker ─────────────────────────────────────────────

class _GenWorker(QThread):
    """Runs generate_network_doc() off the main thread."""

    finished = pyqtSignal(str)   # path to generated file
    error    = pyqtSignal(str)

    def __init__(self, devices, port_data, cert_data, topology_png, parent=None):
        super().__init__(parent)
        self._devices      = devices
        self._port_data    = port_data
        self._cert_data    = cert_data
        self._topology_png = topology_png

    def run(self) -> None:
        try:
            from modules.net_doc_generator import generate_network_doc
            path = generate_network_doc(
                devices      = self._devices,
                port_data    = self._port_data,
                cert_data    = self._cert_data,
                topology_png = self._topology_png,
            )
            self.finished.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))


# ── Card helper ───────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(
        f"QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    hdr = QFrame()
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER}; border-radius:0px;"
    )
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    t = QLabel(title.upper())
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        f" letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    outer.addWidget(hdr)
    body = QVBoxLayout()
    body.setContentsMargins(12, 10, 12, 10)
    body.setSpacing(6)
    outer.addLayout(body, 1)
    return frame, body


def _kpi(label: str, value: str, color: str = TEXT_PRIMARY) -> QWidget:
    w = QFrame()
    w.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {ACCENT}; border-radius:0px; }}"
    )
    lay = QVBoxLayout(w)
    lay.setContentsMargins(10, 6, 10, 6)
    lay.setSpacing(0)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold; border:none; background:transparent;")
    val = QLabel(value)
    val.setStyleSheet(f"color:{color}; font-size:18px; font-weight:bold; border:none; background:transparent;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return w


# ── Main page ─────────────────────────────────────────────────────────────────

class NetworkDocPage(QWidget):
    """
    One-click network documentation generator page.

    Call set_scan_data(devices, port_data, cert_data, topology_widget)
    from the dashboard after each scan to keep the data fresh.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._devices:     List[Dict] = []
        self._port_data:   Dict[str, List] = {}
        self._cert_data:   List[Dict] = []
        self._topo_widget: Optional[Any]  = None   # TopologyWidget ref
        self._last_path:   Optional[str]  = None
        self._worker:      Optional[_GenWorker] = None
        self._setup_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page header
        title = QLabel("Network Documentation")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        sub = QLabel(
            "Generate a self-contained HTML report — topology diagram, "
            "device inventory, open ports, and certificate expiry"
        )
        sub.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none; padding:0 0 4px 0;"
        )
        root.addWidget(title)
        root.addWidget(sub)

        # ── KPI tiles ─────────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_devices = _kpi("Devices", "0")
        self._kpi_ports   = _kpi("Open Ports", "0")
        self._kpi_certs   = _kpi("Certificates", "0")
        for w in (self._kpi_devices, self._kpi_ports, self._kpi_certs):
            kpi_row.addWidget(w, 1)
        root.addLayout(kpi_row)

        # ── Options card ──────────────────────────────────────────────────────
        opt_frame, opt_body = _card("Report Contents")

        _chk_qss = (
            f"QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; }}"
            f"QCheckBox::indicator {{ width:13px; height:13px; border:1px solid {BORDER};"
            f" border-radius:2px; background:{BG_CARD}; }}"
            f"QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        self._chk_topo  = QCheckBox("Network topology diagram (PNG snapshot)")
        self._chk_inv   = QCheckBox("Device inventory table")
        self._chk_ports = QCheckBox("Open port inventory (requires port scan)")
        self._chk_certs = QCheckBox("TLS certificate inventory (requires cert scan)")
        for c in (self._chk_topo, self._chk_inv, self._chk_ports, self._chk_certs):
            c.setChecked(True)
            c.setStyleSheet(_chk_qss)
            opt_body.addWidget(c)
        root.addWidget(opt_frame)

        # ── Action row ────────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._btn_generate = QPushButton("▣  Generate Network Doc")
        self._btn_generate.setObjectName("btnScan")
        self._btn_generate.setFixedHeight(34)
        self._btn_generate.setMinimumWidth(200)
        self._btn_generate.clicked.connect(self._generate)

        self._btn_open = QPushButton("Open in Browser")
        self._btn_open.setFixedHeight(34)
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_in_browser)
        self._btn_open.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:2px; padding:0 16px; font-size:12px; }}"
            f"QPushButton:hover {{ background:{ACCENT}; color:white; border-color:{ACCENT}; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
        )

        self._btn_save_as = QPushButton("Save As…")
        self._btn_save_as.setFixedHeight(34)
        self._btn_save_as.setEnabled(False)
        self._btn_save_as.clicked.connect(self._save_as)
        self._btn_save_as.setStyleSheet(self._btn_open.styleSheet())

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )

        action_row.addWidget(self._btn_generate)
        action_row.addWidget(self._btn_open)
        action_row.addWidget(self._btn_save_as)
        action_row.addWidget(self._status_lbl, 1)
        root.addLayout(action_row)

        # ── Log card ──────────────────────────────────────────────────────────
        log_frame, log_body = _card("Generation Log")
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"QPlainTextEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" font-size:11px; border:none; padding:4px 8px; }}"
        )
        self._log.setMaximumBlockCount(500)
        self._log.appendPlainText("Run a scan first, then click Generate Network Doc.")
        log_body.addWidget(self._log)
        root.addWidget(log_frame, 1)

    # ── Data injection ────────────────────────────────────────────────────────

    def set_scan_data(
        self,
        devices:      List[Dict],
        port_data:    Dict[str, List],
        cert_data:    List[Dict],
        topo_widget=None,
    ) -> None:
        """Call from the dashboard after each scan to refresh the source data."""
        self._devices   = devices   or []
        self._port_data = port_data or {}
        self._cert_data = cert_data or []
        self._topo_widget = topo_widget
        n_ports = sum(len(v) for v in self._port_data.values())
        # Update KPI tiles
        for kpi, val in [
            (self._kpi_devices, str(len(self._devices))),
            (self._kpi_ports,   str(n_ports)),
            (self._kpi_certs,   str(len(self._cert_data))),
        ]:
            kpi.findChild(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly)
            # Simpler: walk children
            for child in kpi.findChildren(QLabel):
                if child.text().lstrip("-").isdigit() or child.text() == "0":
                    child.setText(val)
                    break

    def _refresh_kpis(self) -> None:
        n_ports = sum(len(v) for v in self._port_data.values())
        self._update_kpi(self._kpi_devices, str(len(self._devices)))
        self._update_kpi(self._kpi_ports,   str(n_ports))
        self._update_kpi(self._kpi_certs,   str(len(self._cert_data)))

    def _update_kpi(self, tile: QWidget, value: str) -> None:
        labels = tile.findChildren(QLabel)
        # second label is the value (first is the capitalized header)
        if len(labels) >= 2:
            labels[1].setText(value)

    # ── Generation ────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _generate(self) -> None:
        if self._worker and self._worker.isRunning():
            return

        self._btn_generate.setEnabled(False)
        self._btn_generate.setText("⏳  Generating…")
        self._status_lbl.setText("")
        self._log.appendPlainText(
            f"\n── Generating at {datetime.datetime.now().strftime('%H:%M:%S')} ──"
        )
        self._refresh_kpis()

        # Build optional topology PNG
        topology_png: Optional[Path] = None
        if self._chk_topo.isChecked() and self._topo_widget is not None:
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.close()
                topology_png = Path(tmp.name)
                self._topo_widget._fig.savefig(
                    str(topology_png), dpi=144, bbox_inches="tight",
                    facecolor=self._topo_widget._fig.get_facecolor(),
                )
                self._log.appendPlainText("  ✓ Topology snapshot saved")
            except Exception as exc:
                self._log.appendPlainText(f"  ⚠ Topology snapshot failed: {exc}")
                topology_png = None

        devices   = self._devices   if self._chk_inv.isChecked()   else []
        port_data = self._port_data if self._chk_ports.isChecked() else {}
        cert_data = self._cert_data if self._chk_certs.isChecked() else []

        self._log.appendPlainText(
            f"  Devices: {len(devices)}  "
            f"Open ports: {sum(len(v) for v in port_data.values())}  "
            f"Certs: {len(cert_data)}"
        )

        self._worker = _GenWorker(devices, port_data, cert_data, topology_png, parent=self)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(str)
    def _on_done(self, path: str) -> None:
        self._last_path = path
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("▣  Generate Network Doc")
        self._btn_open.setEnabled(True)
        self._btn_save_as.setEnabled(True)
        self._status_lbl.setText(f"✓  Saved: {path}")
        self._log.appendPlainText(f"  ✓ Report written: {path}")
        self._log.appendPlainText("── Done ──\n")

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("▣  Generate Network Doc")
        self._status_lbl.setText(f"⚠  {msg}")
        self._log.appendPlainText(f"  ✗ Error: {msg}")

    @pyqtSlot()
    def _open_in_browser(self) -> None:
        if self._last_path:
            webbrowser.open(Path(self._last_path).as_uri())

    @pyqtSlot()
    def _save_as(self) -> None:
        if not self._last_path:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Network Doc",
            str(Path.home() / "network_documentation.html"),
            "HTML files (*.html);;All files (*)",
        )
        if dest:
            import shutil
            shutil.copy2(self._last_path, dest)
            self._status_lbl.setText(f"Saved to: {dest}")

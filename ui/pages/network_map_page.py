"""
network_map_page.py — Interactive Cytoscape.js Network Map page.

Replaces the embedded TopologyWidget matplotlib tab with a full-page widget
that offers two views:
  • Interactive (QWebEngineView + Cytoscape.js) — drag-to-arrange, physics
    layouts, Focus Mode, per-node HTML tooltips, position persistence via
    QWebChannel bridge.
  • Classic (TopologyWidget matplotlib) — retained as a fallback for users
    without PyQt6-WebEngine or in headless mode.

The page implements the same public render() / update_lldp_neighbors() API
as TopologyWidget so that all existing callers in scan_wiring.py continue
to work without modification.

Architecture:
  • UI layer — inherits QWidget; no direct DB writes.
  • WebEngine is lazy-imported so the app starts even without PyQt6-WebEngine.
  • All colours come from ui/styles.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, QSettings, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE,
    BG_CARD, BG_DARK, BG_HOVER, BORDER,
    TEAL, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.topology_widget import TopologyWidget
from modules.topology_layout import (
    NodePosition, TopologyEdge, clear_layout, compute_scan_id, load_layout, save_layout,
)
from modules.topology_cytoscape import LAYOUT_NAMES, build_cytoscape_html

log = logging.getLogger(__name__)

_SETTINGS_KEY_LAYOUT = "network_map/layout"
_SETTINGS_KEY_VIEW   = "network_map/active_view"  # "interactive" | "classic"

# Compact inline style for toolbar buttons — overrides the wide-padding
# #btnNetRefresh QSS which is designed for full-size action buttons, not
# the tight fixed-width buttons (32–116 px) used in the map toolbar.
_TOOLBAR_BTN_SS = (
    f"QPushButton{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
    f"border-radius:4px;padding:3px 10px;font-size:12px;font-weight:500;}}"
    f"QPushButton:hover{{background:{BG_HOVER};border-color:{ACCENT};color:{ACCENT};}}"
    f"QPushButton:pressed{{background:{ACCENT};color:{WHITE};border-color:{ACCENT_DARK};}}"
    f"QPushButton:checked{{background:{ACCENT};color:{WHITE};border-color:{ACCENT_DARK};}}"
    f"QPushButton:disabled{{background:{BG_CARD};color:{TEXT_MUTED};border-color:{BORDER};}}"
)


# ── QWebChannel bridge (server-side Python object) ───────────────────────────

class _CytoscapeBridge(QObject):
    """Python object exposed to Cytoscape.js via QWebChannel.

    Methods decorated with @pyqtSlot are callable from JavaScript.
    """

    node_clicked_signal = pyqtSignal(str)   # emits IP address
    export_ready        = pyqtSignal(str)   # emits base-64 PNG data URL

    def __init__(self, scan_id: str = "default", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._scan_id = scan_id
        self._pending_positions: Dict[str, NodePosition] = {}

    def set_scan_id(self, scan_id: str) -> None:
        self._scan_id = scan_id
        self._pending_positions = {}

    @pyqtSlot(str)
    def nodeClicked(self, ip: str) -> None:  # noqa: N802 — JS convention
        self.node_clicked_signal.emit(ip)

    @pyqtSlot(str, str, str)
    def savePosition(self, node_id: str, x_str: str, y_str: str) -> None:  # noqa: N802
        """Persist a node position (0–1 normalised coords from JS)."""
        try:
            x = float(x_str)
            y = float(y_str)
        except (ValueError, TypeError):
            return
        self._pending_positions[node_id] = NodePosition(
            node_id=node_id, x=x, y=y, pinned=True,
        )
        try:
            existing = load_layout(self._scan_id)
            existing.update(self._pending_positions)
            save_layout(self._scan_id, existing)
        except Exception:
            pass  # non-fatal — position save is best-effort

    @pyqtSlot(str)
    def exportPng(self, data_url: str) -> None:  # noqa: N802
        self.export_ready.emit(data_url)


# ── NetworkMapPage ────────────────────────────────────────────────────────────

class NetworkMapPage(QWidget):
    """Full-page Network Map with interactive Cytoscape.js view + Classic fallback.

    Public API (mirrors TopologyWidget so scan_wiring.py needs no changes):
      render(**kwargs)                — feed both views
      update_lldp_neighbors(...)     — update LLDP overlay on both views
      fit_view()                     — fit the active view
      zoom_in() / zoom_out()         — classic view only (no-op on interactive)
      reset_layout()                 — clear saved positions and re-run layout
      node_clicked : pyqtSignal(str) — emitted when user clicks a node
      scan_requested : pyqtSignal()  — emitted by empty-state CTA button
    """

    node_clicked   = pyqtSignal(str)   # IP address of clicked device
    scan_requested = pyqtSignal()      # empty-state "Run Scan" CTA

    def __init__(self, store=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._last_render_kwargs: Dict[str, Any] = {}
        self._scan_id = "default"
        self._web_available = False
        self._web_view: Any = None
        self._bridge: Optional[_CytoscapeBridge] = None
        self._diff_mode = False

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # QStackedWidget: page 0 = empty state, page 1 = map content
        self._outer_stack = QStackedWidget()
        root.addWidget(self._outer_stack)

        # ── Page 0: empty state ──────────────────────────────────────────────
        empty = QWidget()
        empty_lay = QVBoxLayout(empty)
        empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("◆")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet(f"font-size:40px; color:{TEXT_MUTED};")
        empty_title = QLabel("Network Map")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(
            f"font-size:18px; font-weight:600; color:{TEXT_PRIMARY}; margin-top:12px;"
        )
        empty_body = QLabel(
            "Run a device scan to visualise your network topology.\n"
            "Nodes are drag-to-arrange with physics-based auto-layout."
        )
        empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_body.setWordWrap(True)
        empty_body.setStyleSheet(f"font-size:13px; color:{TEXT_SECONDARY}; margin:8px 40px;")
        btn_scan = QPushButton("Run Scan")
        btn_scan.setFixedWidth(130)
        btn_scan.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:4px;padding:8px 16px;font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:{ACCENT_LITE};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
        )
        btn_scan.clicked.connect(self.scan_requested)
        empty_lay.addWidget(empty_icon)
        empty_lay.addWidget(empty_title)
        empty_lay.addWidget(empty_body)
        empty_lay.addSpacing(16)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_scan)
        btn_row.addStretch()
        empty_lay.addLayout(btn_row)
        self._outer_stack.addWidget(empty)

        # ── Page 1: map content ──────────────────────────────────────────────
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(8, 4, 8, 4)
        content_lay.setSpacing(2)

        # Toolbar
        toolbar_layout = self._build_toolbar()
        content_lay.addLayout(toolbar_layout)

        # Inner tab: Interactive | Classic
        self._inner_tab = QTabWidget()
        self._inner_tab.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {BORDER};background:{BG_CARD};}}"
            f"QTabBar::tab{{padding:4px 14px;font-size:12px;background:{BG_DARK};"
            f"color:{TEXT_SECONDARY};border:1px solid {BORDER};}}"
            f"QTabBar::tab:selected{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"font-weight:600;}}"
        )
        self._inner_tab.currentChanged.connect(self._on_view_tab_changed)

        # Interactive tab: QWebEngineView (lazy)
        self._interactive_container = QWidget()
        ic_lay = QVBoxLayout(self._interactive_container)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        self._web_placeholder = QLabel(
            "Interactive map requires PyQt6-WebEngine.\n"
            "Install with:  pip install PyQt6-WebEngine"
        )
        self._web_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._web_placeholder.setStyleSheet(f"color:{TEXT_MUTED};font-size:12px;")
        ic_lay.addWidget(self._web_placeholder)
        self._web_container_layout = ic_lay
        self._try_init_webengine()

        # Classic tab: TopologyWidget (matplotlib)
        self._classic_widget = TopologyWidget()
        self._classic_widget.node_clicked.connect(self.node_clicked)

        self._inner_tab.addTab(self._interactive_container, "◆  Interactive")
        self._inner_tab.addTab(self._classic_widget,         "◇  Classic")

        content_lay.addWidget(self._inner_tab, 1)
        self._outer_stack.addWidget(content)

        # Restore last-used view tab; fall back to Classic if WebEngine unavailable
        s = QSettings()
        saved_view = s.value(_SETTINGS_KEY_VIEW, "interactive")
        if saved_view == "classic" or not self._web_available:
            self._inner_tab.setCurrentIndex(1)

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 2, 0, 2)
        toolbar.setSpacing(4)

        # Layout selector
        self._layout_combo = QComboBox()
        self._layout_combo.setFixedWidth(116)
        self._layout_combo.setStyleSheet(
            f"QComboBox{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:4px;padding:3px 8px;font-size:12px;color:{TEXT_PRIMARY};}}"
            f"QComboBox:hover{{border-color:{ACCENT};}}"
            f"QComboBox::drop-down{{border:none;width:18px;}}"
            f"QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};selection-background-color:{BG_HOVER};"
            f"selection-color:{TEXT_PRIMARY};}}"
        )
        for label in LAYOUT_NAMES:
            self._layout_combo.addItem(label)
        s = QSettings()
        saved_layout = s.value(_SETTINGS_KEY_LAYOUT, "Hierarchy")
        idx = self._layout_combo.findText(saved_layout)
        if idx >= 0:
            self._layout_combo.setCurrentIndex(idx)
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)

        def _btn(label: str, tip: str, w: int = 52) -> QPushButton:
            b = QPushButton(label)
            b.setFixedWidth(w)
            b.setToolTip(tip)
            b.setStyleSheet(_TOOLBAR_BTN_SS)
            return b

        btn_fit  = _btn("Fit",  "Fit topology to window")
        btn_rst  = _btn("Reset Layout", "Clear saved positions and re-layout", 108)
        btn_zin  = _btn("+",   "Zoom in (Classic only)", 32)
        btn_zout = _btn("−",   "Zoom out (Classic only)", 32)

        # Focus Mode toggle
        self._btn_focus = QPushButton("Focus Mode")
        self._btn_focus.setCheckable(True)
        self._btn_focus.setFixedWidth(96)
        self._btn_focus.setToolTip(
            "Highlight only the selected node and its direct neighbours"
        )
        self._btn_focus.setStyleSheet(_TOOLBAR_BTN_SS)

        # Show Changes toggle (exposed as property for scan_wiring compat)
        self._btn_diff = QPushButton("Show Changes")
        self._btn_diff.setCheckable(True)
        self._btn_diff.setFixedWidth(110)
        self._btn_diff.setToolTip(
            "Overlay added/removed devices and links vs. the previous scan"
        )
        self._btn_diff.setStyleSheet(_TOOLBAR_BTN_SS)

        # Diff badge label
        self._diff_label = QLabel()
        self._diff_label.setStyleSheet(
            f"color:{TEAL};font-size:11px;font-weight:600;padding:0 6px;"
        )
        self._diff_label.setVisible(False)

        # Export button
        btn_export = _btn("Export PNG", "Export the interactive map as a PNG image", 90)
        btn_export.clicked.connect(self._on_export)

        btn_fit.clicked.connect(self.fit_view)
        btn_rst.clicked.connect(self.reset_layout)
        btn_zin.clicked.connect(self.zoom_in)
        btn_zout.clicked.connect(self.zoom_out)
        self._btn_focus.toggled.connect(self._on_focus_toggled)
        self._btn_diff.toggled.connect(self._on_diff_toggled)

        toolbar.addWidget(self._layout_combo)
        toolbar.addWidget(btn_fit)
        toolbar.addWidget(btn_zin)
        toolbar.addWidget(btn_zout)
        toolbar.addWidget(self._btn_focus)
        toolbar.addWidget(self._btn_diff)
        toolbar.addWidget(self._diff_label)
        toolbar.addStretch()
        toolbar.addWidget(btn_export)
        toolbar.addWidget(btn_rst)

        return toolbar

    def _try_init_webengine(self) -> None:
        """Lazy-import QWebEngineView; populate placeholder if unavailable."""
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEnginePage
            from PyQt6.QtWebChannel import QWebChannel
            from PyQt6.QtCore import QUrl as _QUrl

            # javaScriptConsoleMessage is a virtual method, not a signal —
            # must subclass QWebEnginePage to intercept it.
            class _LogPage(QWebEnginePage):
                def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
                    log.debug("JS [%s:%s] %s", source, line, message)

            self._web_view = QWebEngineView(self._interactive_container)
            self._web_view.setPage(_LogPage(self._web_view))
            self._web_view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

            self._bridge = _CytoscapeBridge(parent=self)
            self._bridge.node_clicked_signal.connect(self.node_clicked)
            self._bridge.export_ready.connect(self._on_export_data)

            self._web_channel = QWebChannel(self._web_view.page())
            self._web_channel.registerObject("bridge", self._bridge)
            self._web_view.page().setWebChannel(self._web_channel)

            # Inject qwebchannel.js at document-creation time so QWebChannel is
            # defined before the page's own inline scripts execute.  Using
            # <script src="qrc://..."> inside setHtml() is blocked by Qt6's
            # about:blank origin policy; QWebEngineScript injection bypasses it.
            _qwc = QWebEngineScript()
            _qwc.setName("qwebchannel_init")
            _qwc.setSourceUrl(_QUrl("qrc:///qtwebchannel/qwebchannel.js"))
            _qwc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            _qwc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            self._web_view.page().scripts().insert(_qwc)

            # Remove placeholder, add real view
            self._web_placeholder.setParent(None)
            self._web_container_layout.addWidget(self._web_view)
            self._web_available = True

            # Show a light placeholder so the view is never a dark rectangle
            # before the first scan populates it.
            self._web_view.setHtml(
                f"<html><body style='background:{BG_DARK};display:flex;"
                f"align-items:center;justify-content:center;height:100vh;"
                f"font-family:sans-serif;color:{TEXT_SECONDARY};font-size:13px;'>"
                f"Run a scan to populate the interactive map</body></html>"
            )
        except Exception as exc:
            import traceback
            log.warning("WebEngine init failed: %s: %s", type(exc).__name__, exc)
            traceback.print_exc()
            # non-fatal — classic view only; placeholder stays visible

    # ── Public render API (mirrors TopologyWidget) ────────────────────────────

    def render(
        self,
        devices: List[Any],
        gateway_ip: Optional[str] = None,
        gateway_mac: Optional[str] = None,
        mesh_units: Optional[List[Any]] = None,
        mesh_enrichment: Optional[Dict[str, Any]] = None,
        modem_data: Optional[Dict[str, Any]] = None,
        segments: Optional[List[Any]] = None,
        edges: Optional[List[TopologyEdge]] = None,
        down_ips: Optional[set] = None,
        new_ips: Optional[set] = None,
        diff: Optional[Any] = None,
        lldp_neighbors: Optional[List[Any]] = None,
        lldp_admin_needed: bool = False,
    ) -> None:
        """Update both the Interactive and Classic views with new scan data."""
        self._last_render_kwargs = dict(
            devices=devices,
            gateway_ip=gateway_ip,
            gateway_mac=gateway_mac,
            mesh_units=mesh_units,
            mesh_enrichment=mesh_enrichment,
            modem_data=modem_data,
            segments=segments,
            edges=edges,
            down_ips=down_ips,
            new_ips=new_ips,
            diff=diff,
            lldp_neighbors=lldp_neighbors,
            lldp_admin_needed=lldp_admin_needed,
        )

        # Switch to content view
        if self._outer_stack.currentIndex() == 0:
            self._outer_stack.setCurrentIndex(1)

        # Classic view (always rendered)
        try:
            self._classic_widget.render(
                devices, gateway_ip, gateway_mac,
                mesh_units=mesh_units,
                mesh_enrichment=mesh_enrichment,
                modem_data=modem_data,
                segments=segments,
                edges=edges,
                down_ips=down_ips,
                new_ips=new_ips,
                diff=diff,
                lldp_neighbors=lldp_neighbors,
                lldp_admin_needed=lldp_admin_needed,
            )
        except Exception:
            log.debug("network_map_page: classic render failed", exc_info=True)

        # Interactive view
        if self._web_available and self._web_view is not None:
            self._refresh_web_view(diff=diff if self._diff_mode else None)

        # Compute scan_id for position saving
        self._scan_id = compute_scan_id(devices)
        if self._bridge is not None:
            self._bridge.set_scan_id(self._scan_id)

    def _refresh_web_view(self, diff: Optional[Any] = None) -> None:
        """Rebuild and load the Cytoscape HTML into the web view."""
        if not self._web_available or self._web_view is None:
            return
        kw = self._last_render_kwargs
        if not kw:
            return

        scan_id  = self._scan_id
        saved    = load_layout(scan_id) if scan_id else {}
        layout   = LAYOUT_NAMES.get(
            self._layout_combo.currentText(), "breadthfirst"
        )

        try:
            html = build_cytoscape_html(
                devices=kw.get("devices", []),
                edges=kw.get("edges"),
                diff=diff,
                lldp_neighbors=kw.get("lldp_neighbors"),
                segments=kw.get("segments"),
                positions=saved if saved else None,
                gateway_ip=kw.get("gateway_ip"),
                gateway_mac=kw.get("gateway_mac"),
                mesh_units=kw.get("mesh_units"),
                mesh_enrichment=kw.get("mesh_enrichment"),
                modem_data=kw.get("modem_data"),
                down_ips=kw.get("down_ips"),
                new_ips=kw.get("new_ips"),
                initial_layout=layout,
            )
            self._web_view.setHtml(html)
        except Exception:
            log.debug("network_map_page: Cytoscape HTML build failed", exc_info=True)

    def update_lldp_neighbors(
        self,
        neighbors: List[Any],
        admin_needed: bool = False,
    ) -> None:
        """Re-render with updated LLDP data without requiring a full rescan."""
        if not self._last_render_kwargs:
            return
        kw = dict(self._last_render_kwargs)
        kw["lldp_neighbors"]    = neighbors
        kw["lldp_admin_needed"] = admin_needed
        self.render(**kw)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def fit_view(self) -> None:
        if self._inner_tab.currentIndex() == 0 and self._web_available:
            self._run_js("window.fitView && window.fitView();")
        else:
            self._classic_widget.fit_view()

    def zoom_in(self) -> None:
        self._classic_widget.zoom_in()

    def zoom_out(self) -> None:
        self._classic_widget.zoom_out()

    def reset_layout(self) -> None:
        clear_layout(self._scan_id)
        if self._last_render_kwargs:
            self.render(**self._last_render_kwargs)

    @pyqtSlot(str)
    def _on_layout_changed(self, label: str) -> None:
        cyto_name = LAYOUT_NAMES.get(label, "breadthfirst")
        QSettings().setValue(_SETTINGS_KEY_LAYOUT, label)
        if self._web_available and self._inner_tab.currentIndex() == 0:
            self._run_js(f"window.setLayout && window.setLayout({json.dumps(cyto_name)});")

    @pyqtSlot(bool)
    def _on_focus_toggled(self, checked: bool) -> None:
        self._run_js(
            f"window.toggleFocus && window.toggleFocus({'true' if checked else 'false'});"
        )

    @pyqtSlot(bool)
    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_mode = checked
        # Interactive view: toggle hidden class via JS
        self._run_js(
            f"window.toggleChanges && window.toggleChanges({'true' if checked else 'false'});"
        )
        # Classic view: full re-render with/without diff
        if self._last_render_kwargs:
            kw = dict(self._last_render_kwargs)
            # The stored diff is managed by the Dashboard; we toggle here via overlay
            # JS handles interactive view; classic view re-render is below
            try:
                kw_diff = kw.get("diff") if checked else None
                self._classic_widget.render(
                    kw.get("devices", []),
                    kw.get("gateway_ip"),
                    kw.get("gateway_mac"),
                    mesh_units=kw.get("mesh_units"),
                    mesh_enrichment=kw.get("mesh_enrichment"),
                    modem_data=kw.get("modem_data"),
                    segments=kw.get("segments"),
                    edges=kw.get("edges"),
                    down_ips=kw.get("down_ips"),
                    new_ips=kw.get("new_ips"),
                    diff=kw_diff,
                    lldp_neighbors=kw.get("lldp_neighbors"),
                )
            except Exception:
                pass  # non-fatal — diff overlay is best-effort

    @pyqtSlot(int)
    def _on_view_tab_changed(self, index: int) -> None:
        QSettings().setValue(_SETTINGS_KEY_VIEW, "interactive" if index == 0 else "classic")
        # Refresh the interactive view when switching to it if data is pending
        if index == 0 and self._web_available and self._last_render_kwargs:
            self._refresh_web_view(
                diff=self._last_render_kwargs.get("diff") if self._diff_mode else None
            )

    def _on_export(self) -> None:
        """Trigger JS to capture a PNG from the Cytoscape view."""
        if self._web_available and self._inner_tab.currentIndex() == 0:
            self._run_js("window.exportPng && window.exportPng();")
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Export",
                "PNG export is only available in the Interactive view.\n"
                "Switch to the Interactive tab and try again.",
            )

    @pyqtSlot(str)
    def _on_export_data(self, data_url: str) -> None:
        """Receive base-64 PNG from JS and save it via file dialog."""
        import base64
        from PyQt6.QtWidgets import QFileDialog
        from modules.utils import get_app_data_dir

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Network Map", str(get_app_data_dir() / "network_map.png"),
            "PNG Image (*.png)"
        )
        if not path:
            return
        try:
            header, b64 = data_url.split(",", 1)
            img_bytes = base64.b64decode(b64)
            with open(path, "wb") as fh:
                fh.write(img_bytes)
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Map exported to {path}", "info")
        except Exception as exc:
            log.warning("network_map_page: export failed: %s", exc)

    def _run_js(self, script: str) -> None:
        """Run a JavaScript snippet in the web view if available."""
        if self._web_available and self._web_view is not None:
            try:
                self._web_view.page().runJavaScript(script)
            except Exception:
                pass  # non-fatal — JS call may fail if page not loaded

    # ── Convenience properties for backward compatibility ─────────────────────

    @property
    def classic_widget(self) -> TopologyWidget:
        return self._classic_widget

    @property
    def btn_diff(self) -> QPushButton:
        return self._btn_diff

    @property
    def diff_label(self) -> QLabel:
        return self._diff_label

    @property
    def _topology_widget(self) -> TopologyWidget:
        """Legacy alias so existing code using self._topology_widget still works."""
        return self._classic_widget

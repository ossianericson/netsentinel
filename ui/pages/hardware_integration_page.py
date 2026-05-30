"""
HardwareIntegrationPage — Hardware Hub

Primary view: live status cards for every imported hardware plugin.
Each card auto-refreshes on a configurable interval, shows key metrics,
and expands to a full signal/topology detail panel (v2.1).

Secondary view: collapsible "How to write a plugin" guide (steps 1-4).

Plugin interface contract
─────────────────────────
  Required at module level:
    HARDWARE_NAME: str
    HARDWARE_TYPE: str   ("router" | "modem" | "ap" | "switch" | "other")
    get_info()  -> dict
    get_status() -> dict

  Optional:
    get_clients() -> list[dict]

Scripts are stored as file paths in QSettings("NetSentinel","NetSentinel")
under the key  hardware/custom_scripts.
"""

from __future__ import annotations

import ast
import json
import time
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QFileSystemWatcher, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from workers.plugin_polling_worker import PluginPollingWorker
from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WHITE,
)

from ui.widgets.hub_card import (
    HubCard, PipInstallDialog, _PluginConnectionTester,
    _CommunityIndexThread, _CommunityDownloadThread,
    _btn, _instance_id,
    _validate_script,
    _load_paths, _save_paths,
    _load_instances, _save_instances,
    _is_consented, _record_consent,
    _migrate_stale_paths,
    _load_last_result, _save_last_result,
    _record_success, _record_error, _reset_health,
    _load_instance_config,
    _TEMPLATE,
    _classify_error,
    # Re-exported for test compatibility
    _path_hash,
    _ModemDetailPanel, _RouterDetailPanel, _safe_set_text,
    _CIRCUIT_BREAK_THRESHOLD, _DEGRADED_HOURS, _load_health, _save_health,
)
from ui.pages.plugin_guide import PluginGuide



class HardwareIntegrationPage(QWidget):
    """Hardware Hub — live status dashboard for all imported hardware plugins."""

    # data dict has "_path" embedded so dashboard knows which plugin
    plugin_result    = pyqtSignal(dict)
    plugin_page_added = pyqtSignal(str, str)  # (script_path, display_label) — new plugin installed at runtime
    plugin_page_removed = pyqtSignal(str)     # script_path — plugin removed at runtime
    plugin_renamed   = pyqtSignal(str, str, str)  # (path, old_label, new_label) — instance display name changed
    navigate_to      = pyqtSignal(str)   # page label → _nav_rail_go_to
    geo_map_ip       = pyqtSignal(str)   # open geo map for this IP
    port_scan_ip     = pyqtSignal(str)   # pre-fill port scanner with this IP
    check_abuse_ip   = pyqtSignal(str)   # check IP on AbuseIPDB

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._poll_workers: Dict[str, PluginPollingWorker] = {}
        self._cards:   Dict[str, HubCard] = {}
        # Tab indices — set by _build_ui
        self._tabs: Optional[QTabWidget] = None
        self._suggested_tab_idx: int = 1
        self._suggested_lay:  Optional[QVBoxLayout]        = None

        self._build_ui()

        # Tick timer — updates "X min ago" labels every 30s
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self._tick_timestamps)
        self._tick_timer.start()

        # P6-4: file watcher — detects plugin edits (trigger re-poll) and deletions (FILE: error)
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_plugin_file_changed)

        # Start persistent poll workers for all imported plugins, staggered 3 s apart
        self._start_all_poll_workers()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

        # Page header — outside tabs so it's always visible
        hdr_row = QHBoxLayout()
        title = QLabel("Hardware")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()
        self._btn_new_plugin = _btn("⬡  New Plugin")
        self._btn_new_plugin.setToolTip(
            "Launch the wizard to create a new plugin script from a template"
        )
        self._btn_new_plugin.clicked.connect(self._on_create_plugin)
        hdr_row.addWidget(self._btn_new_plugin)

        self._btn_add = _btn("＋  Add Integration", accent=True)
        self._btn_add.clicked.connect(self._on_browse)
        hdr_row.addWidget(self._btn_add)

        # P3-5: Import .nspkg bundle
        self._btn_nspkg = _btn("⬡  Import .nspkg")
        self._btn_nspkg.setToolTip("Import a .nspkg plugin bundle (ZIP containing plugin.py + manifest.json)")
        self._btn_nspkg.clicked.connect(self._on_import_nspkg)
        hdr_row.addWidget(self._btn_nspkg)

        root.addLayout(hdr_row)

        # Status label (import feedback) — outside tabs
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        root.addWidget(self._status_lbl)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; border-radius:4px; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED};"
            f" padding:5px 14px; border:none; border-bottom:2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY};"
            f" border-bottom:2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        root.addWidget(self._tabs, 1)

        # ── Tab 0: Hardware (HubCards + guide) — always visible ──────────────
        hub_tab = QWidget()
        hub_tab.setStyleSheet(f"background:{BG_DARK};")
        hub_tab_lay = QVBoxLayout(hub_tab)
        hub_tab_lay.setContentsMargins(0, 6, 0, 0)
        hub_tab_lay.setSpacing(6)

        sub = QLabel(
            "Live status for all integrated hardware. "
            "Modem plugins refresh every 60 s · router/AP every 2 min · switch every 5 min. "
            "Click ● to expand the signal / topology detail panel."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; padding:0 8px;")
        hub_tab_lay.addWidget(sub)

        self._hub_scroll = QScrollArea()
        self._hub_scroll.setWidgetResizable(True)
        self._hub_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._hub_body = QWidget()
        self._hub_body.setStyleSheet(f"background:{BG_DARK};")
        self._hub_lay = QVBoxLayout(self._hub_body)
        self._hub_lay.setContentsMargins(0, 4, 0, 4)
        self._hub_lay.setSpacing(8)
        self._rebuild_hub()
        self._hub_scroll.setWidget(self._hub_body)
        hub_tab_lay.addWidget(self._hub_scroll, 3)

        guide_toggle_row = QHBoxLayout()
        guide_toggle_row.setContentsMargins(8, 0, 8, 0)
        self._guide_toggle = _btn("▶  How to write a plugin script")
        self._guide_toggle.clicked.connect(self._toggle_guide)
        guide_toggle_row.addWidget(self._guide_toggle)
        guide_toggle_row.addStretch()
        hub_tab_lay.addLayout(guide_toggle_row)

        self._guide_area = PluginGuide(self._hub_body)
        self._guide_area.setVisible(False)
        hub_tab_lay.addWidget(self._guide_area, 2)

        if not _load_paths():
            self._guide_area.setVisible(True)
            self._guide_toggle.setText("▼  How to write a plugin script")

        self._tabs.addTab(hub_tab, "Hardware")

        # ── Tab 1: Suggested — hidden until hw_detect finds matches ───────────
        suggested_tab = QWidget()
        suggested_tab.setStyleSheet(f"background:{BG_DARK};")
        suggested_outer = QVBoxLayout(suggested_tab)
        suggested_outer.setContentsMargins(0, 0, 0, 0)
        suggested_outer.setSpacing(0)

        sug_hdr = QFrame()
        sug_hdr.setObjectName("hubSugHdr")
        sug_hdr.setStyleSheet(
            f"QFrame#hubSugHdr {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        sug_hdr_lay = QHBoxLayout(sug_hdr)
        sug_hdr_lay.setContentsMargins(12, 7, 10, 7)
        sug_title = QLabel("Suggested for your network")
        sug_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        sug_title.setStyleSheet(f"color:{AMBER}; border:none; background:transparent;")
        sug_hdr_lay.addWidget(sug_title)
        sug_hdr_lay.addStretch()
        suggested_outer.addWidget(sug_hdr)

        sug_scroll = QScrollArea()
        sug_scroll.setWidgetResizable(True)
        sug_scroll.setStyleSheet("QScrollArea { border: none; }")
        sug_inner = QWidget()
        sug_inner.setStyleSheet(f"background:{BG_DARK};")
        self._suggested_lay = QVBoxLayout(sug_inner)
        self._suggested_lay.setContentsMargins(0, 2, 0, 6)
        self._suggested_lay.setSpacing(0)
        sug_scroll.setWidget(sug_inner)
        suggested_outer.addWidget(sug_scroll)

        self._suggested_tab_idx = self._tabs.addTab(suggested_tab, "Suggested")
        self._tabs.setTabVisible(self._suggested_tab_idx, False)

        # ── Tab 2: Browse community plugins (P3-4) ────────────────────────────
        self._browse_index_thread: Optional[QThread] = None
        self._browse_tab_idx = self._tabs.addTab(self._build_browse_tab(), "Browse")

    def _toggle_guide(self) -> None:
        visible = not self._guide_area.isVisible()
        self._guide_area.setVisible(visible)
        self._guide_toggle.setText(
            "▼  How to write a plugin script" if visible
            else "▶  How to write a plugin script"
        )

    # ── Browse tab (P3-4 community plugin index) ──────────────────────────────

    # URL of the community plugin index JSON.  Override by setting
    # QSettings("NetSentinel","NetSentinel")["hardware/community_index_url"].
    _DEFAULT_COMMUNITY_URL = (
        "https://raw.githubusercontent.com/netsentinel/"
        "netsentinel-plugins/main/index.json"
    )

    def _build_browse_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(f"background:{BG_DARK};")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        title = QLabel("Community Plugins")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none;")
        bar.addWidget(title)
        bar.addStretch()
        self._browse_status = QLabel("Press Refresh to fetch the index.")
        self._browse_status.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; border:none;")
        bar.addWidget(self._browse_status)
        btn_refresh = _btn("↻  Refresh")
        btn_refresh.clicked.connect(self._fetch_community_index)
        bar.addWidget(btn_refresh)
        lay.addLayout(bar)

        # Plugin card area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._browse_inner = QWidget()
        self._browse_inner.setStyleSheet(f"background:{BG_DARK};")
        self._browse_lay = QVBoxLayout(self._browse_inner)
        self._browse_lay.setContentsMargins(0, 4, 0, 4)
        self._browse_lay.setSpacing(4)
        self._browse_lay.addStretch()
        scroll.setWidget(self._browse_inner)
        lay.addWidget(scroll, 1)

        return tab

    def _fetch_community_index(self) -> None:
        """Fetch community index JSON in a background thread."""
        if self._browse_index_thread is not None and self._browse_index_thread.isRunning():
            return
        url = (
            QSettings("NetSentinel", "NetSentinel")
            .value("hardware/community_index_url", self._DEFAULT_COMMUNITY_URL)
        )
        self._browse_status.setText("Fetching index…")
        self._browse_index_thread = _CommunityIndexThread(url, parent=self)
        self._browse_index_thread.done.connect(self._on_community_index_done,
                                                Qt.ConnectionType.QueuedConnection)
        self._browse_index_thread.error.connect(self._on_community_index_error,
                                                 Qt.ConnectionType.QueuedConnection)
        self._browse_index_thread.start()

    @pyqtSlot(list)
    def _on_community_index_done(self, entries: list) -> None:
        self._browse_status.setText(f"{len(entries)} plugin(s) found.")
        self._rebuild_browse_cards(entries)

    @pyqtSlot(str)
    def _on_community_index_error(self, msg: str) -> None:
        self._browse_status.setText(f"Error: {msg}")

    def _rebuild_browse_cards(self, entries: list) -> None:
        # Remove existing cards (keep the trailing stretch)
        while self._browse_lay.count() > 1:
            item = self._browse_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for entry in entries:
            card = self._build_community_card(entry)
            self._browse_lay.insertWidget(self._browse_lay.count() - 1, card)

    def _build_community_card(self, entry: dict) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        info = QVBoxLayout()
        name_lbl = QLabel(f"<b>{entry.get('name', 'Unknown')}</b>")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none; background:transparent;")
        info.addWidget(name_lbl)

        author = entry.get("author", "")
        pypi   = entry.get("pypi", "")
        meta_parts = [p for p in [f"by {author}" if author else "", f"pip: {pypi}" if pypi else ""] if p]
        sub = QLabel("  ·  ".join(meta_parts))
        sub.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none; background:transparent;")
        info.addWidget(sub)

        desc = entry.get("desc", entry.get("description", ""))
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; border:none; background:transparent;")
            desc_lbl.setWordWrap(True)
            info.addWidget(desc_lbl)

        lay.addLayout(info, 1)

        btn_install = _btn("⬇ Install", accent=True)
        has_url = bool(entry.get("file_url"))
        btn_install.setEnabled(has_url)
        if not has_url:
            btn_install.setToolTip("No download URL provided")
        btn_install.clicked.connect(lambda _=False, e=entry: self._install_community_plugin(e))
        lay.addWidget(btn_install)
        return card

    def _install_community_plugin(self, entry: dict) -> None:
        """Download, SHA-256 verify, and import a community plugin."""
        file_url  = entry.get("file_url", "")
        expected  = entry.get("sha256", "")
        name      = entry.get("name", "plugin")

        if not file_url:
            self._set_status("No download URL for this plugin.", error=True)
            return

        self._browse_status.setText(f"Downloading {name}…")
        thread = _CommunityDownloadThread(file_url, expected, name, parent=self)
        thread.done.connect(
            lambda path: self._on_community_download_done(path, entry),
            Qt.ConnectionType.QueuedConnection,
        )
        thread.error.connect(
            lambda msg: self._on_community_download_error(msg),
            Qt.ConnectionType.QueuedConnection,
        )
        # Keep a reference so it isn't GC'd
        self._browse_index_thread = thread
        thread.start()

    @pyqtSlot(str)
    def _on_community_download_done(self, plugin_path: str, entry: dict) -> None:
        self._browse_status.setText(f"Downloaded — importing '{entry.get('name', plugin_path)}'…")
        self._import_bundled(plugin_path)

    @pyqtSlot(str)
    def _on_community_download_error(self, msg: str) -> None:
        self._browse_status.setText(f"Download error: {msg}")

    # ── Hub management ────────────────────────────────────────────────────────

    @staticmethod
    def _bundled_plugins_dir() -> Path:
        return Path(__file__).parent.parent.parent / "plugins"

    def _rebuild_hub(self) -> None:
        # Remove all existing card widgets
        while self._hub_lay.count():
            item = self._hub_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        # ── Catalog: bundled plugins not yet imported ─────────────────────────
        self._rebuild_catalog()

        # ── Active integrations ───────────────────────────────────────────────
        instances = _load_instances()

        if not instances:
            empty = QLabel(
                "No hardware imported yet.\n"
                "Click  ＋ Add Integration  to import a script."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px; padding:24px 0;"
            )
            self._hub_lay.addWidget(empty)
        else:
            for inst in instances:
                path = inst["path"]
                ok, _, meta = _validate_script(path)
                if not ok:
                    meta = {"name": Path(path).stem, "type": "unknown", "ip": ""}
                last_result = _load_last_result(inst["id"])
                card = HubCard(
                    path, meta, last_result,
                    instance_id=inst["id"],
                    display_name=inst.get("name", ""),
                    instance_ip=inst.get("ip", ""),
                    parent=self._hub_body,
                )
                card.refresh_clicked.connect(self._run_plugin)
                card.remove_clicked.connect(self._remove_plugin)
                card.stop_clicked.connect(self._stop_poll_worker)
                card.reenable_clicked.connect(self._on_reenable_plugin)
                card.install_completed.connect(self._on_install_completed)
                card.add_another.connect(self._on_add_another_instance)
                card.update_credentials_clicked.connect(self._on_update_credentials)
                card.reimport_clicked.connect(self._on_reimport_plugin)
                card.rename_requested.connect(self._on_rename_card)
                self._hub_lay.addWidget(card)
                # Key by instance_id so multiple instances of same plugin coexist
                self._cards[inst["id"]] = card

        self._hub_lay.addStretch()

    def _rebuild_catalog(self) -> None:
        """Inject catalog cards for bundled plugins that are not yet imported."""
        bdir = self._bundled_plugins_dir()
        if not bdir.is_dir():
            return
        imported = {inst["path"] for inst in _load_instances()}
        entries: list[tuple[str, dict]] = []
        for pyf in sorted(bdir.glob("*_plugin.py")):
            if "template" in pyf.stem.lower():
                continue
            ps = str(pyf)
            if ps in imported:
                continue
            ok, _, meta = _validate_script(ps)
            if ok:
                entries.append((ps, meta))
        if not entries:
            return

        # Section header
        hdr_lbl = QLabel("AVAILABLE PLUGINS")
        hdr_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; font-weight:bold;"
            " letter-spacing:0.5px; padding:4px 8px 2px 8px;"
        )
        self._hub_lay.addWidget(hdr_lbl)

        for path, meta in entries:
            self._hub_lay.addWidget(self._build_catalog_card(path, meta))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border:none; border-top:1px solid {BORDER}; background:transparent;"
        )
        sep.setFixedHeight(1)
        self._hub_lay.addWidget(sep)

    def _build_catalog_card(self, path: str, meta: dict) -> QFrame:
        _TYPE_ICON = {"modem": "📡", "router": "🔀", "ap": "📶",
                      "switch": "🔗", "other": "🔌"}
        card = QFrame()
        card.setObjectName("hubCatalogCard")
        card.setStyleSheet(
            f"QFrame#hubCatalogCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # Use PNG icon if available (P2-3), else fall back to emoji type icon
        icon_path = meta.get("icon_path", "")
        icon_widget_added = False
        if icon_path:
            try:
                px = QPixmap(icon_path).scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                if not px.isNull():
                    icon_lbl = QLabel()
                    icon_lbl.setPixmap(px)
                    icon_lbl.setFixedSize(26, 26)
                    icon_lbl.setStyleSheet("background:transparent; border:none;")
                    lay.addWidget(icon_lbl)
                    icon_widget_added = True
            except Exception:
                pass  # icon load is non-critical — fall back to text emoji below
        if not icon_widget_added:
            icon_lbl = QLabel(_TYPE_ICON.get(meta.get("type", ""), "🔌"))
            icon_lbl.setFixedWidth(22)
            icon_lbl.setStyleSheet("background:transparent; border:none;")
            lay.addWidget(icon_lbl)

        txt = QVBoxLayout()
        txt.setSpacing(1)
        name_lbl = QLabel(meta.get("name", Path(path).stem))
        name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        txt.addWidget(name_lbl)
        desc = meta.get("description", "")
        if desc:
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
            desc_lbl.setWordWrap(True)
            txt.addWidget(desc_lbl)
        lay.addLayout(txt, 1)

        ip_lbl = QLabel(meta.get("ip", ""))
        ip_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; background:transparent; border:none;"
        )
        lay.addWidget(ip_lbl)

        add_btn = QPushButton("＋  Add")
        add_btn.setFixedHeight(26)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            " border-radius:3px; font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        add_btn.clicked.connect(lambda _, p=path: self._import_bundled(p))
        lay.addWidget(add_btn)
        return card

    def _register_plugin(self, path: str, source: str = "browse") -> None:
        """Unified plugin registration pipeline — all entry points call this.

        Steps (always in this order, regardless of source):
        1. Validate script
        2. Check and install PYPI deps
        3. Copy to AppData stable path
        4. Show credential dialog → live test → capture confirmed IP
        5. Write instance registry entry using confirmed IP
        6. Rebuild hub card
        7. Start poll worker
        8. Emit plugin_page_added → nav updates

        source: "browse" | "bundled" | "community" | "nspkg"
        """
        ok, msg, meta = _validate_script(path)
        if not ok:
            self._set_status(f"Validation failed: {msg}", error=True)
            return

        # Step 2: PYPI dependency check and install
        pypi_pkg = meta.get("pypi_package", "")
        if pypi_pkg:
            import importlib.util
            module_name = pypi_pkg.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_pkg, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"'{pypi_pkg}' still not importable — check pip output.",
                        error=True,
                    )
                    return

        # Step 3: copy to stable AppData plugins dir.
        # Bundled/frozen plugins live in a _MEI* temp dir recreated each launch.
        # Browse plugins may be anywhere on disk.  Both are copied once to
        # get_app_data_dir()/plugins/ so the stored path is always valid.
        import shutil as _shutil
        from modules.utils import get_app_data_dir as _gad
        try:
            _dest_dir = _gad() / "plugins"
            _dest_dir.mkdir(parents=True, exist_ok=True)
            _dest = _dest_dir / Path(path).name
            if Path(path).resolve() != _dest.resolve():
                _shutil.copy2(path, _dest)
            path = str(_dest)
        except Exception as _exc:
            self._set_status(f"Failed to install plugin: {_exc}", error=True)
            return

        # Step 4: credential dialog
        cred_label = meta.get("credential_label", "")
        hw_ip      = meta.get("ip", "")
        if cred_label and hw_ip:
            try:
                import keyring as _kr
                existing_pw = _kr.get_password("NetSentinel/hardware", hw_ip)
            except Exception:
                existing_pw = None
            if not existing_pw:
                accepted, confirmed_ip = self._show_credential_dialog(
                    meta.get("name", Path(path).stem), hw_ip, cred_label,
                    plugin_path=path,
                )
                if not accepted:
                    self._set_status("Setup cancelled.", error=True)
                    return
                hw_ip = confirmed_ip or hw_ip

        # Step 5: instance registry
        label   = meta.get("name", Path(path).stem)
        inst_ip = hw_ip
        instances = _load_instances()
        inst_id = _instance_id(path, inst_ip or path)
        is_new  = not any(i["id"] == inst_id for i in instances)
        if is_new:
            instances.append({"id": inst_id, "path": path, "ip": inst_ip, "name": label})
            _save_instances(instances)

        # Steps 6–8: rebuild, start, emit
        self._set_status(f"Imported '{label}' — running first check…", error=False)
        self._rebuild_hub()
        self._start_poll_worker_inst(inst_id)
        if is_new:
            self.plugin_page_added.emit(path, label)

    def _import_bundled(self, path: str) -> None:
        """Add a bundled plugin — delegates to the unified registration pipeline."""
        self._register_plugin(path, source="bundled")

    def _show_credential_dialog(self, name: str, default_ip: str, cred_label: str,
                                plugin_path: str = "") -> tuple[bool, str]:
        """Credential dialog with live connection test.

        Shows IP + password fields.  The primary button ("Test & Add") runs a
        live connection test in a background thread before accepting.  The dialog
        only closes with Accepted after a successful test, so the plugin is never
        registered when it cannot connect.

        Returns (accepted, confirmed_ip).  confirmed_ip is the IP the user
        actually entered (may differ from default_ip), or "" on cancel.
        """
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Set up {name}")
        dlg.setMinimumWidth(400)

        _field_ss = (
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:12px;"
        )
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        note = QLabel(f"Enter the connection details for <b>{name}</b>.")
        note.setTextFormat(Qt.TextFormat.RichText)
        note.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px;")
        note.setWordWrap(True)
        lay.addWidget(note)

        form = QFormLayout()
        form.setSpacing(6)

        ip_edit = QLineEdit(default_ip)
        ip_edit.setStyleSheet(_field_ss)
        ip_edit.setPlaceholderText("e.g. 192.168.1.1")
        form.addRow("IP Address", ip_edit)

        pw_edit = QLineEdit()
        pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pw_edit.setStyleSheet(_field_ss)
        pw_edit.setPlaceholderText(f"Device {cred_label.lower()}")
        form.addRow(cred_label, pw_edit)
        lay.addLayout(form)

        keyring_note = QLabel("🔒  Password saved to OS keychain — never written to disk")
        keyring_note.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        lay.addWidget(keyring_note)

        # ── Status area ───────────────────────────────────────────────────────
        status_lbl = QLabel("")
        status_lbl.setWordWrap(True)
        status_lbl.setVisible(False)
        status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; padding:4px 0;")
        lay.addWidget(status_lbl)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:5px 14px; font-size:12px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        test_btn = QPushButton("Test & Add")
        test_btn.setDefault(True)
        test_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:5px 18px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        btn_row.addWidget(test_btn)
        lay.addLayout(btn_row)

        # "Add Without Testing" — hidden initially; appears after a live-test failure
        # so the user can still register when the device is temporarily offline.
        skip_btn = QPushButton("Add Without Testing")
        skip_btn.setVisible(False)
        skip_btn.setToolTip(
            "Device unreachable — save credentials now and add.\n"
            "The card will show an error until the device comes online."
        )
        skip_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:10px; padding:2px 0; text-decoration:underline; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        lay.addWidget(skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # ── Live-test logic ───────────────────────────────────────────────────
        _tester: list[_PluginConnectionTester] = []

        def _set_status(msg: str, color: str) -> None:
            status_lbl.setText(msg)
            status_lbl.setStyleSheet(
                f"font-size:11px; color:{color}; padding:4px 0; background:transparent;"
            )
            status_lbl.setVisible(True)

        def _save_and_accept() -> None:
            ip = ip_edit.text().strip()
            pw = pw_edit.text().strip()
            if pw:
                try:
                    import keyring as _kr
                    # Per-instance namespace (P4-2)
                    iid = _instance_id(plugin_path or ip, ip)
                    _kr.set_password("NetSentinel/plugin", iid, pw)
                    # Legacy namespace for backwards-compat
                    _kr.set_password("NetSentinel/hardware", ip, pw)
                except Exception:
                    pass  # keyring unavailable — dialog still accepts; plugin will re-prompt later
            dlg.accept()

        def _run_test() -> None:
            ip = ip_edit.text().strip()
            pw = pw_edit.text().strip()
            if not ip:
                _set_status("Enter the device IP address.", RED)
                return
            if not pw:
                _set_status(f"Enter the device {cred_label.lower()} to continue.", RED)
                pw_edit.setFocus()
                return

            test_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            ip_edit.setEnabled(False)
            pw_edit.setEnabled(False)
            skip_btn.setVisible(False)
            _set_status("Testing connection…  ⏳", TEXT_SECONDARY)

            tester = _PluginConnectionTester(plugin_path or "", ip, pw, parent=dlg)
            _tester.append(tester)

            def _on_success(result: dict) -> None:
                _set_status("✓  Connected successfully — adding integration.", GREEN)
                try:
                    import keyring as _kr
                    # Per-instance namespace (P4-2)
                    iid = _instance_id(plugin_path or ip, ip)
                    _kr.set_password("NetSentinel/plugin", iid, pw)
                    # Legacy namespace for backwards-compat
                    _kr.set_password("NetSentinel/hardware", ip, pw)
                except Exception:
                    pass  # keyring unavailable — credential stored in-memory for this session
                QTimer.singleShot(600, dlg.accept)

            def _on_failure(msg: str) -> None:
                try:
                    import keyring as _kr
                    _kr.delete_password("NetSentinel/hardware", ip)
                except Exception:
                    pass  # key may not exist yet; deletion is best-effort
                _set_status(f"✗  {msg}", RED)
                test_btn.setEnabled(True)
                cancel_btn.setEnabled(True)
                ip_edit.setEnabled(True)
                pw_edit.setEnabled(True)
                test_btn.setText("Retry")
                skip_btn.setVisible(True)  # offer skip only after a real failure

            tester.success.connect(_on_success, Qt.ConnectionType.QueuedConnection)
            tester.failure.connect(_on_failure, Qt.ConnectionType.QueuedConnection)
            tester.start()

        skip_btn.clicked.connect(_save_and_accept)
        test_btn.clicked.connect(_run_test)
        pw_edit.returnPressed.connect(_run_test)

        result = dlg.exec()
        confirmed_ip = ip_edit.text().strip()

        # Stop any running tester
        for t in _tester:
            if t.isRunning():
                t.wait(500)

        accepted = result == QDialog.DialogCode.Accepted
        return accepted, (confirmed_ip if accepted else "")

    def _start_all_poll_workers(self) -> None:
        self._migrate_stale_paths()
        for i, inst in enumerate(_load_instances()):
            inst_id = inst["id"]
            QTimer.singleShot(100, lambda iid=inst_id: self._smoke_check_deps_inst(iid))
            QTimer.singleShot(
                i * 3000, lambda iid=inst_id: self._start_poll_worker_inst(iid)
            )

    def _smoke_check_deps(self, path: str) -> None:
        """Check PYPI_PACKAGE dep; set card to error immediately if missing."""
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        pypi_pkg = meta.get("pypi_package", "")
        if not pypi_pkg:
            return
        import importlib.util
        module_name = pypi_pkg.replace("-", "_")
        if importlib.util.find_spec(module_name) is not None:
            return
        err_msg = f"DEPS: {pypi_pkg} not installed. Run: pip install {pypi_pkg}"
        # Cards are keyed by instance_id now; look across all cards for this path
        for inst_id, card in self._cards.items():
            if card._path == path:
                card.set_error(_classify_error(err_msg))

    def _smoke_check_deps_inst(self, instance_id: str) -> None:
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst:
            self._smoke_check_deps(inst["path"])

    def _migrate_stale_paths(self) -> None:
        """Delegate to the module-level _migrate_stale_paths() helper."""
        _migrate_stale_paths()

    def _start_poll_worker(self, path: str) -> None:
        """Start a worker for the first instance whose path matches."""
        for inst in _load_instances():
            if inst["path"] == path:
                self._start_poll_worker_inst(inst["id"])
                return

    def _start_poll_worker_inst(self, instance_id: str) -> None:
        if instance_id in self._poll_workers:
            return
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst is None:
            return
        path = inst["path"]

        # P4-2: verify bundled plugin signature before execution
        try:
            from modules.plugin_tools import verify_signature as _vsig
            _signed, _sig_msg = _vsig(path)
            if "MISMATCH" in _sig_msg:
                card = self._cards.get(instance_id)
                if card:
                    card.set_error(
                        f"ERR: Plugin hash mismatch — possible tampering. "
                        f"Re-import the original plugin or reinstall NetSentinel."
                    )
                return
        except Exception:
            pass  # hash DB unavailable — proceed without check

        ok, _, meta = _validate_script(path)
        hw_type = meta.get("type", "other") if ok else "other"
        saved_config = _load_instance_config(instance_id)
        worker = PluginPollingWorker(
            path=path, hw_type=hw_type,
            instance_id=instance_id,
            instance_ip=inst.get("ip", ""),
            config=saved_config or None,
            parent=self,
        )
        worker.result.connect(
            lambda data, iid=instance_id: self._on_plugin_result(iid, data),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda msg, iid=instance_id: self._on_plugin_error(iid, msg),
            Qt.ConnectionType.QueuedConnection,
        )
        # P3-3: wire log output to the card's console panel
        card = self._cards.get(instance_id)
        if card is not None:
            worker.log_line.connect(
                lambda line, c=card: c.append_log(line),
                Qt.ConnectionType.QueuedConnection,
            )
        worker.start()
        self._poll_workers[instance_id] = worker
        # P6-4: watch plugin file for changes / deletion
        if Path(path).exists() and path not in self._file_watcher.files():
            self._file_watcher.addPath(path)

    def _stop_poll_worker(self, path_or_id: str) -> None:
        """Stop by instance_id (preferred) or by path (legacy)."""
        # Try direct instance_id lookup first
        worker = self._poll_workers.pop(path_or_id, None)
        if worker is None:
            # Fallback: find by path
            for iid, w in list(self._poll_workers.items()):
                if getattr(w, "_path", "") == path_or_id:
                    self._poll_workers.pop(iid, None)
                    worker = w
                    break
        if worker:
            worker.stop()
            worker.wait(2000)

    @pyqtSlot(str)
    def _on_reimport_plugin(self, path: str) -> None:
        """P6-2: Plugin file gone — open file browser so user can locate the new path."""
        self._on_browse()

    @pyqtSlot(str)
    def _on_add_another_instance(self, path: str) -> None:
        """Add a second instance of the same plugin type with a different IP."""
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        cred_label = meta.get("credential_label", "Password")
        default_ip = meta.get("ip", "")
        hw_name    = meta.get("name", Path(path).stem)

        # Show credential dialog; IP field is editable so user sets the new device IP.
        # The confirmed_ip returned is what the user actually typed.
        accepted, confirmed_ip = self._show_credential_dialog(
            f"{hw_name} (new instance)", default_ip, cred_label, plugin_path=path
        )
        if not accepted:
            return

        inst_ip = confirmed_ip or default_ip
        instances = _load_instances()
        existing_names = [i["name"] for i in instances if i["path"] == path]
        idx  = len(existing_names) + 1
        name = f"{hw_name} #{idx}"

        inst_id = _instance_id(path, inst_ip)
        new_inst = {"id": inst_id, "path": path, "ip": inst_ip, "name": name}
        instances.append(new_inst)
        _save_instances(instances)
        self._rebuild_hub()
        self._start_poll_worker_inst(inst_id)
        self.plugin_page_added.emit(path, name)

    @pyqtSlot()
    def _tick_timestamps(self) -> None:
        for card in self._cards.values():
            card.tick_timestamp()

    # ── Plugin execution ──────────────────────────────────────────────────────

    @pyqtSlot(str)
    def _run_plugin(self, path: str) -> None:
        """Trigger an immediate poll — called by Refresh button or import."""
        card = self._cards.get(path)
        if card:
            card.set_refreshing(True)
        worker = self._poll_workers.get(path)
        if worker and worker.isRunning():
            worker.trigger_now()
        else:
            self._start_poll_worker(path)

    def _on_plugin_result(self, instance_id: str, data: dict) -> None:
        ts = time.time()
        data["_ts"] = ts
        data["_instance_id"] = instance_id
        # Resolve path for backwards-compat fields
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        path = inst["path"] if inst else instance_id
        data["_path"] = path
        _save_last_result(instance_id, data)
        err_in_data = (data.get("status") or {}).get("extra", {}).get("error", "")
        if err_in_data:
            h = _record_error(instance_id, err_in_data)
            if h.get("disabled"):
                self._stop_poll_worker(instance_id)
        else:
            _record_success(instance_id)
        card = self._cards.get(instance_id)
        if card:
            card.update_result(data, ts)
            card.refresh_health_ui()
        self.plugin_result.emit(data)

    def _instance_id_for_path(self, path: str) -> "str | None":
        """Return the instance_id whose card._path matches *path*, or None."""
        for iid, card in self._cards.items():
            if card._path == path:
                return iid
        return None

    @pyqtSlot(str)
    def _on_plugin_file_changed(self, path: str) -> None:
        """P6-4: QFileSystemWatcher callback — plugin file was modified or deleted.

        File modified → re-add the watch path (OS removes it after notification on some
        platforms) then trigger an immediate re-poll so the worker picks up the new code.
        File deleted  → emit FILE: error to the card immediately without waiting for the
        next poll cycle.
        """
        if Path(path).exists():
            # OS may have removed the path from the watcher after the change event
            if path not in self._file_watcher.files():
                self._file_watcher.addPath(path)
            # Wake the worker immediately to pick up the edited plugin
            for iid, worker in self._poll_workers.items():
                if getattr(worker, "_path", "") == path and worker.isRunning():
                    worker.trigger_now()
                    break
        else:
            # File deleted — surface the error on the card right away
            inst_id = self._instance_id_for_path(path)
            if inst_id:
                self._on_plugin_error(inst_id, f"FILE: plugin file not found at {path}")

    def _on_plugin_error(self, instance_id: str, msg: str) -> None:
        h = _record_error(instance_id, msg)
        card = self._cards.get(instance_id)
        if card:
            classified = _classify_error(msg)
            card.set_error(classified)
            card.refresh_health_ui()
            if h.get("disabled"):
                self._stop_poll_worker(instance_id)
                card.mark_disabled()

    # ── Health / re-enable / reload ───────────────────────────────────────────

    @pyqtSlot(str)
    def _on_reenable_plugin(self, path: str) -> None:
        """Reset circuit breaker and restart the poll worker."""
        self._start_poll_worker(path)

    @pyqtSlot(str)
    def _on_install_completed(self, path: str) -> None:
        """P1-6: pip install succeeded — reload plugin without restarting the app."""
        import importlib
        importlib.invalidate_caches()
        self._stop_poll_worker(path)
        _reset_health(path)
        card = self._cards.get(path)
        if card:
            card._btn_install.setVisible(False)
            card._btn_reenable.setVisible(False)
            card._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
            card._metrics_lbl.setText("Library installed — reconnecting…")
        QTimer.singleShot(300, lambda p=path: self._start_poll_worker(p))

    @pyqtSlot(str)
    def _on_update_credentials(self, instance_id: str) -> None:
        """P4-1: Re-open credential dialog for an AUTH-error card.

        On success, saves the new credential to the per-instance keyring key
        and restarts the poll worker so it picks up the new password.
        """
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst is None:
            return
        path = inst["path"]
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        cred_label = meta.get("credential_label", "Password")
        hw_name    = inst.get("name") or meta.get("name", Path(path).stem)
        current_ip = inst.get("ip") or meta.get("ip", "")

        accepted, confirmed_ip = self._show_credential_dialog(
            hw_name, current_ip, cred_label, plugin_path=path
        )
        if not accepted:
            return

        # Update stored IP if the user changed it
        if confirmed_ip and confirmed_ip != current_ip:
            instances = _load_instances()
            for i in instances:
                if i["id"] == instance_id:
                    i["ip"] = confirmed_ip
            _save_instances(instances)

        # Reset circuit breaker and restart the worker
        _reset_health(path)
        self._stop_poll_worker(instance_id)
        card = self._cards.get(instance_id)
        if card:
            card._btn_update_cred.setVisible(False)
            card._btn_reenable.setVisible(False)
            card._dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; border:none;")
            card._metrics_lbl.setText("Credentials updated — reconnecting…")
        QTimer.singleShot(300, lambda iid=instance_id: self._start_poll_worker_inst(iid))

    @pyqtSlot(str, str, str)
    def _on_rename_card(self, instance_id: str, old_name: str, new_name: str) -> None:
        """P3-4: Persist display name change and propagate to dashboard nav (plugin_renamed)."""
        instances = _load_instances()
        path = ""
        for inst in instances:
            if inst["id"] == instance_id:
                inst["name"] = new_name
                path = inst.get("path", "")
                break
        if path:
            _save_instances(instances)
            self.plugin_renamed.emit(path, old_name, new_name)

    # ── Import / remove ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _on_create_plugin(self) -> None:
        """P3-2: Template wizard — generate a new plugin .py from user-supplied fields.

        Presents a dialog collecting hardware name, type, IP, credential label,
        optional PyPI package, and author.  On "Create", writes a filled-in
        template to get_app_data_dir()/plugins/ and offers to import it immediately.
        """
        from modules.utils import get_app_data_dir as _gad

        _field_ss = (
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:11px;"
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Create New Plugin")
        dlg.setMinimumWidth(480)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        intro = QLabel(
            "Fill in the fields below and NetSentinel will generate a plugin "
            "template ready for you to complete with your hardware's API calls."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        lay.addWidget(intro)

        from PyQt6.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        name_edit = QLineEdit()
        name_edit.setStyleSheet(_field_ss)
        name_edit.setPlaceholderText("e.g. ASUS RT-AX88U")
        form.addRow("Hardware name *", name_edit)

        type_combo = QComboBox()
        type_combo.addItems(["router", "modem", "ap", "switch", "other"])
        type_combo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 6px; font-size:11px; }}"
            f"QComboBox:drop-down {{ border:none; }}"
        )
        form.addRow("Hardware type *", type_combo)

        ip_edit = QLineEdit()
        ip_edit.setStyleSheet(_field_ss)
        ip_edit.setPlaceholderText("e.g. 192.168.1.1")
        form.addRow("Default IP *", ip_edit)

        cred_edit = QLineEdit()
        cred_edit.setStyleSheet(_field_ss)
        cred_edit.setText("Password")
        form.addRow("Credential label", cred_edit)

        pypi_edit = QLineEdit()
        pypi_edit.setStyleSheet(_field_ss)
        pypi_edit.setPlaceholderText("e.g. fritzconnection  (leave blank if none)")
        form.addRow("PyPI package", pypi_edit)

        author_edit = QLineEdit()
        author_edit.setStyleSheet(_field_ss)
        author_edit.setPlaceholderText("optional — shown in plugin catalog")
        form.addRow("Author", author_edit)

        lay.addLayout(form)

        # Output file path (auto, shown read-only)
        try:
            dest_dir = _gad() / "plugins"
        except Exception:
            dest_dir = Path.home() / ".netsentinel" / "plugins"
        path_lbl = QLabel("")
        path_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; font-family:Consolas;"
        )
        path_lbl.setWordWrap(True)
        lay.addWidget(path_lbl)

        def _update_path_preview(*_):
            raw = name_edit.text().strip()
            slug = (
                raw.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
            )
            slug = "".join(c for c in slug if c.isalnum() or c == "_")
            slug = slug or "my_plugin"
            fname = f"{slug}_plugin.py"
            path_lbl.setText(f"Will be created at: {dest_dir / fname}")

        name_edit.textChanged.connect(_update_path_preview)
        _update_path_preview()

        status_lbl = QLabel("")
        status_lbl.setStyleSheet(f"color:{RED}; font-size:10px;")
        status_lbl.setVisible(False)
        lay.addWidget(status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:5px 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Plugin")
        create_btn.setDefault(True)
        create_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:5px 18px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        btn_row.addWidget(create_btn)
        lay.addLayout(btn_row)

        _created_path: list[str] = []

        def _on_create() -> None:
            hw_name    = name_edit.text().strip()
            hw_type    = type_combo.currentText()
            hw_ip      = ip_edit.text().strip()
            cred_label = cred_edit.text().strip() or "Password"
            pypi_pkg   = pypi_edit.text().strip()
            author     = author_edit.text().strip()

            if not hw_name:
                status_lbl.setText("Hardware name is required.")
                status_lbl.setVisible(True)
                return
            if not hw_ip:
                status_lbl.setText("Default IP is required.")
                status_lbl.setVisible(True)
                return

            slug = (
                hw_name.lower()
                .replace(" ", "_")
                .replace("-", "_")
                .replace("/", "_")
            )
            slug = "".join(c for c in slug if c.isalnum() or c == "_") or "my_plugin"
            fname = f"{slug}_plugin.py"

            # Build file content from _TEMPLATE with substitutions
            content = _TEMPLATE
            content = content.replace(
                'Hardware: <YOUR HARDWARE NAME>', f'Hardware: {hw_name}'
            )
            content = content.replace(
                'Author:   <YOUR NAME>', f'Author:   {author or "Unknown"}'
            )
            content = content.replace(
                'HARDWARE_NAME = "My Router XYZ"     # displayed in the app',
                f'HARDWARE_NAME = "{hw_name}"',
            )
            content = content.replace(
                'HARDWARE_TYPE = "router"            # router | modem | ap | switch | other',
                f'HARDWARE_TYPE = "{hw_type}"',
            )
            content = content.replace(
                'HARDWARE_IP   = "192.168.1.1"       # your device\'s LAN address',
                f'HARDWARE_IP   = "{hw_ip}"',
            )

            # Insert PYPI_PACKAGE and/or CREDENTIAL_LABEL before the credential helper
            extra_consts = ""
            if pypi_pkg:
                extra_consts += f'\nPYPI_PACKAGE    = "{pypi_pkg}"'
            extra_consts += f'\nCREDENTIAL_LABEL = "{cred_label}"'
            if extra_consts:
                content = content.replace(
                    '\n# ── Credentials',
                    extra_consts + '\n\n# ── Credentials',
                )

            # Write to user plugins dir
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / fname
                dest.write_text(content, encoding="utf-8")
                _created_path.append(str(dest))
                dlg.accept()
            except Exception as exc:
                status_lbl.setText(f"Failed to create file: {exc}")
                status_lbl.setVisible(True)

        create_btn.clicked.connect(_on_create)

        if dlg.exec() != QDialog.DialogCode.Accepted or not _created_path:
            return

        created = _created_path[0]
        self._set_status(
            f"Plugin created: {Path(created).name}  "
            "— click ＋ Add Integration to import it.",
            error=False,
        )

        # Offer to open the file in the system editor
        from PyQt6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Plugin Created")
        msg.setText(
            f"<b>{Path(created).name}</b> has been created.<br><br>"
            f"Path: <code>{created}</code><br><br>"
            "Open the file in your default editor to complete the API code, "
            "then click <b>＋ Add Integration</b> to import it."
        )
        msg.setTextFormat(Qt.TextFormat.RichText)
        open_btn = msg.addButton("Open in editor", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() == open_btn:
            import os as _os
            try:
                _os.startfile(created)  # type: ignore[attr-defined]
            except AttributeError:
                import subprocess
                subprocess.Popen(["xdg-open", created])  # noqa: S603

    def _on_import_nspkg(self) -> None:
        """Import a .nspkg plugin bundle (P3-5)."""
        from PyQt6.QtWidgets import QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "Import plugin bundle", "",
            "NetSentinel plugin bundles (*.nspkg);;ZIP files (*.zip)",
        )
        if not path:
            return

        try:
            from modules.nspkg import unpack_nspkg
            from modules.utils import get_app_data_dir
            dest_dir = get_app_data_dir() / "plugins"
            plugin_path, manifest = unpack_nspkg(path, dest_dir)
        except Exception as exc:
            self._set_status(f"Import failed: {exc}", error=True)
            return

        # Treat the extracted .py as a user-supplied script (show consent if unsigned)
        if not _is_consented(str(plugin_path)):
            if not self._show_unsigned_warning(str(plugin_path)):
                return
            _record_consent(str(plugin_path))

        ok, msg, meta = _validate_script(str(plugin_path))
        if not ok:
            self._set_status(f"Bundle plugin invalid: {msg}", error=True)
            return

        name = manifest.get("name") or meta.get("name", plugin_path.stem)
        self._set_status(f"Importing '{name}' from bundle…", error=False)
        self._import_bundled(str(plugin_path))

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select hardware integration script", "",
            "Python files (*.py)",
        )
        if not path:
            return

        # P4-1: one-time unsigned plugin warning for scripts not in the bundled dir
        bundled_dir = self._bundled_plugins_dir()
        is_bundled = Path(path).resolve().parent == bundled_dir.resolve()
        if not is_bundled and not _is_consented(path):
            if not self._show_unsigned_warning(path):
                return
            _record_consent(path)

        self._register_plugin(path, source="browse")

    def _show_unsigned_warning(self, path: str) -> bool:
        """One-time consent dialog shown before adding any non-bundled plugin.

        Returns True when the user clicks 'I understand — Add anyway'.
        The caller records consent so the dialog is not shown again for the same content.
        """
        try:
            sz = Path(path).stat().st_size
            sz_str = f"{sz:,} bytes"
        except Exception:
            sz_str = "unknown size"

        dlg = QDialog(self)
        dlg.setWindowTitle("Untrusted Plugin")
        dlg.setMinimumWidth(460)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        warn_lbl = QLabel(
            "<b>⚠  This plugin runs arbitrary Python code on your machine.</b><br><br>"
            "Only add scripts from sources you trust — for example, scripts you wrote "
            "yourself or obtained from a known community repository.<br><br>"
            "You will <b>not</b> see this warning again for this exact file."
        )
        warn_lbl.setTextFormat(Qt.TextFormat.RichText)
        warn_lbl.setWordWrap(True)
        warn_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px;")
        lay.addWidget(warn_lbl)

        path_lbl = QLabel(f"<b>Path:</b> {path}<br><b>Size:</b> {sz_str}")
        path_lbl.setTextFormat(Qt.TextFormat.RichText)
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet(
            f"background:{BG_DARK}; color:{TEXT_SECONDARY}; font-size:10px; font-family:Consolas;"
            f" border:1px solid {BORDER}; border-radius:3px; padding:6px;"
        )
        lay.addWidget(path_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:5px 14px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        proceed_btn = QPushButton("I understand — Add anyway")
        proceed_btn.setStyleSheet(
            f"QPushButton {{ background:{AMBER}; color:{TEXT_PRIMARY}; border:none;"
            f" border-radius:3px; padding:5px 16px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{AMBER}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{AMBER}; color:{TEXT_PRIMARY}; }}"
        )
        proceed_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(proceed_btn)
        lay.addLayout(btn_row)

        return dlg.exec() == QDialog.DialogCode.Accepted

    @pyqtSlot(str)
    def _remove_plugin(self, path_or_id: str) -> None:
        """Remove by instance_id (preferred) or by path (removes first matching instance)."""
        self._stop_poll_worker(path_or_id)
        instances = _load_instances()
        # Try exact instance_id match first
        remaining = [i for i in instances if i["id"] != path_or_id]
        if len(remaining) == len(instances):
            # No match on id — try path (remove first matching)
            removed = next((i for i in instances if i["path"] == path_or_id), None)
            if removed:
                remaining = [i for i in instances if i["id"] != removed["id"]]
                path_or_id = removed["path"]
        _save_instances(remaining)
        self._set_status(f"Removed {Path(path_or_id).name}.", error=False)
        self._rebuild_hub()
        self.plugin_page_removed.emit(path_or_id)

    # ── Status helper ─────────────────────────────────────────────────────────

    def _set_status(self, text: str, error: bool = False) -> None:
        color = AMBER if error else GREEN
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{color};")
        QTimer.singleShot(5000, lambda: self._status_lbl.setText(""))

    # ── Hardware auto-detection ───────────────────────────────────────────────

    def on_hardware_detected(self, matches: list) -> None:
        """Populate the Suggested tab from catalogue matches.

        Called from dashboard after HwDetectWorker finishes.
        Skips devices that are already installed.
        """
        if self._suggested_lay is None or self._tabs is None:
            return

        from modules.hw_detect import already_installed
        visible = [m for m in matches if not already_installed(m["plugin"].get("id", ""))]

        if not visible:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)
            return

        # Clear previous rows
        while self._suggested_lay.count():
            item = self._suggested_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        imported = set(_load_paths())
        for match in visible:
            plugin     = match["plugin"]
            confidence = match["confidence"]
            signals    = match["signals"]
            # Consider a plugin "already active" if its bundled script is imported
            plugin_file = plugin.get("file", "")
            native_active = bool(plugin_file and any(
                Path(p).name == Path(plugin_file).name for p in imported
            ))
            self._suggested_lay.addWidget(
                self._build_detect_row(plugin, confidence, signals, native_active)
            )

        self._suggested_lay.addStretch()
        n = len(visible)
        self._tabs.setTabText(self._suggested_tab_idx, f"Suggested ({n})")
        self._tabs.setTabVisible(self._suggested_tab_idx, True)

    def _build_detect_row(
        self, plugin: dict, confidence: float, signals: list,
        native_active: bool = False,
    ) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background:transparent; border:none;"
            f" border-bottom:1px solid {BORDER};"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(10)

        # Confidence dot
        dot = QLabel("●")
        if confidence >= 0.7:
            dot.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none;")
            dot.setToolTip(f"Strong match ({confidence:.0%})")
        else:
            dot.setStyleSheet(f"color:{AMBER}; font-size:11px; border:none;")
            dot.setToolTip(f"Possible match ({confidence:.0%})")
        lay.addWidget(dot)

        # Device info
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        info_col.setContentsMargins(0, 0, 0, 0)
        name_lbl = QLabel(f"<b>{plugin.get('name', '?')}</b>  "
                          f"<span style='color:{TEXT_MUTED}; font-size:9px;'>"
                          f"{plugin.get('manufacturer','')}</span>")
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; border:none;")
        sig_lbl = QLabel(" · ".join(signals[:3]))
        sig_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px; border:none;")
        sig_lbl.setWordWrap(True)
        info_col.addWidget(name_lbl)
        info_col.addWidget(sig_lbl)
        lay.addLayout(info_col, 1)

        # Action buttons
        native_page = plugin.get("native_page", "")
        has_bundled = bool(plugin.get("file"))
        has_prompt  = bool(plugin.get("ai_prompt"))

        if native_active and native_page:
            # Device is already supplying live data via its native worker.
            # Show "Open page" instead of Install — no script copy needed.
            status_lbl = QLabel("Active")
            status_lbl.setStyleSheet(
                f"color:{GREEN}; font-size:9px; font-weight:bold; border:none;"
            )
            lay.addWidget(status_lbl)
            btn_open = _btn(f"Open {native_page} →", accent=True)
            btn_open.setFixedHeight(24)
            btn_open.setToolTip(f"Navigate to the {native_page} page")
            btn_open.clicked.connect(lambda _=False, pg=native_page: self.navigate_to.emit(pg))
            lay.addWidget(btn_open)
        else:
            if has_bundled:
                btn_install = _btn("⬇  Install", accent=True)
                btn_install.setFixedHeight(24)
                btn_install.setToolTip(
                    "Copy bundled plugin into your NetSentinel data folder and register it"
                )
                btn_install.clicked.connect(lambda _=False, p=plugin: self._install_from_catalogue(p))
                lay.addWidget(btn_install)

            if has_prompt:
                btn_prompt = _btn("⎘  Copy AI prompt")
                btn_prompt.setFixedHeight(24)
                btn_prompt.setToolTip("Copy a pre-written prompt for an AI to generate this plugin")
                btn_prompt.clicked.connect(
                    lambda _=False, p=plugin: self._copy_ai_prompt(p, btn_prompt)
                )
                lay.addWidget(btn_prompt)

        return row

    def _install_from_catalogue(self, plugin: dict) -> None:
        """Copy a bundled plugin to the user data dir and register it.

        If the plugin requires a PyPI library that is not yet installed,
        opens PipInstallDialog first and only proceeds on success.
        """
        # ── 1. Check / install PyPI dependency ────────────────────────────────
        pypi_lib = plugin.get("pypi_library", "")
        if pypi_lib:
            import importlib.util
            # Map dash-separated package names to their importable module name
            module_name = pypi_lib.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_lib, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                # Verify the library is now importable after pip install
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"Library '{pypi_lib}' still not importable after install — "
                        "check the pip output for errors.",
                        error=True,
                    )
                    return

        # ── 2. Copy the bundled plugin script to the user data dir ────────────
        from modules.hw_detect import bundled_plugin_path
        file_rel = plugin.get("file", "")
        if not file_rel:
            self._set_status("No bundled plugin file for this entry.", error=True)
            return

        src = bundled_plugin_path(file_rel)
        if src is None:
            self._set_status(f"Bundled file not found: {file_rel}", error=True)
            return

        import shutil
        from pathlib import Path as _Path
        try:
            dest_dir = _Path.home() / ".netsentinel" / "plugins"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest != src:
                shutil.copy2(src, dest)
            dest_str = str(dest)
        except Exception as exc:
            self._set_status(f"Copy failed: {exc}", error=True)
            return

        ok, msg, _ = _validate_script(dest_str)
        if not ok:
            self._set_status(f"Plugin validation failed: {msg}", error=True)
            return

        paths = _load_paths()
        is_new = dest_str not in paths
        if is_new:
            paths.append(dest_str)
            _save_paths(paths)

        name = plugin.get("name", src.name)
        self._set_status(f"Installed '{name}' — opening password field…", error=False)
        self._rebuild_hub()
        self._start_poll_worker(dest_str)
        if is_new:
            self.plugin_page_added.emit(dest_str, name)
        # Hide the Suggested tab since the device is now installed
        if self._tabs is not None:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)

    def _copy_ai_prompt(self, plugin: dict, btn: QPushButton) -> None:
        """Copy the catalogue AI prompt to clipboard, replacing {ip} placeholder."""
        prompt = plugin.get("ai_prompt", "")
        default_ip = (plugin.get("fingerprints", {}).get("default_ips") or ["192.168.1.1"])[0]
        prompt = prompt.replace("{ip}", default_ip)
        QApplication.clipboard().setText(prompt)
        orig = btn.text()
        btn.setText("✓  Copied!")
        QTimer.singleShot(2000, lambda: btn.setText(orig))


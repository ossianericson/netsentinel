"""
_HardwareBrowseMixin — community browse tab, bundled catalog, and hardware
auto-detection for HardwareIntegrationPage.

Extracted from hardware_integration_page.py (S14-2).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_CARD,
    BG_DARK, BORDER, CARD_RADIUS, GREEN,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.widgets.hub_card import (
    _btn,
    _CommunityDownloadThread,
    _CommunityIndexThread,
    _load_paths,
    _load_instances,
    _save_paths,
    _validate_script,
)


class _HardwareBrowseMixin:
    """Browse tab (community plugin index), bundled catalog cards, and
    hardware auto-detection / suggested tab for HardwareIntegrationPage."""

    # URL of the community plugin index JSON.
    _DEFAULT_COMMUNITY_URL = (
        "https://raw.githubusercontent.com/netsentinel/"
        "netsentinel-plugins/main/index.json"
    )

    # ── Browse tab (P3-4 community plugin index) ──────────────────────────────

    def _build_browse_tab(self) -> QWidget:
        self._browse_index_thread: Optional[QThread] = None
        tab = QWidget()
        tab.setStyleSheet(f"background:{BG_DARK};")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

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
        if self._browse_index_thread is not None and self._browse_index_thread.isRunning():
            return
        from PyQt6.QtCore import QSettings
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
        self._browse_index_thread = thread
        thread.start()

    @pyqtSlot(str)
    def _on_community_download_done(self, plugin_path: str, entry: dict) -> None:
        self._browse_status.setText(f"Downloaded — importing '{entry.get('name', plugin_path)}'…")
        self._import_bundled(plugin_path)

    @pyqtSlot(str)
    def _on_community_download_error(self, msg: str) -> None:
        self._browse_status.setText(f"Download error: {msg}")

    # ── Bundled catalog cards ─────────────────────────────────────────────────

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
            " border-radius:4px; }"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

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
                pass
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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:11px; padding:0 12px; }"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        add_btn.clicked.connect(lambda _, p=path: self._import_bundled(p))
        lay.addWidget(add_btn)
        return card

    # ── Hardware auto-detection / suggested tab ───────────────────────────────

    def on_hardware_detected(self, matches: list) -> None:
        """Populate the Suggested tab from catalogue matches."""
        if self._suggested_lay is None or self._tabs is None:
            return

        from modules.hw_detect import already_installed
        visible = [m for m in matches if not already_installed(m["plugin"].get("id", ""))]

        if not visible:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)
            return

        while self._suggested_lay.count():
            item = self._suggested_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        imported = set(_load_paths())
        for match in visible:
            plugin     = match["plugin"]
            confidence = match["confidence"]
            signals    = match["signals"]
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

        dot = QLabel("●")
        if confidence >= 0.7:
            dot.setStyleSheet(f"color:{GREEN}; font-size:11px; border:none;")
            dot.setToolTip(f"Strong match ({confidence:.0%})")
        else:
            dot.setStyleSheet(f"color:{AMBER}; font-size:11px; border:none;")
            dot.setToolTip(f"Possible match ({confidence:.0%})")
        lay.addWidget(dot)

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

        native_page = plugin.get("native_page", "")
        has_bundled = bool(plugin.get("file"))
        has_prompt  = bool(plugin.get("ai_prompt"))

        if native_active and native_page:
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
        """Copy a bundled plugin to the user data dir and register it."""
        from ui.widgets.hub_card import PipInstallDialog
        from PyQt6.QtWidgets import QDialog

        pypi_lib = plugin.get("pypi_library", "")
        if pypi_lib:
            import importlib.util
            module_name = pypi_lib.replace("-", "_")
            if importlib.util.find_spec(module_name) is None:
                dlg = PipInstallDialog(pypi_lib, parent=self)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    self._set_status("Dependency install cancelled.", error=True)
                    return
                import importlib
                importlib.invalidate_caches()
                if importlib.util.find_spec(module_name) is None:
                    self._set_status(
                        f"Library '{pypi_lib}' still not importable after install — "
                        "check the pip output for errors.",
                        error=True,
                    )
                    return

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
        if self._tabs is not None:
            self._tabs.setTabVisible(self._suggested_tab_idx, False)

    def _copy_ai_prompt(self, plugin: dict, btn: QPushButton) -> None:
        from PyQt6.QtWidgets import QApplication
        prompt = plugin.get("ai_prompt", "")
        default_ip = (plugin.get("fingerprints", {}).get("default_ips") or ["192.168.1.1"])[0]
        prompt = prompt.replace("{ip}", default_ip)
        QApplication.clipboard().setText(prompt)
        orig = btn.text()
        btn.setText("✓  Copied!")
        QTimer.singleShot(2000, lambda: btn.setText(orig))

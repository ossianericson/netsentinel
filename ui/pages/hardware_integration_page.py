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

import time
from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt, QFileSystemWatcher, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from workers.plugin_polling_worker import PluginPollingWorker
from ui.styles import (
    ACCENT,
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    GREEN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WHITE,
)

from ui.widgets.hub_card import (
    HubCard, PipInstallDialog,
    _btn, _instance_id,
    _validate_script,
    _load_instances, _save_instances,
    _is_consented, _record_consent,
    _migrate_stale_paths,
    _load_last_result, _save_last_result,
    _record_success, _record_error, _reset_health,
    _load_instance_config,
    _classify_error,
    # Re-exported for test compatibility
    _path_hash,
    _load_paths, _save_paths,
    _CommunityIndexThread, _CommunityDownloadThread,
    _ModemDetailPanel, _RouterDetailPanel, _safe_set_text,
    _CIRCUIT_BREAK_THRESHOLD, _DEGRADED_HOURS, _load_health, _save_health,
)
from ui.pages.plugin_guide import PluginGuide
from ui.widgets.credential_dialog import show_credential_dialog, show_unsigned_warning
from ui.pages.plugin_wizard_mixin import _PluginWizardMixin
from ui.pages.hardware_browse_mixin import _HardwareBrowseMixin


class HardwareIntegrationPage(QWidget, _HardwareBrowseMixin, _PluginWizardMixin):
    """Hardware Hub — live status dashboard for all imported hardware plugins."""

    # data dict has "_path" embedded so dashboard knows which plugin
    plugin_result     = pyqtSignal(dict)
    plugin_page_added = pyqtSignal(str, str)   # (script_path, display_label)
    plugin_page_removed = pyqtSignal(str)      # script_path
    plugin_renamed    = pyqtSignal(str, str, str)  # (path, old_label, new_label)
    navigate_to       = pyqtSignal(str)
    geo_map_ip        = pyqtSignal(str)
    port_scan_ip      = pyqtSignal(str)
    check_abuse_ip    = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._poll_workers: Dict[str, PluginPollingWorker] = {}
        self._cards:   Dict[str, HubCard] = {}
        self._tabs: Optional[QTabWidget] = None
        self._suggested_tab_idx: int = 1
        self._suggested_lay: Optional[QVBoxLayout] = None

        self._build_ui()

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self._tick_timestamps)
        self._tick_timer.start()

        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_plugin_file_changed)

        self._start_all_poll_workers()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(8)

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

        self._btn_nspkg = _btn("⬡  Import .nspkg")
        self._btn_nspkg.setToolTip("Import a .nspkg plugin bundle (ZIP containing plugin.py + manifest.json)")
        self._btn_nspkg.clicked.connect(self._on_import_nspkg)
        hdr_row.addWidget(self._btn_nspkg)

        root.addLayout(hdr_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        root.addWidget(self._status_lbl)

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

        # ── Tab 0: Hardware (HubCards + guide) ───────────────────────────────
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

        if not _load_instances():
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
        self._browse_tab_idx = self._tabs.addTab(self._build_browse_tab(), "Browse")

    def _toggle_guide(self) -> None:
        visible = not self._guide_area.isVisible()
        self._guide_area.setVisible(visible)
        self._guide_toggle.setText(
            "▼  How to write a plugin script" if visible
            else "▶  How to write a plugin script"
        )

    # ── Hub management ────────────────────────────────────────────────────────

    @staticmethod
    def _bundled_plugins_dir() -> Path:
        return Path(__file__).parent.parent.parent / "plugins"

    def _rebuild_hub(self) -> None:
        while self._hub_lay.count():
            item = self._hub_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        self._rebuild_catalog()

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
                self._cards[inst["id"]] = card

        self._hub_lay.addStretch()

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
        """
        ok, msg, meta = _validate_script(path)
        if not ok:
            self._set_status(f"Validation failed: {msg}", error=True)
            return

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

        cred_label = meta.get("credential_label", "")
        hw_ip      = meta.get("ip", "")
        if cred_label and hw_ip:
            try:
                import keyring as _kr
                existing_pw = _kr.get_password("NetSentinel/hardware", hw_ip)
            except Exception:
                existing_pw = None
            if not existing_pw:
                accepted, confirmed_ip = show_credential_dialog(
                    self, meta.get("name", Path(path).stem), hw_ip, cred_label,
                    plugin_path=path,
                )
                if not accepted:
                    self._set_status("Setup cancelled.", error=True)
                    return
                hw_ip = confirmed_ip or hw_ip

        label   = meta.get("name", Path(path).stem)
        inst_ip = hw_ip
        instances = _load_instances()
        inst_id = _instance_id(path, inst_ip or path)
        is_new  = not any(i["id"] == inst_id for i in instances)
        if is_new:
            instances.append({"id": inst_id, "path": path, "ip": inst_ip, "name": label})
            _save_instances(instances)

        self._set_status(f"Imported '{label}' — running first check…", error=False)
        self._rebuild_hub()
        self._start_poll_worker_inst(inst_id)
        if is_new:
            self.plugin_page_added.emit(path, label)

    def _import_bundled(self, path: str) -> None:
        self._register_plugin(path, source="bundled")

    def _start_all_poll_workers(self) -> None:
        self._migrate_stale_paths()
        for i, inst in enumerate(_load_instances()):
            inst_id = inst["id"]
            QTimer.singleShot(100, lambda iid=inst_id: self._smoke_check_deps_inst(iid))
            QTimer.singleShot(
                i * 3000, lambda iid=inst_id: self._start_poll_worker_inst(iid)
            )

    def _smoke_check_deps(self, path: str) -> None:
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
        for inst_id, card in self._cards.items():
            if card._path == path:
                card.set_error(_classify_error(err_msg))

    def _smoke_check_deps_inst(self, instance_id: str) -> None:
        inst = next((i for i in _load_instances() if i["id"] == instance_id), None)
        if inst:
            self._smoke_check_deps(inst["path"])

    def _migrate_stale_paths(self) -> None:
        _migrate_stale_paths()

    def _start_poll_worker(self, path: str) -> None:
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

        try:
            from modules.plugin_tools import verify_signature as _vsig
            _signed, _sig_msg = _vsig(path)
            if "MISMATCH" in _sig_msg:
                card = self._cards.get(instance_id)
                if card:
                    card.set_error(
                        "ERR: Plugin hash mismatch — possible tampering. "
                        "Re-import the original plugin or reinstall NetSentinel."
                    )
                return
        except Exception:
            pass

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
        card = self._cards.get(instance_id)
        if card is not None:
            worker.log_line.connect(
                lambda line, c=card: c.append_log(line),
                Qt.ConnectionType.QueuedConnection,
            )
        worker.start()
        self._poll_workers[instance_id] = worker
        if Path(path).exists() and path not in self._file_watcher.files():
            self._file_watcher.addPath(path)

    def _stop_poll_worker(self, path_or_id: str) -> None:
        worker = self._poll_workers.pop(path_or_id, None)
        if worker is None:
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
        self._on_browse()

    @pyqtSlot(str)
    def _on_add_another_instance(self, path: str) -> None:
        ok, _, meta = _validate_script(path)
        if not ok:
            return
        cred_label = meta.get("credential_label", "Password")
        default_ip = meta.get("ip", "")
        hw_name    = meta.get("name", Path(path).stem)

        accepted, confirmed_ip = show_credential_dialog(
            self, f"{hw_name} (new instance)", default_ip, cred_label, plugin_path=path
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
        for iid, card in self._cards.items():
            if card._path == path:
                return iid
        return None

    @pyqtSlot(str)
    def _on_plugin_file_changed(self, path: str) -> None:
        """P6-4: QFileSystemWatcher callback — plugin file modified or deleted."""
        if Path(path).exists():
            if path not in self._file_watcher.files():
                self._file_watcher.addPath(path)
            for iid, worker in self._poll_workers.items():
                if getattr(worker, "_path", "") == path and worker.isRunning():
                    worker.trigger_now()
                    break
        else:
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
        self._start_poll_worker(path)

    @pyqtSlot(str)
    def _on_install_completed(self, path: str) -> None:
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
        """P4-1: Re-open credential dialog for an AUTH-error card."""
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

        accepted, confirmed_ip = show_credential_dialog(
            self, hw_name, current_ip, cred_label, plugin_path=path
        )
        if not accepted:
            return

        if confirmed_ip and confirmed_ip != current_ip:
            instances = _load_instances()
            for i in instances:
                if i["id"] == instance_id:
                    i["ip"] = confirmed_ip
            _save_instances(instances)

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

    def _on_import_nspkg(self) -> None:
        """Import a .nspkg plugin bundle (P3-5)."""
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

        if not _is_consented(str(plugin_path)):
            if not show_unsigned_warning(self, str(plugin_path)):
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

        bundled_dir = self._bundled_plugins_dir()
        is_bundled = Path(path).resolve().parent == bundled_dir.resolve()
        if not is_bundled and not _is_consented(path):
            if not show_unsigned_warning(self, path):
                return
            _record_consent(path)

        self._register_plugin(path, source="browse")

    @pyqtSlot(str)
    def _remove_plugin(self, path_or_id: str) -> None:
        self._stop_poll_worker(path_or_id)
        instances = _load_instances()
        remaining = [i for i in instances if i["id"] != path_or_id]
        if len(remaining) == len(instances):
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

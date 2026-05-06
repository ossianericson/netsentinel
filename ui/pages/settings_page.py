"""
SettingsPage — Application settings and customisation hub.

This is the primary place for all user-facing customisation:
  - Colour theme picker (front-and-centre)
  - Display preferences
  - Keyboard-shortcut reminder

Architecture rules observed:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread.
  • QSettings used for persistence (same org/app as rest of codebase).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import ui.styles as _styles
from ui.styles import (
    ACCENT, ACCENT_DARK, BG_ALT_ROW, BG_CARD, BG_DARK, BORDER,
    BTN_HOVER_BG, CARD_HDR_BORDER, CARD_RADIUS, GREEN, NAV_BAR, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── Background workers for plugin marketplace ─────────────────────────────────

class _FetchRegistryWorker(QThread):
    """Fetch the community plugin registry off the main thread."""
    ready = pyqtSignal(list)   # List[RegistryEntry]
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from modules.plugin_registry import fetch_registry
            entries = fetch_registry(self._url)
            self.ready.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class _InstallWorker(QThread):
    """Download and install one plugin off the main thread."""
    done  = pyqtSignal(str)         # plugin name
    error = pyqtSignal(str, str)    # plugin name, error message

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import install_plugin
            install_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


class _UninstallWorker(QThread):
    """Remove a plugin file off the main thread."""
    done  = pyqtSignal(str)       # plugin name
    error = pyqtSignal(str, str)  # plugin name, error message

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import uninstall_plugin
            uninstall_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


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
    """Return (card QFrame, body QVBoxLayout) styled per design system."""
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
    )
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    tb = QFrame()
    tb.setFixedHeight(32)
    tb.setStyleSheet(
        f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};"
    )
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
    )
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)

    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(10)
    cl.addWidget(body)
    return card, bl


class SettingsPage(QWidget):
    """
    Dedicated settings and customisation page shown in the sidebar.
    Contains the theme picker, display preferences, and shortcuts reference.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(_page_header(
            "Settings & Customisation",
            "Change the colour theme, display preferences, and more",
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 12, 20)
        bl.setSpacing(12)

        bl.addWidget(self._build_appearance_card())
        bl.addWidget(self._build_display_card())
        bl.addWidget(self._build_tray_card())
        bl.addWidget(self._build_plugin_marketplace_card())
        bl.addWidget(self._build_shortcuts_card())
        bl.addStretch()

        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_card(self) -> QFrame:
        card, bl = _card("Appearance — Colour Theme")

        desc = QLabel(
            "Choose a colour theme for the entire application. "
            "The change takes effect after restarting NetSentinel."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(desc)

        self._theme_status_lbl = QLabel("")
        self._theme_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._theme_btns: dict[str, QPushButton] = {}

        for name in _styles.THEMES:
            btn = QPushButton(name)
            self._theme_btns[name] = btn
            btn_row.addWidget(btn)
            btn.clicked.connect(lambda checked=False, n=name: self._on_theme(n))

        btn_row.addStretch()
        bl.addLayout(btn_row)
        bl.addWidget(self._theme_status_lbl)

        self._refresh_theme_buttons()
        return card

    def _refresh_theme_buttons(self):
        active = _styles.get_active_theme_name()
        for name, btn in self._theme_btns.items():
            if name == active:
                btn.setStyleSheet(
                    f"QPushButton{{background:{ACCENT};color:{NAV_BAR};"
                    f"border:1px solid {ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
                    f"border:1px solid {ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;}}"
                    f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
                )

    def _on_theme(self, name: str):
        _styles.set_active_theme_name(name)
        self._refresh_theme_buttons()
        self._theme_status_lbl.setText(
            f"Theme '{name}' saved — restart NetSentinel to apply."
        )

    # ── Display preferences ───────────────────────────────────────────────────

    def _build_display_card(self) -> QFrame:
        card, bl = _card("Display Preferences")

        qs = QSettings("NetSentinel", "NetSentinel")

        self._chk_compact = QCheckBox("Compact table rows (24 px — more devices visible)")
        self._chk_compact.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_compact.setChecked(
            qs.value("display/compact_rows", True, type=bool)
        )
        self._chk_compact.toggled.connect(self._on_compact_toggled)
        bl.addWidget(self._chk_compact)

        self._chk_tooltips = QCheckBox("Show extended tooltips on hover (400 ms delay)")
        self._chk_tooltips.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tooltips.setChecked(
            qs.value("display/tooltips_enabled", True, type=bool)
        )
        self._chk_tooltips.toggled.connect(self._on_tooltip_toggled)
        bl.addWidget(self._chk_tooltips)

        note = QLabel(
            "Row height and tooltip settings take effect the next time a table is populated."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_compact_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("display/compact_rows", checked)

    def _on_tooltip_toggled(self, checked: bool):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("display/tooltips_enabled", checked)

    # ── System Tray & Startup ─────────────────────────────────────────────────

    def _build_tray_card(self) -> QFrame:
        import sys
        from ui.system_tray import get_run_on_startup, set_run_on_startup

        card, bl = _card("System Tray & Startup")

        qs = QSettings("NetSentinel", "NetSentinel")

        # Minimize to tray
        self._chk_tray = QCheckBox(
            "Minimize to system tray on close  "
            "(app keeps running in the background)"
        )
        self._chk_tray.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tray.setChecked(qs.value("tray/minimize_to_tray", True, type=bool))
        self._chk_tray.toggled.connect(self._on_tray_toggled)
        bl.addWidget(self._chk_tray)

        # Run on startup (Windows only)
        self._chk_startup = QCheckBox(
            "Start NetSentinel automatically when Windows starts  "
            "(launches minimised to tray)"
        )
        self._chk_startup.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        if sys.platform != "win32":
            self._chk_startup.setEnabled(False)
            self._chk_startup.setToolTip("Startup registration is only available on Windows")
        else:
            self._chk_startup.setChecked(get_run_on_startup())
        self._chk_startup.toggled.connect(self._on_startup_toggled)
        bl.addWidget(self._chk_startup)

        # ── Notification opt-ins ───────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-height:1px; border:none;")
        bl.addWidget(sep)

        notif_lbl = QLabel("Notifications  (all off by default)")
        notif_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_PRIMARY}; background:transparent;"
        )
        bl.addWidget(notif_lbl)

        self._chk_notify_new_device = QCheckBox(
            "Notify when a new device joins the network"
        )
        self._chk_notify_new_device.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_new_device.setChecked(
            qs.value("tray/notify_new_device", False, type=bool)
        )
        self._chk_notify_new_device.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_new_device", v)
        )
        bl.addWidget(self._chk_notify_new_device)

        self._chk_notify_gone = QCheckBox(
            "Notify when a known device leaves the network"
        )
        self._chk_notify_gone.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_gone.setChecked(
            qs.value("tray/notify_device_gone", False, type=bool)
        )
        self._chk_notify_gone.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_device_gone", v)
        )
        bl.addWidget(self._chk_notify_gone)

        note = QLabel(
            "Alert-rule notifications (ARP attacks, HIGH-risk devices, custom rules) "
            "are configured per-rule in the Alerts tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        bl.addWidget(note)
        return card

    def _on_tray_toggled(self, checked: bool) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("tray/minimize_to_tray", checked)
        # Also update the live tray manager if reachable
        try:
            from PyQt6.QtWidgets import QApplication
            win = QApplication.instance().activeWindow()
            if win is None:
                # Try main window via topLevelWidgets
                for w in QApplication.instance().topLevelWidgets():
                    if hasattr(w, "_tray_manager"):
                        win = w
                        break
            if win and hasattr(win, "_tray_manager"):
                win._tray_manager.set_minimize_to_tray(checked)
        except Exception:
            pass

    def _on_startup_toggled(self, checked: bool) -> None:
        from ui.system_tray import set_run_on_startup
        set_run_on_startup(checked)

    # ── Plugin Marketplace ────────────────────────────────────────────────────

    def _build_plugin_marketplace_card(self) -> QFrame:
        from modules.plugin_registry import REGISTRY_URL
        card, bl = _card("Community Plugins — Browse & Install")

        desc = QLabel(
            "Browse community plugins hosted on GitHub. "
            "Click Install to download a plugin to your local plugins folder."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)

        # Registry URL row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_lbl = QLabel("Registry URL:")
        url_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};")
        url_lbl.setFixedWidth(90)
        self._pm_url = QLineEdit(REGISTRY_URL)
        self._pm_url.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};border:1px solid {BORDER};padding:2px 6px;"
        )
        url_row.addWidget(url_lbl)
        url_row.addWidget(self._pm_url, 1)
        bl.addLayout(url_row)

        # Toolbar
        tb_row = QHBoxLayout()
        tb_row.setSpacing(6)

        _btn_qss = (
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
            f"border:1px solid {ACCENT};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        self._pm_btn_refresh = QPushButton("↻  Refresh")
        self._pm_btn_refresh.setStyleSheet(_btn_qss)
        self._pm_btn_refresh.clicked.connect(self._pm_refresh)

        self._pm_btn_install = QPushButton("▼  Install")
        self._pm_btn_install.setStyleSheet(_btn_qss)
        self._pm_btn_install.setEnabled(False)
        self._pm_btn_install.clicked.connect(self._pm_install_selected)

        self._pm_btn_uninstall = QPushButton("✕  Uninstall")
        self._pm_btn_uninstall.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{RED};"
            f"border:1px solid {RED};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:#FFF0F0;}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_btn_uninstall.clicked.connect(self._pm_uninstall_selected)

        self._pm_btn_folder = QPushButton("📁  Open Plugins Folder")
        self._pm_btn_folder.setStyleSheet(_btn_qss)
        self._pm_btn_folder.clicked.connect(self._pm_open_folder)

        tb_row.addWidget(self._pm_btn_refresh)
        tb_row.addWidget(self._pm_btn_install)
        tb_row.addWidget(self._pm_btn_uninstall)
        tb_row.addStretch()
        tb_row.addWidget(self._pm_btn_folder)
        bl.addLayout(tb_row)

        # Table
        self._pm_table = QTableWidget(0, 5)
        self._pm_table.setHorizontalHeaderLabels(["Name", "Author", "Tags", "Version", "Status"])
        self._pm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._pm_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._pm_table.verticalHeader().setDefaultSectionSize(24)
        self._pm_table.verticalHeader().setVisible(False)
        self._pm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._pm_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._pm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pm_table.setAlternatingRowColors(True)
        self._pm_table.setMinimumHeight(160)
        self._pm_table.setStyleSheet(
            f"QTableWidget{{font-size:11px;background:{BG_CARD};border:1px solid {BORDER};}}"
            f"QHeaderView::section{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"font-size:11px;font-weight:bold;border:none;"
            f"border-bottom:1px solid {BORDER};padding:3px 6px;}}"
            f"QTableWidget::item:selected{{background:{ACCENT};color:white;}}"
        )
        self._pm_table.itemSelectionChanged.connect(self._pm_on_selection)
        bl.addWidget(self._pm_table)

        # Status label
        self._pm_status = QLabel("Click ↻ Refresh to load the community plugin registry.")
        self._pm_status.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(self._pm_status)

        self._pm_entries: list = []
        self._pm_workers: list = []   # keep references so GC doesn't kill them
        return card

    # ── Plugin marketplace slots ──────────────────────────────────────────────

    def _pm_refresh(self) -> None:
        self._pm_btn_refresh.setEnabled(False)
        self._pm_status.setText("Fetching registry…")
        url = self._pm_url.text().strip()
        worker = _FetchRegistryWorker(url, parent=self)
        worker.ready.connect(self._pm_on_registry_ready)
        worker.error.connect(self._pm_on_registry_error)
        worker.finished.connect(lambda: self._pm_btn_refresh.setEnabled(True))
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_registry_ready(self, entries: list) -> None:
        from modules.plugin_registry import is_installed
        self._pm_entries = entries
        self._pm_table.setRowCount(0)
        for e in entries:
            row = self._pm_table.rowCount()
            self._pm_table.insertRow(row)

            installed = is_installed(e)
            dot_color = GREEN if installed else TEXT_MUTED
            dot_text  = "● Installed" if installed else "○ Available"

            for col, text in enumerate([
                e.name, e.author, e.tag_str, e.version,
            ]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._pm_table.setItem(row, col, item)

            status_item = QTableWidgetItem(dot_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            from PyQt6.QtGui import QColor
            status_item.setForeground(QColor(dot_color))
            self._pm_table.setItem(row, 4, status_item)

        self._pm_status.setText(
            f"Loaded {len(entries)} plugin{'s' if len(entries) != 1 else ''} from registry."
        )

    def _pm_on_registry_error(self, msg: str) -> None:
        self._pm_status.setText(f"Error: {msg}")

    def _pm_on_selection(self) -> None:
        rows = self._pm_table.selectedItems()
        has_sel = bool(rows)
        self._pm_btn_install.setEnabled(has_sel)
        self._pm_btn_uninstall.setEnabled(has_sel)

    def _pm_install_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_install.setEnabled(False)
        self._pm_status.setText(f"Installing {entry.name}…")
        worker = _InstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_install_done)
        worker.error.connect(self._pm_on_install_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_install_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} installed successfully.")
        self._pm_on_registry_ready(self._pm_entries)   # refresh status dots

    def _pm_on_install_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(f"Error installing {name}: {msg}")
        self._pm_btn_install.setEnabled(True)

    def _pm_uninstall_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_status.setText(f"Removing {entry.name}…")
        worker = _UninstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_uninstall_done)
        worker.error.connect(self._pm_on_uninstall_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_uninstall_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} uninstalled.")
        self._pm_on_registry_ready(self._pm_entries)

    def _pm_on_uninstall_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(f"Error removing {name}: {msg}")
        self._pm_btn_uninstall.setEnabled(True)

    def _pm_open_folder(self) -> None:
        import subprocess, sys
        from modules.plugin_system import plugins_dir
        path = plugins_dir()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ── Shortcuts reference ───────────────────────────────────────────────────

    def _build_shortcuts_card(self) -> QFrame:
        card, bl = _card("Keyboard Shortcuts")

        shortcuts = [
            ("Ctrl + R",           "Run full scan"),
            ("Ctrl + E",           "Export last scan results"),
            ("Ctrl + Q",           "Quit application"),
            ("F5",                 "Refresh current page"),
            ("Right-click",        "Context menu on any table row"),
            ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix mode)"),
        ]

        for i, (key, desc) in enumerate(shortcuts):
            row_w = QWidget()
            row_w.setStyleSheet(
                f"background:{BG_ALT_ROW if i % 2 else BG_CARD};"
            )
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 3, 0, 3)
            row_l.setSpacing(12)

            k = QLabel(key)
            k.setFixedWidth(150)
            k.setStyleSheet(
                f"font-family:Consolas;font-size:10px;color:{ACCENT_DARK};"
                f"background:transparent;"
            )
            d = QLabel(desc)
            d.setStyleSheet(
                f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
            )
            row_l.addWidget(k)
            row_l.addWidget(d, 1)
            bl.addWidget(row_w)

        return card

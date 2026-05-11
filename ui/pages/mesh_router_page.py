"""Mesh & Router page — live client data from gateway and mesh nodes.

Supports TP-Link Deco today; architecture allows future Eero, Google Nest,
Asus ZenWiFi, Netgear Orbi providers via the MeshWorker provider key.

Password security
-----------------
Passwords are stored ONLY in the OS credential manager via `keyring`.
They are NEVER written to files, config, or environment variables.
If keyring is unavailable the user is warned once and asked each time.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore    import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BORDER, BG_CARD, GREEN,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "NetSentinel/mesh"


# ── keyring helpers (module-level, checked once) ───────────────────────────────

def _keyring_available() -> bool:
    """Return True if the platform has a usable keyring backend."""
    try:
        import keyring
        kr = keyring.get_keyring()
        # The fail / null backends mean no real storage is available
        return type(kr).__name__ not in ("FailKeyring", "NullKeyring", "PlaintextKeyring")
    except Exception:
        return False


def _keyring_load(host: str) -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, host)
    except Exception:
        return None


def _keyring_save(host: str, password: str) -> bool:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, host, password)
        return True
    except Exception as exc:
        log.warning("keyring save failed: %s", exc)
        return False


def _keyring_delete(host: str) -> bool:
    try:
        import keyring
        from keyring.errors import PasswordDeleteError
        keyring.delete_password(_KEYRING_SERVICE, host)
        return True
    except Exception:
        return False


# ── helpers ────────────────────────────────────────────────────────────────────

def _table(headers: list[str]) -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
        f" border:none; gridline-color:{BORDER}; font-size:12px; }}"
        f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
        f" font-size:11px; font-weight:bold; border:none;"
        f" border-bottom:1px solid {BORDER}; padding:4px 8px; }}"
        f"QTableWidget::item {{ padding:4px 8px; }}"
        f"QTableWidget::item:selected {{ background:{ACCENT}; color:{WHITE}; }}"
    )
    return t


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("meshCard")
    card.setStyleSheet(
        f"QFrame#meshCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:0px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:none;"
        f" border-bottom:1px solid {BORDER}; }}"
    )
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 6, 12, 6)
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        " letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(lbl)
    hdr_lay.addStretch()
    outer.addWidget(hdr)

    body = QVBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    outer.addLayout(body, 1)
    return card, body


def _empty(msg: str) -> QLabel:
    lbl = QLabel(msg)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"color:{TEXT_MUTED}; font-size:13px; padding:40px;"
        " background:transparent; border:none;"
    )
    return lbl


# ── page ───────────────────────────────────────────────────────────────────────

class MeshRouterPage(QWidget):
    """
    Dedicated page for querying gateway and mesh system APIs.

    Emits scan_done(dict) when a scan completes so the dashboard can
    cross-enrich the Devices on Network table with node/band information.
    """

    scan_done = pyqtSignal(dict)

    # Class-level flag so the keyring warning shows once per app session
    _keyring_warned: bool = False

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._worker      = None
        self._keyring_ok  = _keyring_available()
        self._setup_ui()
        self._prepopulate_gateway()

    # ── layout ────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── header ────────────────────────────────────────────────────────────
        title = QLabel("Mesh & Router")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; border:none;"
        )
        sub = QLabel(
            "Live client data from your gateway and mesh nodes  "
            "(TP-Link Deco · more manufacturers coming)"
        )
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; border:none;")
        root.addWidget(title)
        root.addWidget(sub)

        compat = QFrame()
        compat.setStyleSheet(
            f"QFrame {{ background:#1A2A3A; border:1px solid #2A4A6A;"
            f" border-left:3px solid {ACCENT}; border-radius:0px; }}"
        )
        compat_lay = QHBoxLayout(compat)
        compat_lay.setContentsMargins(12, 6, 12, 6)
        compat_lbl = QLabel(
            "ℹ  Tested with <b>TP-Link Deco XE75</b>. Other mesh systems (Eero, Orbi, UniFi) "
            "can be added by implementing the same worker interface — "
            "see <code>workers/mesh_worker.py</code>."
        )
        compat_lbl.setTextFormat(Qt.TextFormat.RichText)
        compat_lbl.setWordWrap(True)
        compat_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;"
        )
        compat_lay.addWidget(compat_lbl)
        root.addWidget(compat)

        # ── config card (two rows) ────────────────────────────────────────────
        cfg_card = QFrame()
        cfg_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:0px; padding:0px; }}"
        )
        cfg_card_lay = QVBoxLayout(cfg_card)
        cfg_card_lay.setContentsMargins(0, 0, 0, 0)
        cfg_card_lay.setSpacing(0)

        # Row 1 — connection inputs
        row1 = QFrame()
        row1.setStyleSheet("QFrame { border:none; background:transparent; }")
        row1_lay = QHBoxLayout(row1)
        row1_lay.setContentsMargins(12, 8, 12, 8)
        row1_lay.setSpacing(8)

        _ip_label = QLabel("Gateway IP")
        _ip_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;")
        row1_lay.addWidget(_ip_label)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("192.168.68.1")
        self._ip_edit.setFixedWidth(140)
        self._ip_edit.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:12px;"
        )
        row1_lay.addWidget(self._ip_edit)

        _pw_label = QLabel("Password")
        _pw_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;")
        row1_lay.addWidget(_pw_label)

        self._pw_edit = QLineEdit()
        self._pw_edit.setPlaceholderText("TP-Link ID password")
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setFixedWidth(160)
        self._pw_edit.setStyleSheet(self._ip_edit.styleSheet())
        row1_lay.addWidget(self._pw_edit)

        self._scan_btn = QPushButton("▶  Scan")
        self._scan_btn.setFixedHeight(28)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:12px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        row1_lay.addWidget(self._scan_btn)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        row1_lay.addWidget(self._status_lbl, 1)

        cfg_card_lay.addWidget(row1)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"border:none; border-top:1px solid {BORDER}; background:transparent;")
        div.setFixedHeight(1)
        cfg_card_lay.addWidget(div)

        # Row 2 — keyring controls
        row2 = QFrame()
        row2.setStyleSheet("QFrame { border:none; background:transparent; }")
        row2_lay = QHBoxLayout(row2)
        row2_lay.setContentsMargins(12, 6, 12, 6)
        row2_lay.setSpacing(12)

        self._remember_cb = QCheckBox("Remember in OS Keychain")
        self._remember_cb.setChecked(self._keyring_ok)
        self._remember_cb.setEnabled(self._keyring_ok)
        self._remember_cb.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        row2_lay.addWidget(self._remember_cb)

        self._forget_btn = QPushButton("Forget Saved Password")
        self._forget_btn.setFixedHeight(24)
        self._forget_btn.setEnabled(False)   # enabled only when keyring entry exists
        self._forget_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._forget_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:1px solid {AMBER};"
            " border-radius:3px; font-size:11px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{AMBER}; color:#000; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; border-color:{BORDER}; }}"
        )
        self._forget_btn.clicked.connect(self._on_forget_clicked)
        row2_lay.addWidget(self._forget_btn)

        self._keyring_info_lbl = QLabel()
        self._keyring_info_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        self._keyring_info_lbl.setVisible(False)
        row2_lay.addWidget(self._keyring_info_lbl, 1)

        cfg_card_lay.addWidget(row2)
        root.addWidget(cfg_card)

        # ── keyring warning banner (shown once if no backend) ─────────────────
        if not self._keyring_ok and not MeshRouterPage._keyring_warned:
            MeshRouterPage._keyring_warned = True
            warn = QFrame()
            warn.setStyleSheet(
                f"QFrame {{ background:#3a2800; border:1px solid {AMBER};"
                " border-radius:0px; padding:0px; }}"
            )
            warn_lay = QHBoxLayout(warn)
            warn_lay.setContentsMargins(12, 8, 12, 8)
            warn_lbl = QLabel(
                "⚠  No keyring backend found — password will be asked every time "
                "and NOT saved. Install a keyring backend to enable secure storage."
            )
            warn_lbl.setStyleSheet(
                f"color:{AMBER}; font-size:11px; background:transparent; border:none;"
            )
            warn_lbl.setWordWrap(True)
            warn_lay.addWidget(warn_lbl)
            root.addWidget(warn)

        # ── nodes card ────────────────────────────────────────────────────────
        nodes_card, nodes_body = _card("Mesh Nodes")
        self._nodes_table = _table(["Name", "MAC Address", "IP Address", "Role"])
        self._nodes_table.setColumnWidth(0, 200)
        self._nodes_table.setColumnWidth(1, 160)
        self._nodes_table.setColumnWidth(2, 140)
        self._nodes_empty = _empty("Run a scan to discover mesh nodes.")
        self._nodes_stack = QStackedWidget()
        self._nodes_stack.addWidget(self._nodes_empty)
        self._nodes_stack.addWidget(self._nodes_table)
        self._nodes_stack.setFixedHeight(180)
        nodes_body.addWidget(self._nodes_stack)
        root.addWidget(nodes_card)

        # ── clients card ──────────────────────────────────────────────────────
        clients_card, clients_body = _card("Connected Clients")
        self._clients_table = _table([
            "Device Name", "MAC Address", "IP Address",
            "Mesh Node", "Band", "↑ KB/s", "↓ KB/s",
        ])
        self._clients_table.setColumnWidth(0, 180)
        self._clients_table.setColumnWidth(1, 150)
        self._clients_table.setColumnWidth(2, 130)
        self._clients_table.setColumnWidth(3, 180)
        self._clients_table.setColumnWidth(4, 60)
        self._clients_table.setColumnWidth(5, 70)
        self._clients_empty = _empty("Run a scan to see connected clients.")
        self._clients_stack = QStackedWidget()
        self._clients_stack.addWidget(self._clients_empty)
        self._clients_stack.addWidget(self._clients_table)
        clients_body.addWidget(self._clients_stack)
        root.addWidget(clients_card, 1)

    def _prepopulate_gateway(self) -> None:
        """Auto-fill gateway IP; then try to load a saved password for that host."""
        from PyQt6.QtCore import QSettings
        # Last-used mesh host is the most reliable key — stored on every successful scan.
        # This is independent of gateway detection, which can fail at startup.
        saved_host = QSettings("NetSentinel", "NetSentinel").value("mesh/last_host", "")
        if saved_host:
            self._ip_edit.setText(saved_host)
            self._try_load_keyring(saved_host)
            return
        # Fall back: detect the default gateway (best-effort)
        try:
            from modules.rogue_device import _get_default_gateway
            gw = _get_default_gateway()
            if gw:
                self._ip_edit.setText(gw)
                self._try_load_keyring(gw)
        except Exception:
            pass

    # ── keyring ops ───────────────────────────────────────────────────────────

    def _try_load_keyring(self, host: str) -> None:
        """Load saved password for `host` and update UI state."""
        if not self._keyring_ok:
            return
        saved = _keyring_load(host)
        if saved:
            self._pw_edit.setText(saved)
            self._forget_btn.setEnabled(True)
            self._keyring_info_lbl.setText(
                "Password loaded from OS Credential Manager (Windows Credential Manager / "
                "macOS Keychain / libsecret)."
            )
            self._keyring_info_lbl.setVisible(True)

    def _on_forget_clicked(self) -> None:
        host = self._ip_edit.text().strip()
        if _keyring_delete(host):
            self._pw_edit.clear()
            self._forget_btn.setEnabled(False)
            self._keyring_info_lbl.setVisible(False)
            self._set_status("Saved password removed from OS Credential Manager.", ok=True)
        else:
            self._set_status("Could not remove saved password.", error=True)

    # ── scan ──────────────────────────────────────────────────────────────────

    def _on_scan_clicked(self) -> None:
        host = self._ip_edit.text().strip()
        pw   = self._pw_edit.text().strip()
        if not host:
            self._set_status("Enter a gateway IP address.", error=True)
            return
        if not pw:
            self._set_status("Enter the TP-Link ID password.", error=True)
            return

        if self._worker and self._worker.isRunning():
            return

        self._scan_btn.setEnabled(False)
        self._set_status("Connecting…")

        from workers.mesh_worker import MeshWorker
        self._worker = MeshWorker(host=host, password=pw)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.status.connect(lambda m: self._set_status(m))
        self._worker.start()

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_result(self, data: dict) -> None:
        self._scan_btn.setEnabled(True)
        units   = data.get("units", [])
        clients = data.get("clients", [])

        # Nodes table
        self._nodes_table.setRowCount(0)
        for u in units:
            row = self._nodes_table.rowCount()
            self._nodes_table.insertRow(row)
            for col, val in enumerate([u.name, u.mac, u.ip, u.role.title()]):
                item = QTableWidgetItem(val)
                if col == 3 and val.lower() == "master":
                    item.setForeground(
                        __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(GREEN)
                    )
                self._nodes_table.setItem(row, col, item)
        self._nodes_stack.setCurrentIndex(1 if units else 0)

        # Clients table
        self._clients_table.setRowCount(0)
        for c in clients:
            row = self._clients_table.rowCount()
            self._clients_table.insertRow(row)
            for col, val in enumerate([
                c.name, c.mac, c.ip, c.unit_name, c.band,
                str(c.upload_kbps), str(c.download_kbps),
            ]):
                self._clients_table.setItem(row, col, QTableWidgetItem(val))
        self._clients_stack.setCurrentIndex(1 if clients else 0)

        self._set_status(
            f"✓  {len(units)} node(s)  ·  {len(clients)} client(s)",
            ok=True,
        )

        # Save credentials on successful scan if the user opted in
        host = self._ip_edit.text().strip()
        pw   = self._pw_edit.text().strip()
        if self._keyring_ok and self._remember_cb.isChecked() and host and pw:
            if _keyring_save(host, pw):
                self._forget_btn.setEnabled(True)
                self._keyring_info_lbl.setText(
                    "Password saved securely in OS Credential Manager."
                )
                self._keyring_info_lbl.setVisible(True)
        # Always persist the host address so startup can find the right keyring entry
        # even when gateway auto-detection returns None or a different IP.
        if host:
            from PyQt6.QtCore import QSettings
            QSettings("NetSentinel", "NetSentinel").setValue("mesh/last_host", host)

        self.scan_done.emit(data)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._scan_btn.setEnabled(True)
        self._set_status(msg, error=True)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, *, error: bool = False, ok: bool = False) -> None:
        colour = AMBER if error else (GREEN if ok else TEXT_SECONDARY)
        self._status_lbl.setStyleSheet(
            f"color:{colour}; font-size:11px; background:transparent; border:none;"
        )
        self._status_lbl.setText(msg)

    def set_gateway_ip(self, ip: str) -> None:
        """Called by the dashboard to pre-fill the IP from the M1 scan result."""
        if ip and not self._ip_edit.text().strip():
            self._ip_edit.setText(ip)
            self._try_load_keyring(ip)

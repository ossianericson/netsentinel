"""
PluginDevicePage — live status page for a hardware integration plugin.

Renders differently based on plugin type:
  "modem"  → signal panel (NR5G / LTE bands, RSRP, SINR, cell info)
  "router" → mesh node tree (expandable) + flat connected-client table
  other    → generic key/value status panel

Receives data via update(result) where result has the shape:
  {"info": {...}, "status": {...}, "clients": [...], "_path": "..."}

The page is marked disabled/greyed when the plugin file no longer exists.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore    import Qt, pyqtSignal
from PyQt6.QtGui     import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BORDER, BG_CARD, BG_DARK, BG_ALT_ROW,
    GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
    BG_HOVER,
)

log = logging.getLogger(__name__)

# ── keyring helpers ────────────────────────────────────────────────────────────

_KEYRING_SERVICE = "NetSentinel/hardware"


def _keyring_available() -> bool:
    try:
        import keyring
        kr = keyring.get_keyring()
        return type(kr).__name__ not in ("FailKeyring", "NullKeyring", "PlaintextKeyring")
    except Exception:
        return False


def _keyring_load(ip: str) -> Optional[str]:
    try:
        import keyring
        return keyring.get_password(_KEYRING_SERVICE, ip)
    except Exception:
        return None


def _keyring_save(ip: str, password: str) -> bool:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, ip, password)
        return True
    except Exception as exc:
        log.warning("keyring save failed: %s", exc)
        return False


def _keyring_delete(ip: str) -> bool:
    try:
        import keyring
        from keyring.errors import PasswordDeleteError
        keyring.delete_password(_KEYRING_SERVICE, ip)
        return True
    except Exception:
        return False


# ── helpers ────────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("pluginCard")
    card.setStyleSheet(
        f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:4px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:none;"
        f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
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
    body.setContentsMargins(12, 10, 12, 10)
    body.setSpacing(6)
    outer.addLayout(body, 1)
    return card, body


def _row(label: str, layout: QVBoxLayout) -> QLabel:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setFixedWidth(160)
    lbl.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;"
    )
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
        " background:transparent; border:none;"
    )
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    h.addWidget(lbl)
    h.addWidget(val, 1)
    layout.addLayout(h)
    return val


def _quality_color(rsrp: Optional[float]) -> str:
    if rsrp is None:
        return TEXT_SECONDARY
    if rsrp >= -80:
        return GREEN
    if rsrp >= -90:
        return "#FFA726"
    if rsrp >= -100:
        return AMBER
    return RED


def _fmt(v, suffix: str = "") -> str:
    if v is None:
        return "—"
    return f"{v}{suffix}"


_TBL_SS = (
    f"QTableWidget {{ border:none; background:{BG_CARD};"
    f" alternate-background-color:{BG_ALT_ROW}; }}"
    f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:none;"
    f" border-bottom:1px solid {BORDER}; padding:4px 8px; font-size:11px; }}"
)

_TREE_SS = (
    f"QTreeWidget {{ border:none; background:{BG_CARD}; outline:none; }}"
    f"QTreeWidget::item {{ padding:3px 4px; color:{TEXT_PRIMARY}; }}"
    f"QTreeWidget::item:selected {{ background:{ACCENT}22; color:{TEXT_PRIMARY}; }}"
    f"QHeaderView::section {{ background:{BG_CARD}; color:{TEXT_SECONDARY}; border:none;"
    f" border-bottom:1px solid {BORDER}; padding:4px 8px; font-size:11px; }}"
)


# ── page ───────────────────────────────────────────────────────────────────────

class PluginDevicePage(QWidget):
    """Live status page for one hardware plugin."""

    test_requested = pyqtSignal(str)   # emits plugin path when Test button clicked

    _keyring_warned: bool = False      # class-level: warn once per session

    def __init__(self, plugin_path: str, label: str, hw_type: str,
                 hw_ip: str = "", credential_label: str = "Password",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path             = plugin_path
        self._label            = label
        self._type             = hw_type
        self._hw_ip            = hw_ip
        self._credential_label = credential_label
        self._keyring_ok       = _keyring_available()
        self._testing          = False
        self._build_ui()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; }")
        outer.addWidget(scroll)

        inner = QWidget()
        inner.setStyleSheet(f"QWidget {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)

        self._root = QVBoxLayout(inner)
        self._root.setContentsMargins(16, 16, 16, 16)
        self._root.setSpacing(12)

        # Error / info banner
        self._banner = QLabel()
        self._banner.setWordWrap(True)
        self._banner.setContentsMargins(10, 6, 10, 6)
        self._banner.setStyleSheet(
            f"background:{RED}22; color:{RED}; border:1px solid {RED}44;"
            " border-radius:4px; font-size:12px;"
        )
        self._banner.setVisible(False)
        self._root.addWidget(self._banner)

        # Timestamp row
        self._ts_lbl = QLabel("No data yet — run a Test from the Hardware page.")
        self._ts_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
        self._root.addWidget(self._ts_lbl)

        self._build_credentials_card()

        if self._type == "modem":
            self._build_modem_ui()
        elif self._type in ("router", "ap", "switch"):
            self._build_router_ui()
        else:
            self._build_generic_ui()

        self._root.addStretch(1)

    def _build_credentials_card(self) -> None:
        _field_ss = (
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:12px;"
        )

        cred_card = QFrame()
        cred_card.setObjectName("pluginCard")
        cred_card.setStyleSheet(
            f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        cred_outer = QVBoxLayout(cred_card)
        cred_outer.setContentsMargins(0, 0, 0, 0)
        cred_outer.setSpacing(0)

        hdr = QFrame()
        hdr.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 6, 12, 6)
        hdr_lbl = QLabel("CONNECTION")
        hdr_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
            " letter-spacing:0.5px; background:transparent; border:none;"
        )
        hdr_lay.addWidget(hdr_lbl)
        hdr_lay.addStretch()
        cred_outer.addWidget(hdr)

        # Row 1 — IP badge + password + Test button + status
        row1 = QFrame()
        row1.setStyleSheet("QFrame { border:none; background:transparent; }")
        row1_lay = QHBoxLayout(row1)
        row1_lay.setContentsMargins(12, 8, 12, 8)
        row1_lay.setSpacing(8)

        ip_lbl = QLabel("Gateway IP")
        ip_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;")
        row1_lay.addWidget(ip_lbl)

        ip_badge = QLabel(self._hw_ip or "—")
        ip_badge.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
            f" background:{BG_DARK}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 8px;"
        )
        row1_lay.addWidget(ip_badge)

        pw_lbl = QLabel(self._credential_label)
        pw_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;")
        row1_lay.addWidget(pw_lbl)

        self._cred_pw_edit = QLineEdit()
        self._cred_pw_edit.setPlaceholderText(f"Device {self._credential_label.lower()}")
        self._cred_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._cred_pw_edit.setFixedWidth(160)
        self._cred_pw_edit.setStyleSheet(_field_ss)
        self._cred_pw_edit.returnPressed.connect(self._on_test_clicked)
        row1_lay.addWidget(self._cred_pw_edit)

        self._cred_test_btn = QPushButton("▶  Test")
        self._cred_test_btn.setFixedHeight(28)
        self._cred_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cred_test_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:12px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        self._cred_test_btn.clicked.connect(self._on_test_clicked)
        row1_lay.addWidget(self._cred_test_btn)

        self._cred_status = QLabel()
        self._cred_status.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        row1_lay.addWidget(self._cred_status, 1)
        cred_outer.addWidget(row1)

        _sec_note = QLabel("🔒  Password saved to OS keychain — never written to disk or plugin file")
        _sec_note.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:9px; background:transparent; border:none;"
            " padding:0 0 4px 12px;"
        )
        cred_outer.addWidget(_sec_note)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"border:none; border-top:1px solid {BORDER}; background:transparent;")
        div.setFixedHeight(1)
        cred_outer.addWidget(div)

        # Row 2 — keyring controls
        row2 = QFrame()
        row2.setStyleSheet("QFrame { border:none; background:transparent; }")
        row2_lay = QHBoxLayout(row2)
        row2_lay.setContentsMargins(12, 6, 12, 6)
        row2_lay.setSpacing(12)

        self._cred_remember_cb = QCheckBox("Remember in OS Keychain")
        self._cred_remember_cb.setChecked(self._keyring_ok)
        self._cred_remember_cb.setEnabled(self._keyring_ok)
        self._cred_remember_cb.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        row2_lay.addWidget(self._cred_remember_cb)

        self._cred_forget_btn = QPushButton("Forget Saved Password")
        self._cred_forget_btn.setFixedHeight(24)
        self._cred_forget_btn.setEnabled(False)
        self._cred_forget_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cred_forget_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:1px solid {AMBER};"
            " border-radius:3px; font-size:11px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{AMBER}; color:#000; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; border-color:{BORDER}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
        )
        self._cred_forget_btn.clicked.connect(self._on_forget_clicked)
        row2_lay.addWidget(self._cred_forget_btn)
        row2_lay.addStretch()
        cred_outer.addWidget(row2)
        self._root.addWidget(cred_card)

        # Keyring warning — shown once per session if no backend
        if not self._keyring_ok and not PluginDevicePage._keyring_warned:
            PluginDevicePage._keyring_warned = True
            warn = QFrame()
            warn.setStyleSheet(
                f"QFrame {{ background:#3a2800; border:1px solid {AMBER}; border-radius:0px; }}"
            )
            warn_lay = QHBoxLayout(warn)
            warn_lay.setContentsMargins(12, 8, 12, 8)
            warn_lbl = QLabel(
                "⚠  No keyring backend found — password will not be saved between sessions."
            )
            warn_lbl.setStyleSheet(
                f"color:{AMBER}; font-size:11px; background:transparent; border:none;"
            )
            warn_lbl.setWordWrap(True)
            warn_lay.addWidget(warn_lbl)
            self._root.addWidget(warn)

        # Pre-populate from keyring
        if self._hw_ip:
            saved = _keyring_load(self._hw_ip)
            if saved:
                self._cred_pw_edit.setText(saved)
                self._cred_forget_btn.setEnabled(True)
                self._cred_status.setText("Password saved securely in OS Credential Manager.")

    # ── credentials handlers ──────────────────────────────────────────────────

    def _on_test_clicked(self) -> None:
        pw = self._cred_pw_edit.text().strip()
        if not pw:
            self._cred_status.setText("Enter a password first.")
            return
        if self._cred_remember_cb.isChecked() and self._hw_ip:
            if _keyring_save(self._hw_ip, pw):
                self._cred_forget_btn.setEnabled(True)
        self._testing = True
        self._cred_test_btn.setEnabled(False)
        self._cred_test_btn.setText("Testing…")
        self._cred_status.setText("")
        self.test_requested.emit(self._path)

    def _on_forget_clicked(self) -> None:
        if self._hw_ip:
            _keyring_delete(self._hw_ip)
        self._cred_pw_edit.clear()
        self._cred_forget_btn.setEnabled(False)
        self._cred_status.setText("Password removed.")

    def test_done(self, error_msg: str = "") -> None:
        """Re-enable Test button after a one-shot run finishes (success or error)."""
        self._testing = False
        self._cred_test_btn.setEnabled(True)
        self._cred_test_btn.setText("▶  Test")
        if error_msg:
            self._cred_status.setText(f"Error: {error_msg}")

    def _build_modem_ui(self) -> None:
        # Status
        card, body = _card("Status")
        self._m_wan_ip      = _row("WAN IP",         body)
        self._m_wan_status  = _row("WAN Status",     body)
        self._m_net_type    = _row("Network Type",   body)
        self._m_bars        = _row("Signal Bars",    body)
        self._m_firmware    = _row("Firmware",       body)
        self._root.addWidget(card)

        # NR5G
        card2, body2 = _card("5G NR")
        self._m_nr_band  = _row("Band",    body2)
        self._m_nr_rsrp  = _row("RSRP",   body2)
        self._m_nr_sinr  = _row("SINR",   body2)
        self._m_nr_rsrq  = _row("RSRQ",   body2)
        self._m_nr_pci   = _row("PCI",    body2)
        self._m_nr_arfcn = _row("ARFCN",  body2)
        self._root.addWidget(card2)

        # LTE
        card3, body3 = _card("LTE")
        self._m_lte_band   = _row("Band",   body3)
        self._m_lte_rsrp   = _row("RSRP",  body3)
        self._m_lte_snr    = _row("SNR",   body3)
        self._m_lte_rsrq   = _row("RSRQ",  body3)
        self._m_lte_pci    = _row("PCI",   body3)
        self._m_lte_earfcn = _row("EARFCN", body3)
        self._root.addWidget(card3)

        # Cell identity
        card4, body4 = _card("Cell Identity")
        self._m_cell_id = _row("Cell ID", body4)
        self._m_enb_id  = _row("eNB ID",  body4)
        self._m_mcc     = _row("MCC",     body4)
        self._m_mnc     = _row("MNC",     body4)
        self._root.addWidget(card4)

    def _build_router_ui(self) -> None:
        # Summary
        card, body = _card("Status")
        self._r_clients = _row("Connected clients", body)
        self._r_nodes   = _row("Mesh nodes",        body)
        self._r_wan_ip  = _row("WAN IP",            body)
        self._root.addWidget(card)

        # Mesh Nodes tree — top-level rows are nodes, children are connected clients
        card2 = QFrame()
        card2.setObjectName("pluginCard")
        card2.setStyleSheet(
            f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        card2_outer = QVBoxLayout(card2)
        card2_outer.setContentsMargins(0, 0, 0, 0)
        card2_outer.setSpacing(0)

        hdr2 = QFrame()
        hdr2.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
        )
        hdr2_lay = QHBoxLayout(hdr2)
        hdr2_lay.setContentsMargins(12, 6, 12, 6)
        hdr2_lbl = QLabel("MESH NODES")
        hdr2_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
            " letter-spacing:0.5px; background:transparent; border:none;"
        )
        hdr2_lay.addWidget(hdr2_lbl)
        hdr2_lay.addStretch()
        hint = QLabel("▶ click node to collapse/expand connected devices")
        hint.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        hdr2_lay.addWidget(hint)
        card2_outer.addWidget(hdr2)

        self._r_node_tree = QTreeWidget()
        self._r_node_tree.setColumnCount(4)
        self._r_node_tree.setHeaderLabels(["NAME", "MAC ADDRESS", "IP ADDRESS", "ROLE"])
        self._r_node_tree.header().setStretchLastSection(True)
        self._r_node_tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._r_node_tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self._r_node_tree.setRootIsDecorated(True)
        self._r_node_tree.setStyleSheet(_TREE_SS)
        self._r_node_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._r_node_tree.itemExpanded.connect(self._resize_node_tree_columns)
        self._r_node_tree.itemCollapsed.connect(self._resize_node_tree_columns)
        card2_outer.addWidget(self._r_node_tree)
        self._root.addWidget(card2)

        # Connected Clients — flat table matching old Mesh Router view
        card3 = QFrame()
        card3.setObjectName("pluginCard")
        card3.setStyleSheet(
            f"QFrame#pluginCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}"
        )
        card3_outer = QVBoxLayout(card3)
        card3_outer.setContentsMargins(0, 0, 0, 0)
        card3_outer.setSpacing(0)

        hdr3 = QFrame()
        hdr3.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:none;"
            f" border-bottom:1px solid {BORDER}; border-radius:4px 4px 0 0; }}"
        )
        hdr3_lay = QHBoxLayout(hdr3)
        hdr3_lay.setContentsMargins(12, 6, 12, 6)
        hdr3_lbl = QLabel("CONNECTED CLIENTS")
        hdr3_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
            " letter-spacing:0.5px; background:transparent; border:none;"
        )
        hdr3_lay.addWidget(hdr3_lbl)
        hdr3_lay.addStretch()
        card3_outer.addWidget(hdr3)

        self._r_client_tbl = QTableWidget(0, 7)
        self._r_client_tbl.setHorizontalHeaderLabels(
            ["DEVICE NAME", "MAC ADDRESS", "IP ADDRESS", "MESH NODE", "BAND", "↑ KB/S", "↓ KB/S"]
        )
        self._r_client_tbl.horizontalHeader().setStretchLastSection(True)
        self._r_client_tbl.verticalHeader().setVisible(False)
        self._r_client_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._r_client_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._r_client_tbl.setAlternatingRowColors(True)
        self._r_client_tbl.setStyleSheet(_TBL_SS)
        self._r_client_tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card3_outer.addWidget(self._r_client_tbl)
        self._root.addWidget(card3)

    def _build_generic_ui(self) -> None:
        card, body = _card("Status")
        self._g_rows: dict[str, QLabel] = {}
        for key in ("wan_ip", "uptime_sec", "download_mbps", "upload_mbps",
                    "signal_dbm", "connected_clients"):
            self._g_rows[key] = _row(key.replace("_", " ").title(), body)
        self._root.addWidget(card)

    # ── data ──────────────────────────────────────────────────────────────────

    def update(self, result: dict) -> None:
        """Refresh the page from a plugin result dict."""
        info    = result.get("info", {})
        status  = result.get("status", {})
        clients = result.get("clients", [])
        extra   = status.get("extra", {})
        err     = extra.get("error")

        file_ok = os.path.isfile(self._path)
        if not file_ok:
            self._show_banner(f"Plugin file not found: {self._path}", RED)
        elif err:
            self._show_banner(str(err), RED)
        else:
            self._banner.setVisible(False)

        self._ts_lbl.setText(
            f"Last updated: {datetime.now().strftime('%H:%M:%S')}  ·  {info.get('ip', '')}"
        )

        if self._type == "modem":
            self._fill_modem(status, extra)
        elif self._type in ("router", "ap", "switch"):
            self._fill_router(status, extra, clients)
        else:
            self._fill_generic(status)

        if self._testing:
            self.test_done()
            self._cred_status.setText("Password saved securely in OS Credential Manager."
                                      if self._cred_remember_cb.isChecked() else "")

    def _show_banner(self, text: str, color: str) -> None:
        self._banner.setText(text)
        self._banner.setStyleSheet(
            f"background:{color}22; color:{color}; border:1px solid {color}44;"
            " border-radius:4px; font-size:12px; padding:6px 10px;"
        )
        self._banner.setVisible(True)

    def _fill_modem(self, status: dict, extra: dict) -> None:
        self._m_wan_ip.setText(_fmt(status.get("wan_ip")))
        self._m_wan_status.setText(_fmt(status.get("wan_status")))
        self._m_net_type.setText(_fmt(extra.get("network_type")))
        bars = extra.get("signal_bars")
        self._m_bars.setText(_fmt(bars))
        self._m_firmware.setText(_fmt(extra.get("firmware")))

        nr_rsrp = extra.get("nr5g_rsrp_dbm")
        self._m_nr_band.setText(_fmt(extra.get("nr5g_band")))
        self._m_nr_rsrp.setText(_fmt(nr_rsrp, " dBm"))
        self._m_nr_rsrp.setStyleSheet(
            f"color:{_quality_color(nr_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        self._m_nr_sinr.setText(_fmt(extra.get("nr5g_sinr_db"), " dB"))
        self._m_nr_rsrq.setText(_fmt(extra.get("nr5g_rsrq_db"), " dB"))
        self._m_nr_pci.setText(_fmt(extra.get("nr5g_pci")))
        self._m_nr_arfcn.setText(_fmt(extra.get("nr5g_arfcn")))

        lte_rsrp = extra.get("lte_rsrp_dbm")
        self._m_lte_band.setText(_fmt(extra.get("lte_band")))
        self._m_lte_rsrp.setText(_fmt(lte_rsrp, " dBm"))
        self._m_lte_rsrp.setStyleSheet(
            f"color:{_quality_color(lte_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        self._m_lte_snr.setText(_fmt(extra.get("lte_snr_db"), " dB"))
        self._m_lte_rsrq.setText(_fmt(extra.get("lte_rsrq_db"), " dB"))
        self._m_lte_pci.setText(_fmt(extra.get("lte_pci")))
        self._m_lte_earfcn.setText(_fmt(extra.get("lte_earfcn")))

        self._m_cell_id.setText(_fmt(extra.get("cell_id")))
        self._m_enb_id.setText(_fmt(extra.get("enb_id")))
        self._m_mcc.setText(_fmt(extra.get("mcc")))
        self._m_mnc.setText(_fmt(extra.get("mnc")))

    def _resize_node_tree_columns(self) -> None:
        for col in range(self._r_node_tree.columnCount()):
            self._r_node_tree.resizeColumnToContents(col)
        self._set_tree_height()

    def _set_tree_height(self) -> None:
        """Set an explicit fixed height so no layout cascade is triggered."""
        tree = self._r_node_tree
        row_h = max(tree.sizeHintForRow(0), 22)
        h = tree.header().sizeHint().height()
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            h += row_h
            if item.isExpanded():
                for j in range(item.childCount()):
                    h += row_h
                    child = item.child(j)
                    if child.isExpanded():
                        h += child.childCount() * row_h
        tree.setFixedHeight(h + 4)

    def _set_table_height(self) -> None:
        """Set an explicit fixed height so no layout cascade is triggered."""
        tbl = self._r_client_tbl
        h = tbl.horizontalHeader().sizeHint().height()
        row_h = tbl.verticalHeader().defaultSectionSize()
        h += tbl.rowCount() * row_h
        tbl.setFixedHeight(h + 4)

    def _fill_router(self, status: dict, extra: dict, clients: list) -> None:
        nodes = extra.get("nodes", [])
        self._r_clients.setText(str(status.get("connected_clients") or len(clients)))
        self._r_nodes.setText(str(status.get("mesh_nodes") or len(nodes)))
        self._r_wan_ip.setText(_fmt(status.get("wan_ip")))

        # Build node-name → client list map
        buckets: dict[str, list] = {n.get("name", ""): [] for n in nodes}
        for c in clients:
            unit = c.get("unit", "") or ""
            if unit in buckets:
                buckets[unit].append(c)

        bold = QFont()
        bold.setBold(True)

        # Mesh nodes tree
        self._r_node_tree.clear()
        for node in nodes:
            name = node.get("name", "")
            mac  = node.get("mac", "")
            ip   = node.get("ip", "") or "—"
            role = node.get("role", "")

            node_item = QTreeWidgetItem([name, mac, ip, role])
            node_item.setFont(0, bold)
            node_item.setForeground(
                0, QColor(ACCENT if role == "master" else TEXT_PRIMARY)
            )
            node_item.setForeground(3, QColor(ACCENT if role == "master" else TEXT_SECONDARY))

            # Child rows: clients connected to this node
            for c in buckets.get(name, []):
                device = c.get("hostname") or c.get("mac") or "Unknown"
                child = QTreeWidgetItem([
                    f"  {device}",
                    c.get("mac", "") or "",
                    c.get("ip", "") or "",
                    c.get("band", "") or "",
                ])
                child.setForeground(0, QColor(TEXT_SECONDARY))
                node_item.addChild(child)

            node_item.setExpanded(True)
            self._r_node_tree.addTopLevelItem(node_item)

        self._r_node_tree.resizeColumnToContents(0)
        self._r_node_tree.resizeColumnToContents(1)
        self._r_node_tree.resizeColumnToContents(2)
        self._set_tree_height()

        # Flat connected clients table
        self._r_client_tbl.setRowCount(0)
        for c in clients:
            r = self._r_client_tbl.rowCount()
            self._r_client_tbl.insertRow(r)
            device = c.get("hostname") or c.get("mac") or ""
            self._r_client_tbl.setItem(r, 0, QTableWidgetItem(device))
            self._r_client_tbl.setItem(r, 1, QTableWidgetItem(c.get("mac", "") or ""))
            self._r_client_tbl.setItem(r, 2, QTableWidgetItem(c.get("ip", "") or ""))
            self._r_client_tbl.setItem(r, 3, QTableWidgetItem(c.get("unit", "") or ""))
            self._r_client_tbl.setItem(r, 4, QTableWidgetItem(c.get("band", "") or ""))
            up   = c.get("upload_kbps")
            down = c.get("download_kbps")
            self._r_client_tbl.setItem(r, 5, QTableWidgetItem("" if up   is None else f"{up:.1f}"))
            self._r_client_tbl.setItem(r, 6, QTableWidgetItem("" if down is None else f"{down:.1f}"))
        self._r_client_tbl.resizeColumnsToContents()
        self._set_table_height()

    def _fill_generic(self, status: dict) -> None:
        for key, lbl in self._g_rows.items():
            lbl.setText(_fmt(status.get(key)))

    def mark_unavailable(self) -> None:
        """Grey the page out when the plugin file is missing."""
        self._show_banner(
            f"Plugin file not found — re-import it from the Hardware page:\n{self._path}",
            AMBER,
        )

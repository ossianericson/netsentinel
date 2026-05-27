"""
Modem page — live 5G/LTE signal metrics from a WAN modem.

Supports ZTE MC889 today; the worker architecture accepts additional
providers (Huawei, Netgear, Sierra Wireless) via a provider key — the
same pattern used by Mesh & Router for Deco.

Password security
-----------------
Passwords are stored ONLY in the OS credential manager via `keyring`.
They are NEVER written to files, config, or environment variables.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore    import Qt, QSettings, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ui.widgets.signal_bar import SignalBar

from ui.styles import (
    ACCENT, AMBER, BORDER, BG_CARD, BG_DARK, GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
    BG_HOVER,
)

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "NetSentinel/modem"
_SETTINGS_HOST   = "modem/last_host"


# ── keyring helpers ────────────────────────────────────────────────────────────

def _keyring_available() -> bool:
    try:
        import keyring
        kr = keyring.get_keyring()
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


# ── layout helpers ─────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("modemCard")
    card.setStyleSheet(
        f"QFrame#modemCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
        " border-radius:0px; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setObjectName("modemCardHdr")
    hdr.setStyleSheet(
        f"QFrame#modemCardHdr {{ background:{BG_CARD}; border:none;"
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
    body.setContentsMargins(12, 10, 12, 10)
    body.setSpacing(6)
    outer.addLayout(body, 1)
    return card, body


def _row(label: str, parent_layout: QVBoxLayout) -> QLabel:
    """Add a label-value row; returns the value QLabel."""
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
    parent_layout.addLayout(h)
    return val


def _signal_row(label: str, metric: str, parent_layout: QVBoxLayout) -> tuple:
    """Add a row with a SignalBar + text label; returns (SignalBar, QLabel)."""
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label)
    lbl.setFixedWidth(160)
    lbl.setStyleSheet(
        f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;"
    )
    bar = SignalBar(metric=metric)
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:bold;"
        " background:transparent; border:none;"
    )
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    h.addWidget(lbl)
    h.addWidget(bar)
    h.addWidget(val, 1)
    parent_layout.addLayout(h)
    return bar, val


def _divider() -> QFrame:
    d = QFrame()
    d.setFrameShape(QFrame.Shape.HLine)
    d.setStyleSheet(f"border:none; border-top:1px solid {BORDER}; background:transparent;")
    d.setFixedHeight(1)
    return d


def _quality_color(rsrp: Optional[float]) -> str:
    if rsrp is None:
        return TEXT_SECONDARY
    if rsrp >= -80:
        return GREEN
    if rsrp >= -90:
        return "#FFA726"   # AMBER
    if rsrp >= -100:
        return AMBER
    return RED


# ── page ───────────────────────────────────────────────────────────────────────

class ModemPage(QWidget):
    """
    Dedicated page for 5G/LTE modem signal monitoring.

    The dashboard owns the ZteWorker.  This page only:
      • Emits connect_requested / disconnect_requested so the dashboard
        can start/stop the worker.
      • Receives on_modem_signal() / on_modem_error() / on_modem_status()
        from the dashboard and updates the display.

    Credential storage: OS keychain via keyring — never written to disk.
    """

    connect_requested    = pyqtSignal(str, str)   # host, password
    disconnect_requested = pyqtSignal()

    _keyring_warned: bool = False   # class-level: warn once per session

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._keyring_ok = _keyring_available()
        self._connected  = False
        self._setup_ui()
        self._prepopulate()

    # ── layout ────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
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

        root = QVBoxLayout(inner)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # ── header ────────────────────────────────────────────────────────────
        from ui.widgets.page_header import PageHeaderBar
        root.addWidget(PageHeaderBar("Modem"))

        compat = QFrame()
        compat.setObjectName("modemCompatBanner")
        compat.setStyleSheet(
            f"QFrame#modemCompatBanner {{ background:#1A2A3A; border:1px solid #2A4A6A;"
            f" border-left:3px solid {ACCENT}; border-radius:0px; }}"
        )
        compat_lay = QHBoxLayout(compat)
        compat_lay.setContentsMargins(12, 6, 12, 6)
        compat_lbl = QLabel(
            "ℹ  Tested with <b>ZTE MC889</b>. For other modem models, use the "
            "<b>Hardware Hub</b> plugin system (Extend section) — any device with a "
            "local HTTP API can be integrated via a Python plugin script."
        )
        compat_lbl.setTextFormat(Qt.TextFormat.RichText)
        compat_lbl.setWordWrap(True)
        compat_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; border:none; background:transparent;"
        )
        compat_lay.addWidget(compat_lbl)
        root.addWidget(compat)

        # ── config card ───────────────────────────────────────────────────────
        cfg_card = QFrame()
        cfg_card.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px;"
        )
        cfg_lay = QVBoxLayout(cfg_card)
        cfg_lay.setContentsMargins(0, 0, 0, 0)
        cfg_lay.setSpacing(0)

        # Row 1 — inputs
        row1 = QFrame()
        row1.setStyleSheet("border:none; background:transparent;")
        row1_lay = QHBoxLayout(row1)
        row1_lay.setContentsMargins(12, 8, 12, 8)
        row1_lay.setSpacing(8)

        _ip_lbl = QLabel("Modem IP")
        _ip_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;"
        )
        row1_lay.addWidget(_ip_lbl)

        self._ip_edit = QLineEdit()
        self._ip_edit.setPlaceholderText("192.168.254.1")
        self._ip_edit.setFixedWidth(140)
        self._ip_edit.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            " border-radius:3px; padding:3px 6px; font-size:12px;"
        )
        row1_lay.addWidget(self._ip_edit)

        _pw_lbl = QLabel("Password")
        _pw_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:12px; background:transparent; border:none;"
        )
        row1_lay.addWidget(_pw_lbl)

        self._pw_edit = QLineEdit()
        self._pw_edit.setPlaceholderText("Admin password")
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.setFixedWidth(160)
        self._pw_edit.setStyleSheet(self._ip_edit.styleSheet())
        row1_lay.addWidget(self._pw_edit)

        self._connect_btn = QPushButton("▶  Connect")
        self._connect_btn.setFixedHeight(28)
        self._connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._connect_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:12px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._connect_btn.clicked.connect(self._on_connect_clicked)
        row1_lay.addWidget(self._connect_btn)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        row1_lay.addWidget(self._status_lbl, 1)

        cfg_lay.addWidget(row1)

        div1 = _divider()
        cfg_lay.addWidget(div1)

        # Row 2 — keyring
        row2 = QFrame()
        row2.setStyleSheet("border:none; background:transparent;")
        row2_lay = QHBoxLayout(row2)
        row2_lay.setContentsMargins(12, 6, 12, 6)
        row2_lay.setSpacing(8)

        self._remember_cb = QCheckBox("Remember in OS Keychain")
        self._remember_cb.setChecked(True)
        self._remember_cb.setEnabled(self._keyring_ok)
        self._remember_cb.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; background:transparent; border:none;"
        )
        row2_lay.addWidget(self._remember_cb)

        self._forget_btn = QPushButton("Forget Saved Password")
        self._forget_btn.setFixedHeight(24)
        self._forget_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._forget_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{AMBER}; border:1px solid {AMBER};"
            " border-radius:3px; font-size:11px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:#FFF3E0; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{AMBER}; }}"
        )
        self._forget_btn.clicked.connect(self._on_forget_clicked)
        row2_lay.addWidget(self._forget_btn)
        row2_lay.addStretch()

        cfg_lay.addWidget(row2)
        root.addWidget(cfg_card)

        # ── keyring warning ────────────────────────────────────────────────────
        if not self._keyring_ok and not ModemPage._keyring_warned:
            ModemPage._keyring_warned = True
            warn = QFrame()
            warn.setObjectName("modemWarnBanner")
            warn.setStyleSheet(
                f"QFrame#modemWarnBanner {{ background:#FFF8E1; border:1px solid {AMBER}; border-radius:0px; }}"
            )
            warn_lay = QHBoxLayout(warn)
            warn_lay.setContentsMargins(12, 8, 12, 8)
            warn_lbl = QLabel(
                "⚠  No secure keyring backend found — password will not be saved between sessions."
            )
            warn_lbl.setStyleSheet(f"color:#7A5700; font-size:11px; border:none; background:transparent;")
            warn_lay.addWidget(warn_lbl)
            root.addWidget(warn)

        # ── signal display (stacked: empty / data) ────────────────────────────
        self._signal_stack = QStackedWidget()
        self._signal_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # Index 0 — empty state
        empty_w = QLabel("Connect to a modem to see live signal metrics.")
        empty_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_w.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:13px; padding:60px; border:none; background:transparent;"
        )
        self._signal_stack.addWidget(empty_w)   # index 0

        # Index 1 — data view
        data_w = QWidget()
        data_w.setStyleSheet("QWidget { background:transparent; }")
        data_lay = QVBoxLayout(data_w)
        data_lay.setContentsMargins(0, 0, 0, 0)
        data_lay.setSpacing(10)

        # Connection card
        conn_card, conn_body = _card("Connection")
        self._v_wan_ip       = _row("Public IP",        conn_body)
        self._v_network_type = _row("Network Type",     conn_body)
        self._v_wan_status   = _row("WAN Status",       conn_body)
        self._v_signal_bars  = _row("Signal",           conn_body)
        self._v_operator     = _row("Operator (MCC-MNC)",conn_body)
        data_lay.addWidget(conn_card)

        # 5G NR card
        nr5g_card, nr5g_body = _card("5G NR")
        self._b_nr5g_rsrp, self._v_nr5g_rsrp = _signal_row("RSRP", "rsrp", nr5g_body)
        self._b_nr5g_rsrp.setToolTip(
            "Reference Signal Received Power — 5G NR signal strength from the tower.\n"
            "Good: ≥ −80 dBm   Acceptable: −80 to −100 dBm   Poor: < −100 dBm"
        )
        self._b_nr5g_sinr, self._v_nr5g_sinr = _signal_row("SINR", "sinr", nr5g_body)
        self._b_nr5g_sinr.setToolTip(
            "Signal-to-Interference-plus-Noise Ratio — signal clarity vs. interference.\n"
            "Good: ≥ 20 dB   Acceptable: 0–20 dB   Poor: < 0 dB"
        )
        self._b_nr5g_rsrq, self._v_nr5g_rsrq = _signal_row("RSRQ", "rsrq", nr5g_body)
        self._b_nr5g_rsrq.setToolTip(
            "Reference Signal Received Quality — signal quality factoring in cell load and interference.\n"
            "Good: ≥ −10 dB   Acceptable: −10 to −15 dB   Poor: < −15 dB"
        )
        self._v_nr5g_band  = _row("Band",  nr5g_body)
        self._v_nr5g_band.setToolTip(
            "5G NR radio band in use. Sub-6 GHz bands (n1, n3, n78) offer wider coverage;\n"
            "mmWave bands (n257+) offer peak speeds but short range."
        )
        self._v_nr5g_pci   = _row("PCI",   nr5g_body)
        self._v_nr5g_pci.setToolTip(
            "Physical Cell ID — identifies the specific antenna sector serving you (0–1007). Informational only."
        )
        self._v_nr5g_arfcn = _row("ARFCN", nr5g_body)
        self._v_nr5g_arfcn.setToolTip(
            "Absolute Radio Frequency Channel Number — the channel index for the 5G NR carrier frequency. Informational only."
        )
        data_lay.addWidget(nr5g_card)

        # LTE card
        lte_card, lte_body = _card("LTE Primary")
        self._b_lte_rsrp, self._v_lte_rsrp = _signal_row("RSRP", "rsrp", lte_body)
        self._b_lte_rsrp.setToolTip(
            "Reference Signal Received Power — LTE signal strength from the tower.\n"
            "Good: ≥ −80 dBm   Acceptable: −80 to −100 dBm   Poor: < −100 dBm"
        )
        self._b_lte_snr, self._v_lte_snr = _signal_row("SNR", "snr", lte_body)
        self._b_lte_snr.setToolTip(
            "Signal-to-Noise Ratio — ratio of signal power to background noise on the LTE carrier.\n"
            "Good: ≥ 20 dB   Acceptable: 0–20 dB   Poor: < 0 dB"
        )
        self._b_lte_rsrq, self._v_lte_rsrq = _signal_row("RSRQ", "rsrq", lte_body)
        self._b_lte_rsrq.setToolTip(
            "Reference Signal Received Quality — LTE signal quality factoring in cell load and interference.\n"
            "Good: ≥ −10 dB   Acceptable: −10 to −15 dB   Poor: < −15 dB"
        )
        self._v_lte_band  = _row("Band",   lte_body)
        self._v_lte_band.setToolTip(
            "LTE frequency band in use (e.g., B3 = 1800 MHz, B20 = 800 MHz).\n"
            "Lower bands travel further; higher bands carry more data."
        )
        self._v_lte_pci   = _row("PCI",    lte_body)
        self._v_lte_pci.setToolTip(
            "Physical Cell ID — identifies the specific LTE antenna sector (0–503). Informational only."
        )
        self._v_lte_earfcn= _row("EARFCN", lte_body)
        self._v_lte_earfcn.setToolTip(
            "E-UTRA Absolute Radio Frequency Channel Number — LTE carrier frequency index. Informational only."
        )
        data_lay.addWidget(lte_card)

        # Cell identity card
        cell_card, cell_body = _card("Cell Identity")
        self._v_cell_id   = _row("Cell ID",        cell_body)
        self._v_cell_id.setToolTip(
            "Unique ID of the serving cell (sector) within the base station. Changes when you hand off to a different sector."
        )
        self._v_enb_id    = _row("eNB / gNB ID",   cell_body)
        self._v_enb_id.setToolTip(
            "Base station ID: eNB = 4G LTE, gNB = 5G NR. Identifies the physical tower you're connected to."
        )
        self._v_endc_info = _row("EN-DC Active",   cell_body)
        self._v_endc_info.setToolTip(
            "E-UTRA–NR Dual Connectivity — running LTE and 5G NR simultaneously for higher combined throughput."
        )
        self._v_firmware  = _row("Firmware",       cell_body)
        data_lay.addWidget(cell_card)

        data_lay.addStretch()
        self._signal_stack.addWidget(data_w)     # index 1

        root.addWidget(self._signal_stack, 1)

    # ── pre-population ────────────────────────────────────────────────────────

    def _prepopulate(self) -> None:
        """Load last-used host + saved password from keyring/QSettings."""
        s = QSettings("NetSentinel", "NetSentinel")
        host = s.value(_SETTINGS_HOST, "") or ""
        if not host:
            try:
                from modules.rogue_device import _get_default_gateway
                gw = _get_default_gateway()
                if gw:
                    host = gw
            except Exception:
                pass
        if host:
            self._ip_edit.setText(host)
            pw = _keyring_load(host)
            if pw:
                self._pw_edit.setText(pw)

    def set_host(self, host: str) -> None:
        """Pre-fill IP from an external source (e.g. M1 scan result)."""
        if host and not self._ip_edit.text().strip():
            self._ip_edit.setText(host)

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_modem_signal(self, data: dict) -> None:
        """Receive signal data from the dashboard and update the display."""
        self._signal_stack.setCurrentIndex(1)
        self._set_status("Connected  ·  updating…", GREEN)

        def _fmt_dbm(v) -> str:
            return f"{float(v):.1f} dBm" if v is not None else "—"

        def _fmt_db(v) -> str:
            return f"{float(v):.1f} dB" if v is not None else "—"

        def _s(v) -> str:
            return str(v) if v is not None else "—"

        # Connection
        self._v_wan_ip.setText(_s(data.get("wan_ip")))
        self._v_network_type.setText(_s(data.get("network_type")))
        self._v_wan_status.setText(_s(data.get("wan_status")))

        bars = data.get("signal_bars")
        self._v_signal_bars.setText(f"{bars}/5" if bars is not None else "—")

        mcc = data.get("mcc")
        mnc = data.get("mnc")
        self._v_operator.setText(f"{mcc}-{mnc}" if mcc and mnc else "—")

        # 5G NR — bar + colored text for signal metrics
        nr_rsrp = data.get("nr5g_rsrp_dbm")
        self._b_nr5g_rsrp.set_value(nr_rsrp, "dBm")
        self._v_nr5g_rsrp.setText(_fmt_dbm(nr_rsrp))
        self._v_nr5g_rsrp.setStyleSheet(
            f"color:{_quality_color(nr_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        nr_sinr = data.get("nr5g_sinr_db")
        self._b_nr5g_sinr.set_value(nr_sinr, "dB")
        self._v_nr5g_sinr.setText(_fmt_db(nr_sinr))
        nr_rsrq = data.get("nr5g_rsrq_db")
        self._b_nr5g_rsrq.set_value(nr_rsrq, "dB")
        self._v_nr5g_rsrq.setText(_fmt_db(nr_rsrq))
        self._v_nr5g_band.setText(_s(data.get("nr5g_band")))
        self._v_nr5g_pci.setText(_s(data.get("nr5g_pci")))
        self._v_nr5g_arfcn.setText(_s(data.get("nr5g_arfcn")))

        # LTE — bar + colored text for signal metrics
        lte_rsrp = data.get("lte_rsrp_dbm")
        self._b_lte_rsrp.set_value(lte_rsrp, "dBm")
        self._v_lte_rsrp.setText(_fmt_dbm(lte_rsrp))
        self._v_lte_rsrp.setStyleSheet(
            f"color:{_quality_color(lte_rsrp)}; font-size:12px; font-weight:bold;"
            " background:transparent; border:none;"
        )
        lte_snr = data.get("lte_snr_db")
        self._b_lte_snr.set_value(lte_snr, "dB")
        self._v_lte_snr.setText(_fmt_db(lte_snr))
        lte_rsrq = data.get("lte_rsrq_db")
        self._b_lte_rsrq.set_value(lte_rsrq, "dB")
        self._v_lte_rsrq.setText(_fmt_db(lte_rsrq))
        self._v_lte_band.setText(_s(data.get("lte_band")))
        self._v_lte_pci.setText(_s(data.get("lte_pci")))
        self._v_lte_earfcn.setText(_s(data.get("lte_earfcn")))

        # Cell
        self._v_cell_id.setText(_s(data.get("cell_id")))
        self._v_enb_id.setText(_s(data.get("enb_id")))
        endc = data.get("endc_info")
        self._v_endc_info.setText("Yes" if endc == "1" else ("No" if endc == "0" else "—"))
        self._v_firmware.setText(_s(data.get("firmware_version")))

    @pyqtSlot(str)
    def on_modem_error(self, msg: str) -> None:
        self._set_status(f"Error: {msg}", RED)
        self._connect_btn.setText("▶  Connect")
        self._connect_btn.setEnabled(True)
        self._connected = False

    @pyqtSlot(str)
    def on_modem_status(self, msg: str) -> None:
        self._set_status(msg)

    # ── button handlers ───────────────────────────────────────────────────────

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self._connected = False
            self._connect_btn.setText("▶  Connect")
            self._set_status("Disconnected.")
            self.disconnect_requested.emit()
            return

        host = self._ip_edit.text().strip()
        pw   = self._pw_edit.text().strip()

        if not host:
            self._set_status("Enter the modem IP address.", AMBER)
            return
        if not pw:
            self._set_status("Enter the admin password.", AMBER)
            return

        # Save credentials if requested
        if self._keyring_ok and self._remember_cb.isChecked():
            _keyring_save(host, pw)

        QSettings("NetSentinel", "NetSentinel").setValue(_SETTINGS_HOST, host)

        self._connected = True
        self._connect_btn.setText("■  Disconnect")
        self._set_status("Connecting…")
        self.connect_requested.emit(host, pw)

    def _on_forget_clicked(self) -> None:
        host = self._ip_edit.text().strip()
        if host:
            _keyring_delete(host)
        self._pw_edit.clear()
        self._set_status("Saved password cleared.")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color: str = "") -> None:
        color_style = f"color:{color};" if color else f"color:{TEXT_SECONDARY};"
        self._status_lbl.setStyleSheet(
            f"{color_style} font-size:11px; background:transparent; border:none;"
        )
        self._status_lbl.setText(msg)

"""
log_source_panel.py — LogHub panel builders and source management mixin.

Extracted from log_hub_page.py (S14-3b) to reduce that file's size.

Provides:
  • Module-level constants/helpers shared between LogHubPage and the mixin
    (_SOURCES, _MAX_ROWS, _fmt_ts, _status_color,
     _SOURCE_TIPS, _LABEL_TO_KEY, _source_key, _build_live_scenario)
  • _LogSourcePanelMixin — all panel-building and source-toggle methods
    inherited by LogHubPage
"""
from __future__ import annotations

import csv as _csv
import datetime as _dt
import time as _t

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from ui.styles import (
    alpha,
    LOG_SOURCE_PLUGIN,
)

# Explicit public API — these names are consumed only from log_hub_page.py's
# import, so CodeQL's per-file unused-global-variable check needs __all__ to
# recognise the cross-module usage (py/unused-global-variable).
__all__ = [
    "_LogSourcePanelMixin",
    "_SOURCES",
    "_MAX_ROWS",
    "_LIVE_CHALLENGE_COOLDOWN",
    "_fmt_ts",
    "_status_color",
    "_source_color",
    "_build_live_scenario",
]

# ── Module-level constants (imported by log_hub_page.py too) ─────────────────

_MAX_ROWS = 2000
_LIVE_CHALLENGE_COOLDOWN = 60.0

# Colours are theme token NAME strings (resolved live via getattr(_s, name)) —
# a bare-token tuple would freeze at import and never follow a theme switch.
_SOURCES: dict[str, tuple[str, str]] = {
    "net":    ("RTT",         "ACCENT"),
    "modem":  ("5G Modem",    "GREEN"),
    "mesh":   ("Mesh Router", "AMBER"),
    "syslog": ("Syslog",      "TEXT_SECONDARY"),
    "snmp":   ("SNMP Traps",  "RED"),
    "plugin": ("PLUGIN",      "LOG_SOURCE_PLUGIN"),
}
_LABEL_TO_KEY = {label: key for key, (label, _) in _SOURCES.items()}


def _source_color(key: str) -> str:
    """Live theme colour for a log source key (falls back to TEXT_PRIMARY)."""
    _, cname = _SOURCES.get(key, ("", "TEXT_PRIMARY"))
    return getattr(_s, cname)

_SOURCE_TIPS: dict[str, str] = {
    "net":    "Network RTT — continuous latency measurements to gateway and DNS (higher is worse).",
    "modem":  "5G Modem — periodic signal snapshots: RSRP, SINR, band. Set interval in Scan Config.",
    "mesh":   "Mesh Router — periodic TP-Link Deco status snapshots. Set interval in Scan Config.",
    "syslog": "Syslog — UDP messages received on port 514 from routers and managed switches.",
    "snmp":   "SNMP Traps — trap PDUs received on port 162 from network devices.",
    "plugin": "Plugin — log entries emitted by installed NetSentinel plugins.",
}


def _source_key(label: str) -> str:
    return _LABEL_TO_KEY.get(label, label.lower())


def _fmt_ts(ts: float) -> str:
    dt = _dt.datetime.fromtimestamp(ts)
    if _t.time() - ts < 86400:
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%m-%d %H:%M")


def _status_color(status: str) -> str:
    return {"OK": _s.GREEN, "SLOW": _s.AMBER, "FAIL": _s.RED}.get(status.upper(), _s.TEXT_SECONDARY)


def _pill_seg_style(active: bool) -> str:
    """Live QSS for a Live/History pill segment button."""
    if active:
        return (
            f"QPushButton {{ background:{_s.ACCENT}; color:{_s.WHITE}; font-size:11px; font-weight:bold;"
            f" border:none; border-radius:11px; padding:2px 12px; }}"
        )
    return (
        f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:11px;"
        f" border:none; border-radius:11px; padding:2px 12px; }}"
        f"QPushButton:hover {{ color:{_s.TEXT_PRIMARY}; }}"
    )


def _build_live_scenario(entry, consecutive_fails: int = 0):
    """Return a one-step LabScenario for an interesting log entry, or None."""
    from modules.lab_scenarios import LabScenario, LabStep
    if entry.arp_event and entry.arp_event.startswith("NEW"):
        return LabScenario(
            id="live_new_device",
            title="New Device Detected",
            goal="A new device just appeared on your network. Investigate whether it belongs here.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"A new device appeared: {entry.arp_event}. "
                    "Run a scan to see all devices on your network and confirm it belongs."
                ),
                scan_type="rogue",
                hint="Look at the Risk column. An unexpected vendor or blank hostname may indicate a rogue device.",
                solution=(
                    "If the device has Risk = HIGH or an unexpected vendor, record its MAC address. "
                    "If it's one of your devices, whitelist it from the Overview page."
                ),
            )],
        )
    if entry.dns_ms >= 0 and entry.dns_ms > 200:
        return LabScenario(
            id="live_slow_dns",
            title="Slow DNS Detected",
            goal=f"DNS latency spiked to {entry.dns_ms:.0f} ms. Diagnose your resolver.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your DNS resolver just returned {entry.dns_ms:.0f} ms — above the 200 ms threshold. "
                    "Run the DNS check to measure it formally over 60 seconds."
                ),
                scan_type="dns",
                hint="A single high reading may be transient. The 60-second scan shows whether outages correlate with DNS failures.",
                solution=(
                    "If average DNS is consistently high, switch to 1.1.1.1 (Cloudflare) or "
                    "8.8.8.8 (Google) in your router's DNS settings."
                ),
            )],
        )
    if consecutive_fails >= 3:
        return LabScenario(
            id="live_connectivity_fail",
            title="Connectivity Issues Detected",
            goal="Multiple consecutive failures were logged. Diagnose your connection.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your logger recorded 3+ consecutive FAIL results to {entry.host}. "
                    "Run the DNS and stability check to determine whether this is a routing or DNS issue."
                ),
                scan_type="dns",
                hint="If pings fail but DNS works, the fault is upstream routing. If both fail together, try your DNS server settings.",
                solution=(
                    "Check your router first. If ping to 8.8.8.8 also fails, contact your ISP. "
                    "If only DNS fails, change the DNS server in your router settings to 1.1.1.1."
                ),
            )],
        )
    return None


# ── Mixin ─────────────────────────────────────────────────────────────────────

class _LogSourcePanelMixin:
    """Pure-Python mixin.  LogHubPage inherits this alongside QWidget."""

    # ── Scan configuration accordion ─────────────────────────────────────────

    def _build_scan_config_panel(self) -> QWidget:
        _qs = QSettings("NetSentinel", "NetSentinel")
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("accordionHeader")
        _s.themed_ss(header, "QFrame#accordionHeader {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        hdr_lay = QHBoxLayout(header)
        hdr_lay.setContentsMargins(12, 6, 12, 6)
        hdr_lay.setSpacing(8)
        toggle_btn = QToolButton()
        toggle_btn.setText("▶  Scan Configuration")
        toggle_btn.setCheckable(True)
        toggle_btn.setChecked(False)
        _s.themed_ss(toggle_btn, "QToolButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
            " font-weight:bold; border:none; padding:0; }}"
            "QToolButton:checked {{ color:{ACCENT}; }}"
            "QToolButton::menu-indicator {{ image:none; }}")
        hdr_lay.addWidget(toggle_btn)
        hdr_lay.addStretch()
        sub = QLabel("Controls which modules run when you click Scan")
        _s.themed_ss(sub, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        hdr_lay.addWidget(sub)
        outer_lay.addWidget(header)

        body = QFrame()
        body.setObjectName("accordionBody")
        body.setVisible(False)
        _s.themed_ss(body, "QFrame#accordionBody {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-top:none; border-radius:0 0 {CARD_RADIUS} {CARD_RADIUS}; }}")
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(16, 10, 16, 12)
        body_lay.setSpacing(8)

        _chk_qss = (
            "QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; padding:3px 0; }}"
            "QCheckBox::indicator {{ width:12px; height:12px; border:1px solid {BORDER};"
            " border-radius:2px; background:{BG_DARK}; }}"
            "QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        _spin_qss = (
            "QSpinBox {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:3px; padding:1px 4px; font-size:11px; }}"
        )

        def _chk_row(label: str, key: str) -> QCheckBox:
            chk = QCheckBox(label)
            chk.setChecked(_qs.value(f"scan/{key}_enabled", True, type=bool))
            _s.themed_ss(chk, _chk_qss)
            chk.toggled.connect(
                lambda v, k=key: QSettings("NetSentinel", "NetSentinel").setValue(
                    f"scan/{k}_enabled", v
                )
            )
            return chk

        def _spin_row(label: str, key: str, default: int) -> QWidget:
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lbl = QLabel(label)
            _s.themed_ss(lbl, "color:{TEXT_SECONDARY}; font-size:11px; background:transparent;")
            spin = QSpinBox()
            spin.setRange(5, 120)
            spin.setValue(_qs.value(f"scan/{key}_duration_s", default, type=int))
            spin.setFixedWidth(64)
            _s.themed_ss(spin, _spin_qss)
            spin.valueChanged.connect(
                lambda v, k=key: QSettings("NetSentinel", "NetSentinel").setValue(
                    f"scan/{k}_duration_s", v
                )
            )
            rl.addWidget(lbl)
            rl.addWidget(spin)
            rl.addStretch()
            return row

        grid = QWidget()
        grid.setStyleSheet("background:transparent;")
        gl = QHBoxLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(24)

        chk_col = QVBoxLayout()
        chk_col.setSpacing(4)
        chk_col.addWidget(_chk_row("STP detection",  "stp"))
        chk_col.addWidget(_chk_row("Storm analysis", "storm"))
        chk_col.addWidget(_chk_row("WiFi scan",      "wifi"))
        chk_col.addWidget(_chk_row("DNS check",      "dns"))
        gl.addLayout(chk_col)

        spin_col = QVBoxLayout()
        spin_col.setSpacing(4)
        spin_col.addWidget(_spin_row("STP listen (s):",   "stp",   10))
        spin_col.addWidget(_spin_row("Storm listen (s):", "storm", 10))
        spin_col.addStretch()
        gl.addLayout(spin_col)
        gl.addStretch()

        body_lay.addWidget(grid)
        outer_lay.addWidget(body)

        def _on_toggle(checked: bool) -> None:
            toggle_btn.setText(f"{'▼' if checked else '▶'}  Scan Configuration")
            body.setVisible(checked)

        toggle_btn.toggled.connect(_on_toggle)
        return outer

    # ── Control bar (search + source chips + live/history pill) ──────────────

    def _build_control_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("controlBar")
        _s.themed_ss(bar, "QFrame#controlBar {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…  (source:arp  ip:x  severity:critical)")
        self._search_box.setMinimumWidth(150)
        self._search_box.setMaximumWidth(230)
        self._search_box.setFixedHeight(26)
        self._search_box.setClearButtonEnabled(True)
        _s.themed_ss(self._search_box, "QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px;"
            " padding:1px 8px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}")
        self._search_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search_box)

        _div = QFrame()
        _div.setFrameShape(QFrame.Shape.VLine)
        _div.setFixedWidth(1)
        _s.themed_ss(_div, "background:{BORDER}; border:none;")
        lay.addWidget(_div)

        all_btn = QPushButton("● All")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.setFixedHeight(26)
        self._style_toggle(all_btn, True, "ACCENT")
        all_btn.clicked.connect(self._on_all_toggled)
        self._all_btn = all_btn
        lay.addWidget(all_btn)

        s = QSettings()
        for key, (label, color) in _SOURCES.items():
            default_on = key in ("net", "syslog", "snmp")
            enabled = s.value(f"logging/{key}_enabled", default_on, type=bool)
            btn = QPushButton(f"{'●' if enabled else '○'}  {label}")
            btn.setCheckable(True)
            btn.setChecked(enabled)
            btn.setFixedHeight(26)
            self._style_toggle(btn, enabled, color)
            btn.clicked.connect(lambda checked, k=key: self._on_source_toggled(k, checked))
            self._toggle_btns[key] = btn
            btn.setToolTip(_SOURCE_TIPS.get(key, ""))
            if key == "modem" and not enabled:
                btn.setToolTip("Enable modem logging in Scan Configuration to show here.")
            lay.addWidget(btn)
            btn.setVisible(enabled and key != "plugin")

        self._source_plus_btn = QPushButton("+")
        self._source_plus_btn.setFixedSize(26, 26)
        self._source_plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._source_plus_btn.setToolTip("Add source filter")
        _s.themed_ss(self._source_plus_btn, "QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:13px;"
            " font-weight:bold; border:1px solid {BORDER}; border-radius:4px; padding:0; }}"
            "QPushButton:hover {{ border-color:{ACCENT}; color:{ACCENT}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        self._source_plus_btn.clicked.connect(self._open_source_picker)
        lay.addWidget(self._source_plus_btn)
        lay.addStretch()

        _export_btn = QPushButton("↓ Export")
        _export_btn.setFixedHeight(26)
        _export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _export_btn.setToolTip("Export currently visible (filtered) rows to CSV")
        _s.themed_ss(_export_btn, lambda: (
            f"QPushButton {{ background:transparent; color:{_s.ACCENT}; font-size:11px;"
            f" font-weight:600; border:1px solid {alpha(_s.ACCENT, 0x44)}; border-radius:4px; padding:0 8px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x11)}; border-color:{_s.ACCENT}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
        ))
        _export_btn.clicked.connect(self._export_visible)
        lay.addWidget(_export_btn)

        _pill = QFrame()
        _pill.setObjectName("liveHistoryPill")
        _s.themed_ss(_pill, "QFrame#liveHistoryPill {{ background:{BG_DARK}; border:1px solid {BORDER}; border-radius:13px; }}")
        _pill_lay = QHBoxLayout(_pill)
        _pill_lay.setContentsMargins(2, 2, 2, 2)
        _pill_lay.setSpacing(0)
        self._live_mode_btn = QPushButton("● Live")
        self._live_mode_btn.setFixedHeight(24)
        self._live_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._live_mode_btn, lambda: _pill_seg_style(True))
        self._live_mode_btn.clicked.connect(self._on_mode_live)
        self._hist_mode_btn = QPushButton("⊙ History")
        self._hist_mode_btn.setFixedHeight(24)
        self._hist_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._hist_mode_btn, lambda: _pill_seg_style(False))
        self._hist_mode_btn.clicked.connect(self._on_mode_history)
        _pill_lay.addWidget(self._live_mode_btn)
        _pill_lay.addWidget(self._hist_mode_btn)
        lay.addWidget(_pill)
        return bar

    def _open_source_picker(self) -> None:
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER}; border-radius:4px; padding:2px; }}"
            f"QMenu::item {{ padding:5px 14px; color:{_s.TEXT_PRIMARY}; font-size:11px; }}"
            f"QMenu::item:selected {{ background:{alpha(_s.ACCENT, 0x22)}; color:{_s.TEXT_PRIMARY}; }}"
        )
        has_hidden = False
        for key, (label, _color) in _SOURCES.items():
            btn = self._toggle_btns.get(key)
            if btn and not btn.isVisible():
                action = menu.addAction(f"+ {label}")
                action.triggered.connect(lambda _, k=key: self._reveal_source_chip(k))
                has_hidden = True
        if not has_hidden:
            return
        pos = self._source_plus_btn.mapToGlobal(self._source_plus_btn.rect().bottomLeft())
        menu.exec(pos)

    def _reveal_source_chip(self, key: str) -> None:
        btn = self._toggle_btns.get(key)
        if btn:
            btn.setVisible(True)
            btn.setChecked(True)
            self._on_source_toggled(key, True)

    # ── Source bar (separate from control bar — used in some layouts) ─────────

    def _build_source_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("sourceBar")
        _s.themed_ss(bar, "QFrame#sourceBar {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(6)
        lbl = QLabel("Show:")
        _s.themed_ss(lbl, "color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;")
        lay.addWidget(lbl)
        all_btn = QPushButton("● All")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.setFixedHeight(26)
        self._style_toggle(all_btn, True, "ACCENT")
        all_btn.clicked.connect(self._on_all_toggled)
        self._all_btn = all_btn
        lay.addWidget(all_btn)
        s = QSettings()
        for key, (label, color) in _SOURCES.items():
            default_on = key in ("net", "syslog", "snmp")
            enabled = s.value(f"logging/{key}_enabled", default_on, type=bool)
            btn = QPushButton(f"{'●' if enabled else '○'}  {label}")
            btn.setCheckable(True)
            btn.setChecked(enabled)
            btn.setFixedHeight(26)
            self._style_toggle(btn, enabled, color)
            btn.clicked.connect(lambda checked, k=key: self._on_source_toggled(k, checked))
            self._toggle_btns[key] = btn
            lay.addWidget(btn)
            if key == "plugin":
                btn.setVisible(False)
            if key == "modem" and not enabled:
                btn.setToolTip("Connect a modem plugin to enable modem logging.")
        cfg_lbl = QLabel("· Configure in Network Logger")
        _s.themed_ss(cfg_lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        lay.addWidget(cfg_lbl)
        lay.addStretch()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…  (source:arp  ip:x  severity:critical)")
        self._search_box.setFixedWidth(260)
        self._search_box.setFixedHeight(26)
        self._search_box.setClearButtonEnabled(True)
        _s.themed_ss(self._search_box, "QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px;"
            " padding:1px 8px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            "QLineEdit:focus {{ border-color:{ACCENT}; }}")
        self._search_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search_box)
        return bar

    # ── Mode bar (Live / History) ─────────────────────────────────────────────

    def _build_mode_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("modeBar")
        _s.themed_ss(bar, "QFrame#modeBar {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(4)
        _seg_on = (
            f"QPushButton {{ background:{_s.ACCENT}; color:{_s.WHITE}; font-size:11px; font-weight:bold;"
            f" border:none; border-radius:3px; padding:2px 14px; }}"
        )
        _seg_off = (
            f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:11px;"
            f" border:none; border-radius:3px; padding:2px 14px; }}"
            f"QPushButton:hover {{ color:{_s.TEXT_PRIMARY}; background:{_s.BG_HOVER}; }}"
        )
        self._live_mode_btn = QPushButton("● Live")
        self._live_mode_btn.setFixedHeight(24)
        self._live_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._live_mode_btn.setStyleSheet(_seg_on)
        self._live_mode_btn.clicked.connect(self._on_mode_live)
        self._hist_mode_btn = QPushButton("⊙ History")
        self._hist_mode_btn.setFixedHeight(24)
        self._hist_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hist_mode_btn.setStyleSheet(_seg_off)
        self._hist_mode_btn.clicked.connect(self._on_mode_history)
        lay.addWidget(self._live_mode_btn)
        lay.addWidget(self._hist_mode_btn)
        lay.addStretch()
        hint = QLabel("History mode queries your database for any time range")
        _s.themed_ss(hint, "font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;")
        lay.addWidget(hint)
        return bar

    # ── Logged sources bar ────────────────────────────────────────────────────

    def _build_logged_sources_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("loggedSourcesBar")
        _s.themed_ss(bar, "QFrame#loggedSourcesBar {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)
        hdr = QLabel("LOGGING TO DATABASE")
        _s.themed_ss(hdr, "color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
            " letter-spacing:0.08em; background:transparent; border:none;")
        lay.addWidget(hdr)
        self._plugin_db_empty_lbl = QLabel(
            "No hardware plugins configured — add one in Hardware Integrations"
        )
        _s.themed_ss(self._plugin_db_empty_lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        lay.addWidget(self._plugin_db_empty_lbl)
        self._plugin_db_container = QWidget()
        self._plugin_db_container.setStyleSheet("background:transparent;")
        self._plugin_db_container_lay = QVBoxLayout(self._plugin_db_container)
        self._plugin_db_container_lay.setContentsMargins(0, 0, 0, 0)
        self._plugin_db_container_lay.setSpacing(6)
        lay.addWidget(self._plugin_db_container)
        self._db_feedback_lbl = QLabel("")
        _s.themed_ss(self._db_feedback_lbl, "color:{GREEN}; font-size:10px; background:transparent; border:none;")
        self._db_feedback_lbl.setVisible(False)
        lay.addWidget(self._db_feedback_lbl)
        return bar

    # ── DB toggle styling and handlers ────────────────────────────────────────

    def _style_db_btn(self, btn: QPushButton, enabled: bool) -> None:
        if enabled:
            _s.themed_ss(btn, lambda: (
                f"QPushButton {{ background:{alpha(_s.GREEN, 0x22)}; color:{_s.GREEN}; font-size:10px;"
                f" font-weight:bold; border:1px solid {_s.GREEN}; border-radius:11px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{alpha(_s.GREEN, 0x44)}; }}"
                f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
            ))
        else:
            _s.themed_ss(btn, (
                "QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                " border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                "QPushButton:hover {{ background:{BG_HOVER}; }}"
                "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            ))

    def _on_db_toggled(self, key: str, checked: bool, btn: QPushButton) -> None:
        label = _SOURCES[key][0]
        btn.setText("● Logging to DB" if checked else "○  Not logging  ")
        self._style_db_btn(btn, checked)
        QSettings("NetSentinel", "NetSentinel").setValue(f"logging/{key}_enabled", checked)
        if checked:
            self._show_db_feedback(f"{label} data will be saved to your database.", _s.GREEN)
        else:
            self._show_db_feedback(
                f"{label} logging stopped. History recorded so far is preserved.", _s.TEXT_SECONDARY
            )

    def _on_interval_changed(self, key: str, combo: QComboBox) -> None:
        val = combo.currentData()
        if val is not None:
            QSettings("NetSentinel", "NetSentinel").setValue(f"logging/{key}_interval_min", val)

    def _show_db_feedback(self, msg: str, color: str) -> None:
        self._db_feedback_lbl.setText(msg)
        self._db_feedback_lbl.setStyleSheet(
            f"color:{color}; font-size:10px; background:transparent; border:none;"
        )
        self._db_feedback_lbl.setVisible(True)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: self._db_feedback_lbl.setVisible(False))
        _t.start(3000)

    # ── Challenge banner ──────────────────────────────────────────────────────

    def _show_challenge_banner(self, time_str: str) -> None:
        self._challenge_time_lbl.setText(f"Live challenge detected at {time_str} — ")
        self._challenge_banner_ts = _t.time()
        self._challenge_banner.setVisible(True)
        self._challenge_timer.start(60_000)

    def _hide_challenge_banner(self) -> None:
        self._challenge_timer.stop()
        self._challenge_banner.setVisible(False)

    # ── Mode switching ────────────────────────────────────────────────────────

    def _on_mode_live(self) -> None:
        self._is_history_mode = False
        _s.themed_ss(self._live_mode_btn, lambda: _pill_seg_style(True))
        _s.themed_ss(self._hist_mode_btn, lambda: _pill_seg_style(False))
        self._history_bar.setVisible(False)
        self._apply_filter()

    def _on_mode_history(self) -> None:
        self._is_history_mode = True
        _s.themed_ss(self._hist_mode_btn, lambda: _pill_seg_style(True))
        _s.themed_ss(self._live_mode_btn, lambda: _pill_seg_style(False))
        self._history_bar.setVisible(True)
        self._load_history_range()

    def _load_history_range(self) -> None:
        fd = self._hist_from_date.date().toPyDate()
        ft = _dt.time(self._hist_from_time.time().hour(), self._hist_from_time.time().minute())
        td = self._hist_to_date.date().toPyDate()
        tt = _dt.time(self._hist_to_time.time().hour(), self._hist_to_time.time().minute(), 59)
        ts_start = _dt.datetime.combine(fd, ft).timestamp()
        ts_end   = _dt.datetime.combine(td, tt).timestamp()
        rows: list = []
        for e in self._entries:
            if ts_start <= e["ts"] <= ts_end:
                rows.append(e)
        if self._store:
            hours = max(1, int((ts_end - ts_start) / 3600) + 1)
            try:
                for p in self._store.query_modem_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        rows.append(self._modem_point_to_entry(p))
            except Exception:
                pass  # non-fatal
            try:
                for p in self._store.query_mesh_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        rows.append(self._make_entry(
                            "mesh", float(p.ts), "Mesh system",
                            f"{p.online_count}/{p.unit_count} units",
                            "  ·  ".join(parts), "OK",
                        ))
            except Exception:
                pass  # non-fatal
            try:
                for row in self._store.query_plugin_log(hours=hours, limit=10_000):
                    if ts_start <= float(row.get("ts", 0)) <= ts_end:
                        rows.append(self._plugin_row_to_entry(row))
            except Exception:
                pass  # non-fatal
        rows.sort(key=lambda e: e["ts"], reverse=True)
        rows = rows[:_MAX_ROWS]
        filt = self._search_box.text().strip().lower()
        visible = [
            e for e in rows
            if self._is_source_enabled(e["source_key"])
            and (not filt or self._row_matches(e["row"], filt))
        ]
        self._table.setRowCount(0)
        for i, e in enumerate(visible):
            self._table.insertRow(i)
            self._set_table_row(i, e)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_visible(self) -> None:
        filt = self._search_box.text().strip().lower()
        visible = [
            e for e in self._entries
            if self._is_source_enabled(e["source_key"])
            and self._entry_matches(e, filt)
        ]
        if not visible:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Export", "No rows match the current filter.")
            return
        ts_label = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Filtered Log CSV",
            f"netsentinel_log_filtered_{ts_label}.csv",
            "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        headers = [
            self._table.horizontalHeaderItem(c).text()
            for c in range(self._table.columnCount())
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = _csv.writer(fh)
                w.writerow(headers)
                for e in visible:
                    w.writerow(list(e["row"]))
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export failed", str(exc))

    def _open_export_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Export Log")
        dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 12)
        today = _dt.date.today()
        week_ago = today - _dt.timedelta(days=7)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("From:"))
        from PyQt6.QtCore import QDate
        start_edit = QDateEdit(dlg)
        start_edit.setCalendarPopup(True)
        start_edit.setDate(QDate(week_ago.year, week_ago.month, week_ago.day))
        row1.addWidget(start_edit)
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("To:"))
        end_edit = QDateEdit(dlg)
        end_edit.setCalendarPopup(True)
        end_edit.setDate(QDate(today.year, today.month, today.day))
        row2.addWidget(end_edit)
        lay.addLayout(row2)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Export CSV")
        btns.accepted.connect(lambda: self._do_export(
            start_edit.date().toPyDate(), end_edit.date().toPyDate(), dlg
        ))
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()

    def _do_export(self, start, end, dlg: QDialog) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log CSV",
            f"netsentinel_log_{start}_{end}.csv", "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        ts_start = _dt.datetime.combine(start, _dt.time.min).timestamp()
        ts_end   = _dt.datetime.combine(end,   _dt.time.max).timestamp()
        rows: list = []
        for e in self._entries:
            if ts_start <= e["ts"] <= ts_end:
                r = e["row"]
                rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))
        if self._store:
            hours = max(1, int((ts_end - ts_start) / 3600) + 1)
            try:
                for p in self._store.query_modem_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        e = self._modem_point_to_entry(p)
                        r = e["row"]
                        rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))
            except Exception:
                pass  # non-fatal
            try:
                for p in self._store.query_mesh_signal_log(hours=hours, limit=10_000):
                    if ts_start <= float(p.ts) <= ts_end:
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        rows.append((_fmt_ts(float(p.ts)), "MESH", "Mesh system",
                                     f"{p.online_count}/{p.unit_count} units",
                                     "  ·  ".join(parts), "OK"))
            except Exception:
                pass  # non-fatal
            try:
                for row in self._store.query_plugin_log(hours=hours, limit=10_000):
                    if ts_start <= float(row.get("ts", 0)) <= ts_end:
                        e = self._plugin_row_to_entry(row)
                        r = e["row"]
                        rows.append((_fmt_ts(e["ts"]), r[1], r[2], r[3], r[4], r[5]))
            except Exception:
                pass  # non-fatal
        rows.sort(key=lambda r: r[0])
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(["Time", "Source", "Host", "Event", "Detail", "Status"])
                w.writerows(rows)
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        dlg.accept()

    # ── Plugin source management ──────────────────────────────────────────────

    def update_plugin_sources(self, names: list) -> None:
        while self._plugin_db_container_lay.count():
            item = self._plugin_db_container_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        btn = self._toggle_btns.get("plugin")
        if btn:
            btn.setVisible(bool(names))
        self._plugin_db_empty_lbl.setVisible(not bool(names))
        _qs = QSettings("NetSentinel", "NetSentinel")
        for name in names:
            qs_key = f"plugin_{name.lower().replace(' ', '_')}"
            enabled = _qs.value(f"logging/{qs_key}_enabled", False, type=bool)
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(8)
            src_lbl = QLabel(f"● {name}")
            src_lbl.setFixedWidth(120)
            src_lbl.setStyleSheet(
                f"color:{LOG_SOURCE_PLUGIN}; font-size:11px; font-weight:bold;"
                f" background:transparent; border:none;"
            )
            row_l.addWidget(src_lbl)
            db_btn = QPushButton("● Logging to DB" if enabled else "○  Not logging  ")
            db_btn.setCheckable(True)
            db_btn.setChecked(enabled)
            db_btn.setFixedHeight(22)
            db_btn.setFixedWidth(130)
            self._style_db_btn(db_btn, enabled)
            db_btn.clicked.connect(
                lambda checked, n=name, k=qs_key, b=db_btn:
                self._on_plugin_db_toggled(n, k, checked, b)
            )
            row_l.addWidget(db_btn)
            row_l.addStretch()
            self._plugin_db_container_lay.addWidget(row_w)

    def _on_plugin_db_toggled(
        self, name: str, qs_key: str, checked: bool, btn: QPushButton
    ) -> None:
        btn.setText("● Logging to DB" if checked else "○  Not logging  ")
        self._style_db_btn(btn, checked)
        QSettings("NetSentinel", "NetSentinel").setValue(f"logging/{qs_key}_enabled", checked)
        self.logging_active_changed.emit(checked)
        if checked:
            self._show_db_feedback(f"{name} data will be saved to your database.", _s.GREEN)
        else:
            self._show_db_feedback(
                f"{name} logging stopped. History recorded so far is preserved.", _s.TEXT_SECONDARY
            )

    # ── Source toggle helpers ─────────────────────────────────────────────────

    def _style_toggle(self, btn: QPushButton, enabled: bool, color_name: str) -> None:
        """color_name: a ui/styles.py token NAME (e.g. "ACCENT"), not a resolved value."""
        if enabled:
            _s.themed_ss(btn, lambda c=color_name: (
                f"QPushButton {{ background:{getattr(_s, c)}22; color:{getattr(_s, c)}; font-size:11px;"
                f" font-weight:bold; border:1px solid {getattr(_s, c)}; border-radius:12px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{getattr(_s, c)}44; }}"
                f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
            ))
        else:
            _s.themed_ss(btn, (
                "QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:11px;"
                " border:1px solid {BORDER}; border-radius:12px; padding:1px 10px; }}"
                "QPushButton:hover {{ background:{BG_HOVER}; }}"
                "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            ))

    def _on_source_toggled(self, key: str, checked: bool) -> None:
        label, color = _SOURCES[key]
        btn = self._toggle_btns[key]
        btn.setText(f"{'●' if checked else '○'}  {label}")
        self._style_toggle(btn, checked, color)
        self._sync_all_btn()
        self._apply_filter()
        # Switch content stack: show card when any source is on, empty state when all off
        if hasattr(self, "_content_stack"):
            any_on = any(b.isChecked() for b in self._toggle_btns.values())
            self._content_stack.setCurrentIndex(1 if any_on else 0)

    def _on_all_toggled(self) -> None:
        for key, btn in self._toggle_btns.items():
            if not btn.isChecked():
                btn.setChecked(True)
                label, color = _SOURCES[key]
                btn.setText(f"●  {label}")
                self._style_toggle(btn, True, color)
        if self._all_btn:
            self._all_btn.setChecked(True)
            self._style_toggle(self._all_btn, True, "ACCENT")
        self._apply_filter()

    def _sync_all_btn(self) -> None:
        if self._all_btn is None:
            return
        all_on = all(
            btn.isChecked()
            for btn in self._toggle_btns.values()
            if btn.isVisible()
        )
        self._all_btn.setChecked(all_on)
        self._style_toggle(self._all_btn, all_on, "ACCENT")

    def _is_source_enabled(self, key: str) -> bool:
        btn = self._toggle_btns.get(key)
        return btn.isChecked() if btn else False

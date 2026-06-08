"""
home_session_widgets.py — Session and onboarding widgets for the Home page.

Extracted from ui/widgets/home_widgets.py (Sprint 17) to keep that file within budget.
Contains: FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog,
          StandardWelcomePage, ProWelcomePage.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE, AMBER,
    BG_CARD, BG_DARK, BORDER,
    CARD_RADIUS, GRADE_B_COLOR, GREEN, NAV_BAR,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.widgets.home_widgets import _bundled_plugin_path


# ── FreshnessStrip ────────────────────────────────────────────────────────────

class FreshnessStrip(QFrame):
    """Top-of-page strip: last-scan timestamp, monitor status pills, scan progress."""

    rescan_requested = pyqtSignal()
    navigate_to      = pyqtSignal(str)   # emitted when an inactive pill is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("freshnessStrip")
        self.setFixedHeight(30)
        self.setStyleSheet(
            f"QFrame#freshnessStrip {{ background:{NAV_BAR}; border-bottom:1px solid {BORDER}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 0, 8, 0)
        row.setSpacing(12)

        self._fs_scan_lbl = QLabel("Last scan: —")
        self._fs_scan_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        row.addWidget(self._fs_scan_lbl)

        _sep = QLabel("|")
        _sep.setStyleSheet(f"font-size:11px; color:{BORDER}; background:transparent; border:none;")
        row.addWidget(_sep)

        # Pills are QPushButton (flat) so they support tooltips and click events
        self._fs_pill_arp   = self._make_fs_pill("ARP")
        self._fs_pill_dhcp  = self._make_fs_pill("DHCP")
        self._fs_pill_storm = self._make_fs_pill("Storm")
        self._fs_pill_log   = self._make_fs_pill("Logger")
        _pill_nav = {
            self._fs_pill_arp:   "ARP Spoof Watch",
            self._fs_pill_dhcp:  "DHCP Leases",
            self._fs_pill_storm: "Broadcast Storm",
            self._fs_pill_log:   "Log Hub",
        }
        self._fs_pill_active: dict = {p: False for p in _pill_nav}
        for pill, nav_label in _pill_nav.items():
            _nav = nav_label
            pill.clicked.connect(
                lambda _=False, p=pill, n=_nav: self._on_pill_clicked(p, n)
            )
            row.addWidget(pill)

        _sep2 = QLabel("|")
        _sep2.setStyleSheet(f"font-size:11px; color:{BORDER}; background:transparent; border:none;")
        row.addWidget(_sep2)

        self._fs_next_scan_lbl = QLabel("")
        self._fs_next_scan_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        row.addWidget(self._fs_next_scan_lbl)
        self.refresh_next_scan_label()

        row.addStretch()

        self._scan_progress_lbl = QLabel("")
        self._scan_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{AMBER}; background:transparent; border:none;"
        )
        self._scan_progress_lbl.setVisible(False)
        row.addWidget(self._scan_progress_lbl)

        _btn = QPushButton("↻")
        _btn.setFixedSize(24, 22)
        _btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _btn.setToolTip("Rescan network")
        _btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:none;"
            f" font-size:14px; border-radius:3px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:{BORDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:{BORDER}; }}"
        )
        _btn.clicked.connect(self.rescan_requested)
        row.addWidget(_btn)

        qs = QSettings("NetSentinel", "NetSentinel")
        _ts = qs.value("home/last_scan_ts", "")
        if _ts:
            try:
                _dt = datetime.datetime.fromisoformat(_ts)
                self._fs_scan_lbl.setText(f"Last scan: {self._fmt_age(_dt)}")
            except ValueError:
                pass  # ignore invalid timestamp

    @staticmethod
    def _make_fs_pill(label: str) -> QPushButton:
        btn = QPushButton(f"○ {label}")
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ font-size:10px; color:{TEXT_MUTED}; background:transparent;"
            f" border:none; padding:0 2px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        return btn

    @staticmethod
    def _fmt_age(dt: datetime.datetime) -> str:
        delta = datetime.datetime.now() - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60} min ago"
        if secs < 86400:
            h = secs // 3600
            return f"{h} hour{'s' if h != 1 else ''} ago"
        d = secs // 86400
        return f"{d} day{'s' if d != 1 else ''} ago"

    def _on_pill_clicked(self, pill: QPushButton, nav_label: str) -> None:
        if not self._fs_pill_active.get(pill, True):
            self.navigate_to.emit(nav_label)

    def update_freshness(self, arp: bool = False, dhcp: bool = False,
                          storm: bool = False, logger: bool = False) -> None:
        _PILL_OFF_TIPS = {
            "ARP":    "ARP Spoof Watch is OFF — click to enable real-time spoofing detection.",
            "DHCP":   "DHCP Rogue detection is OFF — click to go to the DHCP page.",
            "Storm":  "Broadcast Storm monitor is OFF — click to go to the Storm page.",
            "Logger": "Network Logger is OFF — click to start recording RTT and DNS every 30 s.",
        }
        _PILL_ON_TIPS = {
            "ARP":    "ARP Spoof Watch is ON — detecting address-spoofing attacks in real time.",
            "DHCP":   "DHCP Rogue detection is ON — watching for rogue DHCP servers.",
            "Storm":  "Broadcast Storm monitor is ON — watching for packet storms.",
            "Logger": "Network Logger is ON — recording RTT and DNS every 30 s.",
        }

        def _set_pill(pill: QPushButton, active: bool, name: str) -> None:
            self._fs_pill_active[pill] = active
            if active:
                pill.setText(f"● {name}")
                pill.setStyleSheet(
                    f"QPushButton {{ font-size:10px; color:{GREEN}; background:transparent;"
                    f" border:none; padding:0 2px; }}"
                    f"QPushButton:hover {{ color:{GREEN}; background:transparent; }}"
                    f"QPushButton:pressed {{ color:{GREEN}; background:transparent; }}"
                )
                pill.setToolTip(_PILL_ON_TIPS.get(name, ""))
            else:
                pill.setText(f"○ {name}")
                pill.setStyleSheet(
                    f"QPushButton {{ font-size:10px; color:{TEXT_MUTED}; background:transparent;"
                    f" border:none; padding:0 2px; }}"
                    f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
                    f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
                )
                pill.setToolTip(_PILL_OFF_TIPS.get(name, ""))

        _set_pill(self._fs_pill_arp,   arp,    "ARP")
        _set_pill(self._fs_pill_dhcp,  dhcp,   "DHCP")
        _set_pill(self._fs_pill_storm, storm,  "Storm")
        _set_pill(self._fs_pill_log,   logger, "Logger")

    def refresh_next_scan_label(self) -> None:
        import time as _t
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            self._fs_next_scan_lbl.setVisible(False)
            return
        next_ts = float(qs.value("sched_scan/next_ts", 0))
        self._fs_next_scan_lbl.setVisible(True)
        if next_ts > _t.time():
            nxt = datetime.datetime.fromtimestamp(next_ts)
            now = datetime.datetime.now()
            if nxt.date() == now.date():
                self._fs_next_scan_lbl.setText(f"Next scan: today {nxt.strftime('%H:%M')}")
            elif (nxt.date() - now.date()).days == 1:
                self._fs_next_scan_lbl.setText(f"Next scan: tomorrow {nxt.strftime('%H:%M')}")
            else:
                self._fs_next_scan_lbl.setText(f"Next scan: {nxt.strftime('%a %H:%M')}")
        else:
            self._fs_next_scan_lbl.setText("Next scan: pending")

    def set_scan_progress(self, message: str) -> None:
        if not message:
            self._scan_progress_lbl.setVisible(False)
            self._scan_progress_lbl.setText("")
            return
        text = message if len(message) <= 60 else message[:57] + "…"
        self._scan_progress_lbl.setText(text)
        self._scan_progress_lbl.setVisible(True)

    def set_scan_timestamp(self, text: str, style: str = "") -> None:
        self._fs_scan_lbl.setText(text)
        if style:
            self._fs_scan_lbl.setStyleSheet(style)

    def update_logger_tooltip(self, since_str: str = "", last_entry_str: str = "",
                              rtt_str: str = "") -> None:
        """Update Logger pill tooltip with live data when logger is active."""
        if not self._fs_pill_active.get(self._fs_pill_log, False):
            return
        parts = ["Network Logger is ON"]
        if since_str:
            parts.append(f"logging since {since_str}")
        if last_entry_str:
            parts.append(f"Last entry: {last_entry_str}")
        if rtt_str:
            parts.append(f"RTT: {rtt_str}")
        self._fs_pill_log.setToolTip("  ·  ".join(parts))


# ── GettingStartedCard ────────────────────────────────────────────────────────

class GettingStartedCard(QFrame):
    """Onboarding checklist: hardware connections + core setup steps."""

    add_plugin_requested = pyqtSignal(str)
    navigate_to = pyqtSignal(str)
    completion_done = pyqtSignal()  # emitted 2 s after all steps are complete

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("gettingStartedCard")
        self.setStyleSheet(
            f"QFrame#gettingStartedCard {{"
            f" background:{BG_CARD};"
            f" border:1px solid {BORDER};"
            f" border-left:3px solid {ACCENT};"
            f" border-radius:{CARD_RADIUS};"
            f"}}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 12, 12)
        outer.setSpacing(0)

        self._setup_collapsed = False
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(8)

        self._setup_hdr_lbl = QLabel("GETTING STARTED")
        self._setup_hdr_lbl.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{ACCENT};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        self._setup_progress_lbl = QLabel("")
        self._setup_progress_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        self._setup_collapse_btn = QPushButton("▼")
        self._setup_collapse_btn.setFixedSize(18, 18)
        self._setup_collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_collapse_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:10px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        self._setup_collapse_btn.clicked.connect(self._toggle_collapse)
        hdr_row.addWidget(self._setup_hdr_lbl)
        hdr_row.addWidget(self._setup_progress_lbl)
        hdr_row.addStretch()
        hdr_row.addWidget(self._setup_collapse_btn)
        outer.addLayout(hdr_row)

        self._setup_body = QWidget()
        self._setup_body.setStyleSheet("background:transparent;")
        body_lay = QVBoxLayout(self._setup_body)
        body_lay.setContentsMargins(0, 8, 0, 0)
        body_lay.setSpacing(0)

        zte_path  = _bundled_plugin_path("zte_plugin.py")
        deco_path = _bundled_plugin_path("deco_plugin.py")

        # Step order: scan first (gives data), then hardware (enriches data), then grade/arp/logger
        _STEPS = [
            ("scan",    "Run your first scan",
             "Discover all devices on your network",
             None, "Devices"),
            ("hw_deco", "Connect your router",
             "Get real device names, signal strength, and your full network map",
             deco_path, None),
            ("hw_zte",  "Connect your modem",
             "See signal quality in every speed test — critical for ISP accountability",
             zte_path, None),
            ("grade",   "Run a Network Grade",
             "Score your network across 8 dimensions",
             None, "Network Grade"),
            ("arp",     "Turn on ARP Spoof Watch",
             "Detect address spoofing in real time",
             None, "ARP Spoof Watch"),
            ("logger",  "Start the Network Logger",
             "Records RTT and DNS every 30 s — leave it on for daily insights",
             None, "Log Hub"),
        ]

        self._setup_check_lbls:   dict[str, QLabel]       = {}
        self._setup_step_rows:    dict[str, QWidget]      = {}
        self._setup_step_btns:    dict[str, QPushButton]  = {}
        self._setup_title_lbls:   dict[str, QLabel]       = {}
        self._setup_plugin_paths: dict[str, str]          = {}

        for key, title, subtitle, plugin_path, nav_target in _STEPS:
            if plugin_path:
                self._setup_plugin_paths[key] = plugin_path

            row = QWidget()
            row.setObjectName(f"setupRow_{key}")
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 3, 0, 3)
            rl.setSpacing(8)

            chk = QLabel("○")
            chk.setFixedWidth(14)
            chk.setStyleSheet(
                f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            self._setup_check_lbls[key] = chk

            text_col = QVBoxLayout()
            text_col.setSpacing(1)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(
                f"font-size:11px; font-weight:500; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._setup_title_lbls[key] = title_lbl
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            text_col.addWidget(title_lbl)
            text_col.addWidget(sub_lbl)

            if plugin_path:
                btn = QPushButton("Add →")
                btn.setFixedHeight(24)
                btn.setFixedWidth(72)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
                    f" border-radius:3px; font-size:10px; font-weight:600; padding:0 8px; }}"
                    f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
                    f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
                )
                _p = plugin_path
                btn.clicked.connect(lambda _=False, p=_p: self.add_plugin_requested.emit(p))
            else:
                btn = QPushButton("→")
                btn.setFlat(True)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setStyleSheet(
                    f"QPushButton {{ color:{ACCENT}; font-size:14px; background:transparent;"
                    f" border:none; padding:0 4px; }}"
                    f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
                    f"QPushButton:pressed {{ color:{ACCENT_DARK}; background:transparent; }}"
                )
                _t = nav_target
                btn.clicked.connect(lambda _=False, t=_t: self.navigate_to.emit(t))

            self._setup_step_btns[key] = btn
            self._setup_step_rows[key] = row

            rl.addWidget(chk)
            rl.addLayout(text_col, 1)
            rl.addWidget(btn)
            body_lay.addWidget(row)

        outer.addWidget(self._setup_body)

    def _toggle_collapse(self) -> None:
        self._setup_collapsed = not self._setup_collapsed
        self._setup_body.setVisible(not self._setup_collapsed)
        self._setup_collapse_btn.setText("▶" if self._setup_collapsed else "▼")

    def ensure_expanded(self) -> None:
        self.setVisible(True)
        if self._setup_collapsed:
            self._toggle_collapse()

    def _checklist_states(self, device_count: int = 0) -> dict:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            raw = qs.value("hardware/custom_scripts", "[]") or "[]"
            imported = set(_json.loads(raw))
        except Exception:
            imported = set()
        zte_path  = _bundled_plugin_path("zte_plugin.py")
        deco_path = _bundled_plugin_path("deco_plugin.py")
        return {
            "scan":    device_count > 0,
            "hw_deco": deco_path in imported,
            "hw_zte":  zte_path  in imported,
            "grade":   qs.value("grade/last_run", False, type=bool),
            "arp":     qs.value("home/setup/arp_started", False, type=bool),
            "logger":  qs.value("logger_started_once", False, type=bool),
        }

    def refresh_checklist(self, device_count: int = 0) -> None:
        if not hasattr(self, "_setup_check_lbls"):
            return
        states = self._checklist_states(device_count)
        done_count = sum(states.values())
        total = len(states)
        for key, chk in self._setup_check_lbls.items():
            done = states.get(key, False)
            if done:
                chk.setText("✓")
                chk.setStyleSheet(
                    f"font-size:13px; color:{GREEN}; background:transparent; border:none;"
                )
                btn = self._setup_step_btns.get(key)
                if btn:
                    btn.setEnabled(False)
                    if key.startswith("hw_"):
                        btn.setText("✓ Added")
                    btn.setStyleSheet(
                        f"QPushButton {{ color:{GREEN}; font-size:10px; background:transparent;"
                        f" border:none; padding:0 4px; }}"
                        f"QPushButton:hover   {{ color:{GREEN}; background:transparent; }}"
                        f"QPushButton:pressed {{ color:{GREEN}; background:transparent; }}"
                        f"QPushButton:disabled {{ color:{GREEN}; background:transparent; }}"
                    )
            else:
                chk.setText("○")
                chk.setStyleSheet(
                    f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
                )
        self._setup_progress_lbl.setText(f"{done_count}/{total} done")
        if done_count == total:
            self._setup_hdr_lbl.setText("✓ SETUP COMPLETE")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; font-weight:700; color:{GREEN};"
                " background:transparent; border:none; letter-spacing:1.5px;"
            )
            from PyQt6.QtCore import QTimer as _QT
            _QT.singleShot(2000, self.completion_done.emit)
        else:
            self._setup_hdr_lbl.setText("GETTING STARTED")
            self._setup_hdr_lbl.setStyleSheet(
                f"font-size:10px; font-weight:700; color:{ACCENT};"
                " background:transparent; border:none; letter-spacing:1.5px;"
            )

    def notify_hw_detected(self, hw_type: str) -> None:
        """Mark a hardware step as 'detected nearby' with amber indicator."""
        from ui.styles import AMBER
        key_map = {"modem": "hw_zte", "router": "hw_deco"}
        key = key_map.get(hw_type)
        if not key:
            return
        states = self._checklist_states()
        if states.get(key):
            return  # already added — don't downgrade to detected
        chk = self._setup_check_lbls.get(key)
        btn = self._setup_step_btns.get(key)
        if chk:
            chk.setText("◉")
            chk.setStyleSheet(
                f"font-size:13px; color:{AMBER}; background:transparent; border:none;"
            )
        if btn and btn.isEnabled():
            btn.setText("Add it now →")


# ── _GradeBreakdownDialog ─────────────────────────────────────────────────────

class _GradeBreakdownDialog:
    """QDialog showing the grade sub-score breakdown."""

    def __new__(cls, grade: str, dimensions: list, parent=None):
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel,
            QScrollArea, QWidget, QFrame, QPushButton,
        )
        from PyQt6.QtCore import Qt
        from ui.styles import (
            ACCENT, AMBER, BG_CARD, BG_DARK, BORDER, GREEN, RED,
            TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
        )

        _GRADE_COLOR = {
            "A": GREEN, "B": GRADE_B_COLOR, "C": AMBER, "D": RED, "F": RED,
        }

        dlg = QDialog(parent)
        dlg.setWindowTitle("Network Grade Breakdown")
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet(f"QDialog {{ background:{BG_DARK}; }}")

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        hdr_row = QHBoxLayout()
        overall_lbl = QLabel(grade)
        _fg = _GRADE_COLOR.get(grade, TEXT_SECONDARY)
        overall_lbl.setStyleSheet(
            f"font-size:36px; font-weight:bold; color:{_fg};"
            f" background:{BG_CARD}; border:3px solid {_fg}; border-radius:28px;"
            f" min-width:56px; min-height:56px;"
        )
        overall_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        overall_lbl.setFixedSize(56, 56)
        hdr_text = QLabel(
            "<b>Network Grade Breakdown</b><br>"
            f"<span style='font-size:11px; color:{TEXT_SECONDARY};'>"
            "Hover each row for thresholds. The lowest score determines the overall grade.</span>"
        )
        hdr_text.setTextFormat(Qt.TextFormat.RichText)
        hdr_text.setWordWrap(True)
        hdr_text.setStyleSheet(f"background:transparent; border:none; color:{TEXT_PRIMARY};")
        hdr_row.addWidget(overall_lbl)
        hdr_row.addSpacing(12)
        hdr_row.addWidget(hdr_text, 1)
        lay.addLayout(hdr_row)

        _grade_rank = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4, "N/A": 5}
        worst_dim = max(dimensions, key=lambda d: _grade_rank.get(getattr(d, "grade", "N/A"), 5)) if dimensions else None
        _DIM_NAV = {
            "Connection Uptime":          "DNS & Stability",
            "Average Latency":            "DNS & Stability",
            "Jitter (Call Quality)":      "Bandwidth Usage",
            "DNS Response Speed":         "DNS & Stability",
            "Download Speed":             "Speed Test",
            "Device Safety":              "Security Overview",
            "STP Health":                 "Broadcast Storm",
            "Broadcast Storm Level":      "Broadcast Storm",
        }
        if worst_dim is not None:
            tip_name = getattr(worst_dim, "name", "")
            tip_nav  = _DIM_NAV.get(tip_name, "")
            tip_grade = getattr(worst_dim, "grade", "")
            if tip_grade not in ("A", "B", "N/A") and tip_name:
                tip_frame = QFrame()
                tip_frame.setObjectName("breakdownTip")
                tip_frame.setStyleSheet(
                    f"QFrame#breakdownTip {{ background:{BG_CARD}; border:1px solid {AMBER}44;"
                    f" border-left:3px solid {AMBER}; border-radius:4px; }}"
                )
                tip_lay = QHBoxLayout(tip_frame)
                tip_lay.setContentsMargins(10, 6, 10, 6)
                tip_lay.setSpacing(8)
                tip_lbl = QLabel(
                    f"<b>Biggest improvement:</b> {tip_name} is grade "
                    f"<b style='color:{_GRADE_COLOR.get(tip_grade, AMBER)}'>{tip_grade}</b>"
                )
                tip_lbl.setTextFormat(Qt.TextFormat.RichText)
                tip_lbl.setStyleSheet(
                    f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
                )
                tip_lay.addWidget(tip_lbl, 1)
                if tip_nav:
                    go_btn = QPushButton(f"Go to {tip_nav} →")
                    go_btn.setFlat(True)
                    go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    go_btn.setStyleSheet(
                        f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
                        f" border:none; padding:0; }}"
                        f"QPushButton:hover {{ color:{ACCENT}; text-decoration:underline; }}"
                        f"QPushButton:pressed {{ color:{ACCENT}; }}"
                    )
                    go_btn.clicked.connect(dlg.accept)
                    tip_lay.addWidget(go_btn)
                lay.addWidget(tip_frame)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(340)
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 0, 0)
        inner_lay.setSpacing(4)
        scroll.setWidget(inner)

        _THRESHOLDS = {
            "Connection Uptime":     ("A: ≥99%", "B: ≥97%", "C: ≥95%", "D: ≥90%", "F: <90%"),
            "Average Latency":       ("A: <20ms", "B: <40ms", "C: <80ms", "D: <150ms", "F: ≥150ms"),
            "Jitter (Call Quality)": ("A: <5ms", "B: <10ms", "C: <20ms", "D: <40ms", "F: ≥40ms"),
            "DNS Response Speed":    ("A: <30ms", "B: <60ms", "C: <120ms", "D: <200ms", "F: ≥200ms"),
            "Download Speed":        ("A: ≥100Mbps", "B: ≥25Mbps", "C: ≥10Mbps", "D: ≥2Mbps", "F: <2Mbps"),
            "Device Safety":         ("A: 0 high-risk", "B: 0 rogue", "C: 1 medium-risk", "D/F: 2+"),
            "STP Health":            ("A: no rogue bridge", "C: 1 bridge event", "F: active storm"),
            "Broadcast Storm Level": ("A: <1%", "B: <5%", "C: <15%", "D: <30%", "F: ≥30%"),
        }
        for dim in dimensions:
            name  = getattr(dim, "name",  "")
            dgrade = getattr(dim, "grade", "N/A")
            value = getattr(dim, "value", "")
            msg   = getattr(dim, "message", "")

            row = QFrame()
            row.setObjectName("breakdownRow")
            row.setStyleSheet(
                f"QFrame#breakdownRow {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:3px; }}"
            )
            _fg2 = _GRADE_COLOR.get(dgrade, TEXT_SECONDARY)
            _th  = " | ".join(_THRESHOLDS.get(name, ()))
            if _th:
                row.setToolTip(f"Thresholds: {_th}")

            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 5, 8, 5)
            rl.setSpacing(8)

            grade_badge = QLabel(dgrade)
            grade_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grade_badge.setFixedSize(28, 28)
            grade_badge.setStyleSheet(
                f"font-size:13px; font-weight:bold; color:{_fg2};"
                f" background:{BG_DARK}; border:2px solid {_fg2}; border-radius:14px;"
            )

            name_lbl = QLabel(name)
            name_lbl.setStyleSheet(
                f"font-size:11px; font-weight:500; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )

            right_col = QVBoxLayout()
            right_col.setSpacing(1)
            val_lbl = QLabel(str(value))
            val_lbl.setStyleSheet(
                f"font-size:10px; color:{_fg2}; background:transparent; border:none;"
            )
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            msg_lbl.setWordWrap(True)
            right_col.addWidget(val_lbl)
            right_col.addWidget(msg_lbl)

            rl.addWidget(grade_badge)
            rl.addWidget(name_lbl, 1)
            rl.addLayout(right_col, 2)
            inner_lay.addWidget(row)

        lay.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; font-size:11px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        close_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        return dlg


# ── StandardWelcomePage ───────────────────────────────────────────────────────

class StandardWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Standard mode.
    Displays a 2-column feature card grid: 'WHAT EACH SECTION GIVES YOU'.
    """

    _FEATURES = [
        ("⚡", "Speed test",      AMBER,        ["Download / upload speed",
                                                      "Ookla or fallback backends",
                                                      "Historical trend chart"]),
        ("◎", "DNS & Stability", ACCENT,        ["Live ping + DNS latency graph",
                                                      "Outage detection & log",
                                                      "STP reconvergence signature"]),
        ("⊕", "Devices",         TEXT_PRIMARY,  ["IP, MAC, vendor, model",
                                                      "Right-click How to Fix",
                                                      "Availability history per device"]),
        ("▲", "Live Bandwidth",  TEXT_PRIMARY,  ["Per-device rx/tx Mbps",
                                                      "60-second rolling area chart",
                                                      "Session totals table"]),
        ("◼", "Network Grade",   TEXT_PRIMARY,  ["A–F across 8 dimensions",
                                                      "Colour-coded verdict per metric",
                                                      "Actionable fix tip per grade"]),
        ("↗", "Network Health Report", TEXT_PRIMARY, ["Self-contained HTML export",
                                                           "MTR hop table + outage log",
                                                           "Great for ISP support tickets"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel("WHAT EACH SECTION GIVES YOU")
        hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        lay.addWidget(hdr)

        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, icon_colour, bullets) in enumerate(self._FEATURES):
            card = self._make_card(icon, title, icon_colour, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, icon_colour: str,
                   bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("stdCapabilityCard")
        card.setStyleSheet(
            f"QFrame#stdCapabilityCard {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{icon_colour}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(bullet)
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card


# ── ProWelcomePage ────────────────────────────────────────────────────────────

class ProWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Pro mode.
    Shows an admin-required warning and security audit capability cards.
    """

    _CAPABILITIES = [
        ("◎", "Port scanning",       ["• TCP connect + SYN (Scapy)",
                                           "• UDP scanner (DNS/SNMP/NTP)",
                                           "• Stealth / normal / fast modes"]),
        ("◎", "CVE tracker",         ["• NVD API v2 lookup per host",
                                           "• Lifecycle state machine",
                                           "• Days-open counter, owner field"]),
        ("◎", "Threat Intelligence", ["• Feodo Tracker + Emerging Threats",
                                           "• AbuseIPDB v2 lookup",
                                           "• Blocklist KPI tiles"]),
        ("◼", "TLS & exposure",      ["• Per-host cert expiry monitor",
                                           "• WAN / CGNAT / UPnP exposure",
                                           "• Cloud metadata probe"]),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        hdr = QLabel("SECURITY AUDIT CAPABILITIES")
        hdr.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; letter-spacing:1.5px; border:none;"
        )
        lay.addWidget(hdr)

        grid_w = QWidget()
        grid_w.setStyleSheet(f"background:{BG_DARK};")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        for i, (icon, title, bullets) in enumerate(self._CAPABILITIES):
            card = self._make_card(icon, title, bullets)
            grid.addWidget(card, i // 2, i % 2)

        lay.addWidget(grid_w)
        lay.addStretch()

    @staticmethod
    def _make_card(icon: str, title: str, bullets: list[str]) -> QFrame:
        card = QFrame()
        card.setObjectName("secCapabilityCard")
        card.setStyleSheet(
            f"QFrame#secCapabilityCard {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"font-size:14px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        icon_lbl.setFixedWidth(18)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        title_row.addWidget(icon_lbl)
        title_row.addWidget(title_lbl, 1)
        card_lay.addLayout(title_row)

        for bullet in bullets:
            b = QLabel(bullet)
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card



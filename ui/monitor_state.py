"""
monitor_state.py — _MonitorStateMixin and related helpers.

Extracted from ui/dashboard.py (Sprint 19).
Covers: verdict/badge/pill display, KPI tiles, pulse bar, section badges,
overall verdict, and the RiskBadge / VerdictPanel widget classes.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from modules.alert_types import SECURITY_RELEVANT_RULE_TYPES

from ui import styles as _s
from ui.styles import (
    RISK_BG,
    RISK_COLORS,
    STATUS_ICON_CRIT,
    STATUS_ICON_OK,
    STATUS_ICON_WARN,
)
from ui.widgets.device_detail_pane import _wire_close_icon

# ── Module-level colour helpers ───────────────────────────────────────────────

def _color_for_level(level: str) -> str:
    return RISK_COLORS.get(level.upper(), _s.TEXT_SECONDARY)


def _icon_for_level(level: str) -> str:
    """Return a shape icon for the risk level so colour is not the sole indicator."""
    lvl = level.upper()
    if lvl in ("CLEAN", "LOW"):
        return STATUS_ICON_OK
    if lvl in ("WARNING", "MEDIUM"):
        return STATUS_ICON_WARN
    if lvl in ("HIGH", "STORM"):
        return STATUS_ICON_CRIT
    return "○"


def _bg_for_level(level: str) -> str:
    return RISK_BG.get(level.upper(), _s.BG_CARD)


# ── Widget classes ────────────────────────────────────────────────────────────

class RiskBadge(QLabel):
    def __init__(self, level: str, parent=None):
        super().__init__(level.upper(), parent)
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"color:{color}; background:{bg}; border:1px solid {color};"
            "border-radius:3px; padding:1px 8px; font-weight:bold; font-size:10px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


_VERDICT_COLLAPSED_KEY = "ui/verdict_collapsed"


class VerdictPanel(QFrame):
    """Traffic-light coloured plain-English verdict box — collapsible via the ▼/▶ toggle."""

    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("verdictFrame")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row: title + toggle + dismiss ─────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet("background:transparent;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 6, 6, 4)
        hdr_lay.setSpacing(4)

        self._title = QLabel("Overall Verdict")
        self._title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        _btn_style = (
            "QPushButton {{ background:transparent; border:none;"
            " color:{TEXT_MUTED}; font-size:11px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ color:{TEXT_MUTED}; }}"
        )

        self._toggle_btn = QPushButton("▼")
        self._toggle_btn.setFixedSize(22, 22)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setToolTip("Collapse / expand verdict")
        _s.themed_ss(self._toggle_btn, _btn_style)
        self._toggle_btn.clicked.connect(self._on_toggle)

        self._close_btn = QPushButton()
        self._close_btn.setFixedSize(22, 22)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setToolTip("Dismiss — reappears after next scan")
        _wire_close_icon(self._close_btn, "TEXT_PRIMARY")
        _s.themed_ss(self._close_btn, "QPushButton {{ background:transparent; border:none; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:transparent; }}")
        self._close_btn.clicked.connect(self.close_requested)

        hdr_lay.addWidget(self._title, 1)
        hdr_lay.addWidget(self._toggle_btn)
        hdr_lay.addWidget(self._close_btn)
        outer.addWidget(hdr)

        # ── Body: multi-line verdict text ─────────────────────────────────────
        self._text = QLabel("Run a scan to see results.")
        self._text.setObjectName("verdictText")
        self._text.setWordWrap(True)
        self._text.setFont(QFont("Segoe UI", 11))
        self._text.setTextFormat(Qt.TextFormat.PlainText)
        outer.addWidget(self._text)

        self._set_level("UNKNOWN")

        # Default collapsed — only expand if user explicitly clicked the toggle before
        qs = QSettings("NetSentinel", "NetSentinel")
        if qs.value(_VERDICT_COLLAPSED_KEY, True, type=bool):
            self._text.setVisible(False)
            self._toggle_btn.setText("▶")

    def _on_toggle(self) -> None:
        collapsed = not self._text.isVisible()
        self._text.setVisible(collapsed)
        self._toggle_btn.setText("▼" if collapsed else "▶")
        QSettings("NetSentinel", "NetSentinel").setValue(
            _VERDICT_COLLAPSED_KEY, not collapsed
        )

    def _set_level(self, level: str):
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"QFrame#verdictFrame {{ background:{bg}; border-left:4px solid {color};"
            f"border-radius:0px; border-top:1px solid {_s.BORDER};"
            f"border-right:1px solid {_s.BORDER}; border-bottom:1px solid {_s.BORDER}; }}"
        )
        self._title.setStyleSheet(
            f"color:{color}; font-weight:bold; background:transparent;"
        )
        _s.themed_ss(self._text, "color:{TEXT_PRIMARY}; padding:2px 12px 8px 12px; font-size:11px;")

    def update(self, text: str, level: str = "UNKNOWN"):
        self._set_level(level)
        self._text.setText(text)
        # Respect the user's collapsed preference — never auto-expand


# ── Mixin ─────────────────────────────────────────────────────────────────────

class _MonitorStateMixin:
    """Methods that manage monitoring state indicators: badges, pills, verdict, KPI tiles."""

    # ── Alert badge ───────────────────────────────────────────────────────────

    def _refresh_alert_badge(self) -> None:
        if not hasattr(self, "_store") or self._store is None:
            return
        # Rail mode: dot + tooltip handled by _refresh_section_badges
        self._refresh_section_badges()

    # ── KPI bar (Devices page) ────────────────────────────────────────────────

    def _build_kpi_bar(self) -> QWidget:
        """
        Four KPI tiles: Total Nodes | Critical Risks | Unauthorized | Scan Status.
        Sits at the top of the Devices page. Values are updated by _update_kpi_tiles().
        """
        bar = QWidget()
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 6)
        row.setSpacing(8)

        def _tile(dot_cname: str, label: str, start_val: str, start_cname: str):
            """Return (tile QFrame, dot QLabel, value QLabel).

            dot_cname/start_cname are ui/styles.py token NAMES, not resolved values.
            """
            tile = QFrame()
            tile.setObjectName("card")
            _s.themed_ss(tile, lambda c=dot_cname: (
                f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
                f"border-left:3px solid {getattr(_s, c)};border-radius:0px;}}"
            ))
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)

            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            _s.themed_ss(dot, lambda c=dot_cname: (
                f"color:{getattr(_s, c)}; font-size:9px; background:transparent; border:none;"
            ))
            lbl_w = QLabel(label)
            _s.themed_ss(lbl_w, "color:{TEXT_SECONDARY}; font-size:9px; background:transparent; border:none;")
            hdr.addWidget(dot)
            hdr.addWidget(lbl_w)
            hdr.addStretch()
            val = QLabel(start_val)
            _s.themed_ss(val, lambda c=start_cname: (
                f"color:{getattr(_s, c)}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            ))
            vl.addLayout(hdr)
            vl.addWidget(val)
            return tile, dot, val

        t1, _d1, v1 = _tile("ACCENT", "TOTAL NODES",    "—", "ACCENT")
        t2, d2,  v2 = _tile("GREEN",  "CRITICAL RISKS",  "—", "GREEN")
        t3, d3,  v3 = _tile("GREEN",  "UNAUTHORIZED",    "—", "GREEN")
        t4, d4,  v4 = _tile("ACCENT", "SCAN STATUS",     "Idle", "ACCENT")

        self._kpi_nodes_val  = v1
        self._kpi_risk_val   = v2;  self._kpi_risk_dot   = d2;  self._kpi_risk_tile   = t2
        self._kpi_unauth_val = v3;  self._kpi_unauth_dot = d3;  self._kpi_unauth_tile = t3
        self._kpi_scan_val   = v4;  self._kpi_scan_dot   = d4

        for t in (t1, t2, t3, t4):
            row.addWidget(t)
        return bar

    def _update_kpi_tiles(self, data: dict) -> None:
        """Refresh KPI tile values from a completed scan result dict."""
        devices    = data.get("devices", [])
        total      = len(devices)
        high_risk  = sum(
            1 for d in devices
            if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) in ("HIGH", "CRITICAL")
        )
        unauth     = data.get("high_risk_count", high_risk)

        # Nodes tile — always blue
        self._kpi_nodes_val.setText(str(total))
        _s.themed_ss(self._kpi_nodes_val, "color:{ACCENT}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;")

        # Critical risks tile — green if 0, amber if 1-2, red if 3+
        risk_color = _s.GREEN if high_risk == 0 else (_s.AMBER if high_risk <= 2 else _s.RED)
        self._kpi_risk_val.setText(str(high_risk))
        self._kpi_risk_val.setStyleSheet(
            f"color:{risk_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_risk_dot.setStyleSheet(
            f"color:{risk_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_risk_tile.setStyleSheet(
            f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
            f"border-left:3px solid {risk_color};border-radius:0px;}}"
        )

        # Unauthorized tile — green if 0, red if >0
        unauth_color = _s.GREEN if unauth == 0 else _s.RED
        self._kpi_unauth_val.setText(str(unauth))
        self._kpi_unauth_val.setStyleSheet(
            f"color:{unauth_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_unauth_dot.setStyleSheet(
            f"color:{unauth_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_unauth_tile.setStyleSheet(
            f"QFrame#card{{background:{_s.BG_CARD};border:1px solid {_s.BORDER};"
            f"border-left:3px solid {unauth_color};border-radius:0px;}}"
        )

        # Scan status tile — green "Complete"
        self._kpi_scan_val.setText("Complete")
        _s.themed_ss(self._kpi_scan_dot, "color:{GREEN}; font-size:9px; background:transparent; border:none;")
        _s.themed_ss(self._kpi_scan_val, "color:{GREEN}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;")

    # ── Verdict area ──────────────────────────────────────────────────────────

    def _build_verdict_area(self) -> QWidget:
        """Compact verdict strip at bottom — thin, doesn't waste screen space."""
        w = QWidget()
        _s.themed_ss(w, "background:{BG_CARD}; border-top:1px solid {BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(0)

        self._verdict = VerdictPanel()
        self._verdict.close_requested.connect(w.hide)
        lay.addWidget(self._verdict, 1)
        return w

    # ── KPI-card helpers ──────────────────────────────────────────────────────

    def _stat_label(self, title: str, value: str) -> QFrame:
        """KPI card: coloured left border, label above, large number below."""
        frame = QFrame()
        _s.themed_ss(frame, "background:{BG_CARD}; border:1px solid {BORDER};"
            "border-left:3px solid {ACCENT}; border-radius:3px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 6, 10, 6)
        fl.setSpacing(1)
        t = QLabel(title.upper())
        _s.themed_ss(t, "color:{TEXT_SECONDARY}; font-size:9px; font-weight:bold; letter-spacing:0.5px;")
        v = QLabel(value)
        _s.themed_ss(v, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;")
        v.setObjectName(f"stat_{title.replace('/','_').replace(' ','_')}")
        fl.addWidget(t)
        fl.addWidget(v)
        return frame

    def _find_stat_value(self, frame: QFrame):
        for child in frame.findChildren(QLabel):
            if child.objectName().startswith("stat_"):
                return child
        return None

    def _update_stat(self, frame: QFrame, value: str, color: str = None):
        if color is None:
            color = _s.TEXT_PRIMARY
        lbl = self._find_stat_value(frame)
        if lbl:
            lbl.setText(value)
            lbl.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")

    # ── Status bar ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_bar.showMessage(f"  {msg}")

    # ── Pulse bar ─────────────────────────────────────────────────────────────

    def _refresh_pulse_bar(self) -> None:
        """Update the four permanent status-bar indicators (called every 10 s)."""
        import time as _t

        _muted  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {_s.TEXT_MUTED}; }} QLabel:hover {{ color: {_s.WHITE}; }}"
        _green  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {_s.GREEN}; }} QLabel:hover {{ color: {_s.WHITE}; }}"
        _amber  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {_s.AMBER}; }} QLabel:hover {{ color: {_s.WHITE}; }}"
        _red    = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {_s.RED}; }} QLabel:hover {{ color: {_s.WHITE}; }}"

        # Online / Offline
        status = self._last_log_status
        if status == "OK":
            self._pulse_online_lbl.setText(f"{STATUS_ICON_OK}  Online")
            self._pulse_online_lbl.setStyleSheet(_green)
        elif status == "SLOW":
            self._pulse_online_lbl.setText(f"{STATUS_ICON_WARN}  Slow")
            self._pulse_online_lbl.setStyleSheet(_amber)
        elif status == "FAIL":
            self._pulse_online_lbl.setText(f"{STATUS_ICON_CRIT}  Offline")
            self._pulse_online_lbl.setStyleSheet(_red)
        else:
            self._pulse_online_lbl.setText("○  —")
            self._pulse_online_lbl.setStyleSheet(_muted)

        # Device count
        n = len(self._last_scan_devices)
        if n > 0:
            self._pulse_devices_lbl.setText(f"■  {n} device{'s' if n != 1 else ''}")
        else:
            self._pulse_devices_lbl.setText("■  —")
        self._pulse_devices_lbl.setStyleSheet(_muted)

        # Last scan age
        if self._last_scan_time > 0:
            elapsed = _t.time() - self._last_scan_time
            if elapsed < 60:
                age = "just now"
            elif elapsed < 3600:
                age = f"{int(elapsed // 60)}m ago"
            else:
                age = f"{int(elapsed // 3600)}h ago"
            self._pulse_scan_lbl.setText(f"Last scan: {age}")
        else:
            self._pulse_scan_lbl.setText("Last scan: —")
        self._pulse_scan_lbl.setStyleSheet(_muted)

        # Logger status
        logging_on = bool(hasattr(self, '_logger_worker') and self._logger_worker and self._logger_worker.isRunning())
        if logging_on:
            self._pulse_logger_lbl.setText("⏺  Logging")
            self._pulse_logger_lbl.setStyleSheet(_green)
        else:
            self._pulse_logger_lbl.setText("○  Logger off")
            self._pulse_logger_lbl.setStyleSheet(_muted)

    # ── Section badges ────────────────────────────────────────────────────────

    def _update_monitor_badge(self, _active: bool = False) -> None:
        """Refresh all section badges and Home pills when log source state changes."""
        self._push_monitor_pills()

    def _refresh_section_badges(self, *, arp: bool = None, dhcp: bool = None,
                                storm: bool = None, logger: bool = None) -> None:
        """Update rail section button dots for Monitor, Analysis, and Security Audit."""
        if not hasattr(self, "_nav_rail_buttons"):
            return
        if arp is None:
            arp = bool(hasattr(self, '_arp_worker') and self._arp_worker and self._arp_worker.isRunning())
        if dhcp is None:
            dhcp = bool(hasattr(self, '_dhcp_worker') and self._dhcp_worker and self._dhcp_worker.isRunning())
        if storm is None:
            storm = self._m3_monitoring_active()
        if logger is None:
            qs = QSettings("NetSentinel", "NetSentinel")
            logger = any(
                qs.value(k, False, type=bool)
                for k in qs.allKeys()
                if k.startswith("logging/") and k.endswith("_enabled")
            )
        # Monitor — left dot: green when any log source is active, muted when idle
        mon_btn = self._nav_rail_buttons.get("Monitor")
        if mon_btn:
            mon_btn.set_badge("")   # top-right badge not used for Monitor
            mon_btn.set_left_dot(_s.GREEN if logger else _s.TEXT_MUTED)
        # Analysis — left dot: green when ARP watch or broadcast storm is running
        ana_btn = self._nav_rail_buttons.get("Analysis")
        if ana_btn:
            ana_btn.set_badge("")   # top-right badge not used for Analysis
            ana_btn.set_left_dot(_s.GREEN if (arp or storm) else _s.TEXT_MUTED)
        # Security Audit — numeric red pill when unacked alerts exist, green dot when DHCP running
        sec_btn = self._nav_rail_buttons.get("Security Audit")
        if sec_btn:
            try:
                alert_count = (
                    len(self._store.get_unacked_alerts(rule_types=SECURITY_RELEVANT_RULE_TYPES))
                    if self._store else 0
                )
            except Exception:
                alert_count = 0
            if alert_count > 0:
                sec_btn.set_badge(alert_count)   # numeric red pill
                sec_btn.setToolTip(f"Security Audit — {alert_count} unacknowledged alert(s)")
            elif dhcp:
                sec_btn.set_badge(_s.GREEN)
                sec_btn.setToolTip("Security Audit")
            else:
                sec_btn.set_badge(0)
                sec_btn.setToolTip("Security Audit")

        # POLISH-2: CVE Tracker — count of Open-state CVEs
        cve_btn = self._nav_rail_buttons.get("CVE Tracker")
        if cve_btn and self._store:
            try:
                open_cves = len(self._store.list_cve_lifecycles(state_filter="Open"))
            except Exception:
                open_cves = 0
            cve_btn.set_badge(open_cves if open_cves > 0 else 0)
            if open_cves:
                cve_btn.setToolTip(f"CVE Tracker — {open_cves} open CVE{'s' if open_cves != 1 else ''}")

        # POLISH-2: TLS & Exposure — count of expiring / expired certs
        tls_btn = self._nav_rail_buttons.get("TLS & Exposure")
        if tls_btn and self._store:
            try:
                certs = self._store.query_cert_status(hours=168)
                expired  = sum(1 for c in certs if getattr(c, "is_expired", False))
                expiring = sum(
                    1 for c in certs
                    if not getattr(c, "is_expired", False)
                    and 0 <= (getattr(c, "days_remaining", 999) or 999) <= 30
                )
            except Exception:
                expired = expiring = 0
            cert_total = expired + expiring
            if cert_total > 0:
                tls_btn.set_badge(_s.RED if expired > 0 else _s.AMBER)
                tls_btn.setToolTip(
                    f"TLS & Exposure — {expired} expired, {expiring} expiring soon"
                    if expired else f"TLS & Exposure — {expiring} cert{'s' if expiring != 1 else ''} expiring soon"
                )
            else:
                tls_btn.set_badge(0)

        # POLISH-2: Config Snapshots — drift indicator "≠" when auto-snapshot drifted
        base_btn = self._nav_rail_buttons.get("Config Snapshots")
        if base_btn:
            if getattr(self, "_baseline_has_drift", False):
                base_btn.set_badge(_s.AMBER)
                base_btn.setToolTip("Config Snapshots — baseline drift detected")
            else:
                base_btn.set_badge(0)

    # ── Flyout dots ───────────────────────────────────────────────────────────

    def _set_flyout_dot(self, label: str, color: str) -> None:
        """Set or clear a status dot on a flyout item by label."""
        if not hasattr(self, "_flyout_dots"):
            self._flyout_dots: dict[str, str] = {}
        self._flyout_dots[label] = color
        if hasattr(self, "_nav_flyout"):
            self._nav_flyout.apply_dot(label, color)

    # ── Monitor pills ─────────────────────────────────────────────────────────

    def _push_monitor_pills(self) -> None:
        """Push current monitoring states to Home pills, flyout dots, and section badges."""
        arp    = bool(hasattr(self, '_arp_worker')  and self._arp_worker  and self._arp_worker.isRunning())
        dhcp   = bool(hasattr(self, '_dhcp_worker') and self._dhcp_worker and self._dhcp_worker.isRunning())
        storm  = self._m3_monitoring_active()
        qs     = QSettings("NetSentinel", "NetSentinel")
        logger = any(
            qs.value(k, False, type=bool)
            for k in qs.allKeys()
            if k.startswith("logging/") and k.endswith("_enabled")
        )
        if hasattr(self, "_home_page"):
            self._home_page.set_monitor_pills(arp, dhcp, storm, logger)
            if self._store is not None:
                try:
                    unacked = self._store.get_unacked_alerts()
                    offline = sum(
                        1 for d in self._store.get_known_devices().values()
                        if getattr(d, "last_seen", 0) and
                        (__import__("time").time() - d.last_seen) > 1800
                    )
                    self._home_page.set_action_needed(len(unacked), offline)
                    self._home_page.set_pending_alert_rows(unacked)
                except Exception:
                    pass  # non-fatal
        # Flyout item dots — always reflect current state.
        # Network Logger is NOT set here (F-57): its dot is exclusively owned by
        # the scan registry (_nav_set_scan_state(L.NETWORK_LOGGER, ...), called
        # from ui/tabs_logger.py on real start/stop) so it can show
        # running/fresh/stale/error, not just this binary checkbox-derived on/off.
        self._set_flyout_dot("ARP Spoof Watch",    _s.GREEN if arp    else "")
        self._set_flyout_dot("DHCP Rogue Monitor", _s.GREEN if dhcp   else "")
        self._set_flyout_dot("Broadcast Storm",    _s.GREEN if storm  else "")
        # AUTO-1/2: Automation dot and tile — green if any rule fired in last 24h
        try:
            from modules.automation_hooks import get_engine as _get_ae
            _ae = _get_ae()
            _auto_ts = _ae.get_last_triggered()
            _auto_rules = _ae.get_rules()
            import time as _t
            _auto_active = _auto_ts > 0 and (_t.time() - _auto_ts) < 86400
            self._set_flyout_dot("Automation Hooks", _s.GREEN if _auto_active else "")
            if hasattr(self, "_monitor_overview_page"):
                self._monitor_overview_page.set_automation_status(
                    len(_auto_rules), _auto_ts
                )
        except Exception:
            pass  # non-fatal
        # HEALTH-1/4: push health + config completeness to Settings page
        if hasattr(self, "_settings_page"):
            try:
                bw_running = bool(
                    getattr(self, "_bandwidth_worker", None)
                    and self._bandwidth_worker.isRunning()
                )
                scan_sched_running = bool(
                    getattr(self, "_sched_worker", None)
                    and self._sched_worker.isRunning()
                )
                report_sched_running = bool(
                    getattr(self, "_report_scheduler_worker", None)
                    and self._report_scheduler_worker.isRunning()
                )
                db_ok = self._store is not None
                self._settings_page.refresh_health_status({
                    "Scheduler":           ("Running" if scan_sched_running else "Stopped", scan_sched_running),
                    "ARP Monitor":         ("Running" if arp           else "Stopped", arp),
                    "Bandwidth Monitor":   ("Running" if bw_running     else "Stopped", bw_running),
                    "Report Scheduler":    ("Running" if report_sched_running else "Stopped", report_sched_running),
                    "Database":            ("OK"      if db_ok          else "Error",   db_ok),
                    "Logger":              ("Active"  if logger          else "Inactive", logger),
                })
                cve_count = 0
                rule_count = 0
                try:
                    from modules.automation_hooks import get_engine as _gae
                    rule_count = len(_gae().get_rules())
                except Exception:
                    pass  # non-fatal
                try:
                    if self._store:
                        cve_count = len(self._store.list_cve_lifecycles() or [])
                except Exception:
                    pass  # non-fatal
                self._settings_page.refresh_config_completeness(cve_count, rule_count)
            except Exception:
                pass  # non-fatal
        # Section button badges
        self._refresh_section_badges(arp=arp, dhcp=dhcp, storm=storm, logger=logger)
        # Push to Active Monitors page
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_arp_status(arp, alerted=False)
            self._monitor_overview_page.set_dhcp_status(dhcp)
            if self._store is not None:
                try:
                    self._monitor_overview_page.set_monitor_event_times(
                        arp=self._store.get_last_event_time("ARP"),
                        dhcp=self._store.get_last_event_time("DHCP"),
                        storm=self._store.get_last_event_time("Storm"),
                        iot=self._store.get_last_event_time("IoT"),
                        ports=self._store.get_last_event_time("Port"),
                        cve=self._store.get_last_event_time("CVE"),
                    )
                except Exception:
                    pass  # non-fatal

    def _m3_monitoring_active(self) -> bool:
        """Return True if any scan worker (including storm) is currently running."""
        return any(
            w.isRunning()
            for w in getattr(self, "_workers", [])
            if hasattr(w, "isRunning")
        )

    def _refresh_hardware_badge(self) -> None:
        """Update the Extend section rail button tooltip to show active plugin count."""
        n = len(getattr(self, "_plugin_pages", {}))
        if n == 0:
            return
        btn = self._nav_rail_buttons.get("Extend")
        if btn:
            btn.setToolTip(f"Extend — {n} plugin{'s' if n != 1 else ''} active")

    # ── Overall verdict ───────────────────────────────────────────────────────

    def _update_overall_verdict(self):
        verdicts = []
        level = "CLEAN"

        if self._m1_result:
            v = self._m1_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m1_result.get("high_risk_count", 0) > 0:
                level = "HIGH"

        if self._m2_result:
            v = self._m2_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m2_result.get("rogue_count", 0) > 0:
                level = "HIGH"

        if self._m3_result:
            storm_level = (
                self._m3_result.storm_level
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("storm_level", "CLEAN")
            )
            v = (
                self._m3_result.plain_verdict
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            if storm_level in ("STORM", "WARNING") and level == "CLEAN":
                level = "MEDIUM" if storm_level == "WARNING" else "HIGH"

        if self._m4_result:
            v = (
                self._m4_result.plain_verdict
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            rogue_c = (
                self._m4_result.rogue_count
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("rogue_count", 0)
            )
            if rogue_c and level == "CLEAN":
                level = "MEDIUM"

        if self._m5_result:
            v = (
                self._m5_result.plain_verdict
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            stp_sigs = (
                self._m5_result.stp_signatures
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("stp_signatures", [])
            )
            if stp_sigs:
                level = "HIGH"

        if self._diag_result:
            v = getattr(self._diag_result, "plain_verdict", "") or ""
            if v:
                verdicts.append(f"Diagnostics: {v}")
            # Failed ping to gateway → escalate
            gw_ping = next(
                (p for p in getattr(self._diag_result, "ping_results", []) if p.host == "Gateway"),
                None,
            )
            if gw_ping and gw_ping.status == "FAIL" and level == "CLEAN":
                level = "HIGH"
            # DNS leak
            leak = getattr(self._diag_result, "dns_leak", None)
            if leak and getattr(leak, "leak_detected", False) and level == "CLEAN":
                level = "MEDIUM"

        combined = "\n\n".join(verdicts) if verdicts else "Scan in progress..."
        self._verdict.update(combined, level)
        # Show the compact status badge once real data is available
        from ui.tabs_helpers import risk_to_label as _r2l
        self._verdict_badge.setText(f"{_icon_for_level(level)} {_r2l(level)}")
        self._verdict_badge.setStyleSheet(
            f"color:{_color_for_level(level)}; font-size:11px; font-weight:bold; padding:0 8px;"
            "background:transparent; border:none;"
        )
        self._verdict_badge.setVisible(True)

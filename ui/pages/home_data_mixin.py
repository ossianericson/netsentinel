"""
home_data_mixin.py — _HomeDataMixin: data handlers and public slots for HomePage.

Extracted from ui/pages/home_page.py (Sprint 15). Contains all update/handler methods
that operate on widgets built by _setup_ui, keeping home_page.py focused on layout.
"""
from __future__ import annotations

import datetime
import json

from PyQt6.QtCore import Qt, QSettings, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget,
)

from ui.styles import (
    alpha,
    ACCENT, ACCENT_DARK, AMBER, BG_CARD, BG_HOVER, BORDER,
    CARD_RADIUS, GREEN, PRO_WARN_BG, RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, UPDATE_BAR_BORDER, UPDATE_BAR_FG, WHITE,
)
from ui.widgets.home_widgets import (
    _load_grade_history, _GRADE_HISTORY_KEY, _AlertRow,
)
from ui.widgets.home_session_widgets import _GradeBreakdownDialog

try:
    from ui.pages.discover_page import _FEATURES as _GUIDE_FEATURES
except ImportError:
    _GUIDE_FEATURES: list = []


class _HomeDataMixin:
    """Mixin providing data handlers and public slots for HomePage.

    Extracted from ui/pages/home_page.py (Sprint 15).
    Requires all widgets to be pre-built by _setup_ui in the host class.
    """

    # ── Feature search ────────────────────────────────────────────────────────

    def _apply_home_search(self, text: str) -> None:
        while self._search_results_inner.count():
            item = self._search_results_inner.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        q = text.strip().lower()
        if not q:
            self._search_results.setVisible(False)
            return

        filtered = [
            f for f in _GUIDE_FEATURES
            if q in f["name"].lower()
            or q in f["desc"].lower()
            or q in f.get("group", "").lower()
            or q in (f.get("page") or "").lower()
            or any(q in t.lower() for t in f.get("tags", []))
        ][:6]

        if not filtered:
            lbl = QLabel(f'No features matching "{text}"')
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            self._search_results_inner.addWidget(lbl)
        else:
            for feat in filtered:
                self._search_results_inner.addWidget(
                    self._make_search_result_row(feat)
                )
        self._search_results.setVisible(True)

    def _make_search_result_row(self, feat: dict) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(2, 3, 2, 3)
        rl.setSpacing(8)

        name_lbl = QLabel(feat["name"])
        name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none; min-width:130px;"
        )
        desc_lbl = QLabel(feat["desc"])
        desc_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        desc_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        btn = QPushButton("Open →")
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px;"
            f" background:transparent; border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        target = feat.get("page") or "Feature Guide"
        btn.clicked.connect(lambda _=False, t=target: self.navigate_to.emit(t))

        rl.addWidget(name_lbl)
        rl.addWidget(desc_lbl, 1)
        rl.addWidget(btn)
        return row

    # ── Discoverability / show event ──────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        qs = QSettings("NetSentinel", "NetSentinel")
        api_enabled = qs.value("rest_api/enabled", False, type=bool)
        strip_dismissed = qs.value("home/dashboard_strip_dismissed", False, type=bool)
        if api_enabled and not strip_dismissed:
            port = int(qs.value("rest_api/port", 8765))
            self._dashboard_url = f"http://localhost:{port}/dashboard"
            self._ds_text.setText(
                f"REST API running at localhost:{port} — browser dashboard + 7 endpoints "
                f"(devices, alerts, uptime, grade…). Open Settings to see the full list."
            )
            self._dashboard_strip.setVisible(True)
        else:
            self._dashboard_strip.setVisible(False)
        self.refresh_checklist()
        self.refresh_diag_summary()
        if hasattr(self, "_weekly_report_card"):
            self._weekly_report_card.refresh()
        self._check_recurring_mode()
        if self._recurring_mode:
            self._update_recurring_scan_time()
            self._update_this_week()
            self._refresh_sparkline()

    def _open_dashboard(self) -> None:
        QDesktopServices.openUrl(QUrl(self._dashboard_url))

    def _dismiss_dashboard_strip(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(
            "home/dashboard_strip_dismissed", True
        )
        self._dashboard_strip.setVisible(False)
        self.window().activateWindow()

    def _dismiss_recurring_intro(self) -> None:
        """Dismiss the one-time recurring mode intro card."""
        QSettings("NetSentinel", "NetSentinel").setValue(
            "home/recurring_mode_intro_shown", True
        )
        if hasattr(self, "_recurring_intro_card"):
            self._recurring_intro_card.setVisible(False)
        self.window().activateWindow()

    def _on_setup_complete(self) -> None:
        """Called when all Getting Started steps are complete (via completion_done signal)."""
        if hasattr(self, "_setup_card_top"):
            self._setup_card_top.setVisible(False)
        if hasattr(self, "_setup_complete_card"):
            self._setup_complete_card.setVisible(True)
        QSettings("NetSentinel", "NetSentinel").setValue("setup/all_done", True)

    @pyqtSlot()
    def refresh_hw_strip(self) -> None:
        """Compatibility shim -- delegates to refresh_checklist."""
        self.refresh_checklist()

    def refresh_checklist(self) -> None:
        """Delegate to the GettingStartedCard widget."""
        if hasattr(self, "_setup_card_top"):
            self._setup_card_top.refresh_checklist(self._device_count)

    def _dismiss_post_scan_sheet(self) -> None:
        self._post_scan_sheet.setVisible(False)
        # No permanent QSettings persistence — sheet re-shows on next scan
        all_off = not any(p.text().startswith("●") for p in (
            self._pill_arp, self._pill_dhcp, self._pill_storm, self._pill_logger
        ))
        self._monitoring_nudge.setVisible(all_off)
        if hasattr(self, "_btn_start_logger"):
            self._btn_start_logger.setVisible(all_off)

    def _maybe_show_post_scan_sheet(
        self, n_total: int, n_new: int, n_at_risk: int
    ) -> None:
        n_recognized = n_total - n_new
        parts = [f"{n_total} device{'s' if n_total != 1 else ''} found"]
        if n_new:
            parts.append(f"{n_new} new")
        if n_recognized and n_new:
            parts.append(f"{n_recognized} recognized")
        self._sheet_stats_lbl.setText("  ·  ".join(parts))
        if self._current_grade:
            self._sheet_grade_btn.setText(
                f"Network Grade: {self._current_grade}  →"
            )
        else:
            self._sheet_grade_btn.setText("Run a Network Grade →")
        if n_at_risk > 0:
            self._sheet_action_btn.setText("Check unknown devices →")
            self._sheet_action_target = "Devices"
        else:
            self._sheet_action_btn.setText("Set up notifications →")
            self._sheet_action_target = "Notifications"
        self._post_scan_sheet.setVisible(True)

    # ── First-run / recurring-user layout ────────────────────────────────────

    def _set_first_run_mode(self, on: bool) -> None:
        """Show/hide secondary sections based on whether any devices have been scanned."""
        self._first_run_mode = on
        for w in (
            self._sec1_lbl, self._mini_cards_widget,
            self._monitoring_pills_row, self._monitoring_nudge,
            self._sec_mon_lbl, self._mon_card,
            self._alerts_hdr_row, self._alert_card,
        ):
            w.setVisible(not on)
        if hasattr(self, "_monitoring_pills_hint"):
            self._monitoring_pills_hint.setVisible(not on)
        if hasattr(self, "_tip_card"):
            self._tip_card.setVisible(
                not on and not getattr(self, "_tip_card_dismissed", True)
            )
        if on:
            self._hero_title.setText("Discover your network")
            self._hero_sub.setText(
                "See every device, check your security score, and start monitoring"
                " — takes about 30 seconds."
                "   ·   Try Ctrl+K to find any feature instantly."
            )
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)

    def _check_recurring_mode(self) -> None:
        """Activate recurring layout if setup is complete and ≥5 scans recorded."""
        if self._first_run_mode or self._recurring_mode:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        scan_count = int(qs.value("home/scan_count", 0))
        if scan_count >= 5 and all(self._setup_card_top._checklist_states(self._device_count).values()):
            self._apply_recurring_layout(True)

    def _apply_recurring_layout(self, on: bool) -> None:
        """Toggle between new-user and recurring-user Home layout."""
        if self._recurring_mode == on:
            return
        self._recurring_mode = on
        self._recurring_section.setVisible(on)
        self._this_week_card.setVisible(on)
        self._btn_scan.setVisible(not on)
        self._btn_rescan_compact.setVisible(on)
        self._monitoring_pills_row.setVisible(not on)
        self._monitoring_nudge.setVisible(False)
        if hasattr(self, "_monitoring_pills_hint"):
            self._monitoring_pills_hint.setVisible(not on)
        if hasattr(self, "_tip_card"):
            self._tip_card.setVisible(
                not on and not getattr(self, "_tip_card_dismissed", True)
            )
        self._btn_view_all_alerts.setVisible(on)
        if on:
            self._update_recurring_grade_display()
            self._update_recurring_scan_time()
            self._update_this_week()
            qs = QSettings("NetSentinel", "NetSentinel")
            if not qs.value("home/recurring_mode_intro_shown", False, type=bool):
                if hasattr(self, "_recurring_intro_card"):
                    self._recurring_intro_card.setVisible(True)

    def _update_recurring_grade_display(self) -> None:
        if not hasattr(self, "_rec_grade_lbl"):
            return
        if self._current_grade:
            from ui.styles import GREEN as _G, AMBER as _A, RED as _R
            color = _G if self._current_grade in ("A", "B") else (
                _A if self._current_grade == "C" else _R
            )
            self._rec_grade_lbl.setText(f"Network Grade: {self._current_grade}")
            self._rec_grade_lbl.setStyleSheet(
                f"font-size:11px; font-weight:600; color:{color};"
                " background:transparent; border:none;"
            )
        else:
            self._rec_grade_lbl.setText("Network Grade: —")

    def _update_recurring_scan_time(self) -> None:
        if not hasattr(self, "_rec_scan_time_lbl"):
            return
        if self._last_scan_ts is None:
            self._rec_scan_time_lbl.setText("Last scan: —")
            return
        delta = datetime.datetime.now() - self._last_scan_ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            self._rec_scan_time_lbl.setText("Last scan: just now")
        elif mins < 60:
            self._rec_scan_time_lbl.setText(f"Last scan: {mins}m ago")
        else:
            self._rec_scan_time_lbl.setText(f"Last scan: {mins // 60}h ago")

    def _refresh_sparkline(self) -> None:
        if hasattr(self, "_grade_sparkline"):
            self._grade_sparkline.set_points(_load_grade_history())

    def _update_this_week(self) -> None:
        if not self._store:
            return
        try:
            alerts = self._store.get_recent_alerts(hours=168, limit=500)
            self._tw_alerts_val.setText(str(len(alerts)))

            events = self._store.query_device_events(hours=168, event_types=["JOINED"])
            self._tw_devices_val.setText(str(len(events)))

            cves = self._store.list_cve_lifecycles() or []
            self._tw_cve_val.setText(str(len(cves)))
            self._tw_cve_val.setStyleSheet(
                f"font-size:16px; font-weight:bold;"
                f" color:{RED if cves else TEXT_MUTED};"
                " background:transparent; border:none;"
            )

            grade_now = self._current_grade or "—"
            self._tw_grade_val.setText(grade_now)
        except Exception:
            pass  # non-fatal

    def _update_scan_button_label(self) -> None:
        label = "▶  Scan Network" if self._device_count == 0 else "▶  Rescan"
        self._btn_scan.setText(label)

    # ── Monitoring pill status ────────────────────────────────────────────────

    def set_monitor_pills(
        self, arp: bool, dhcp: bool, storm: bool, logger: bool
    ) -> None:
        """Update monitoring pill badges. Called by dashboard on worker state changes."""
        # Track logger start time for rich tooltip
        if logger and not getattr(self, "_logger_active_since", None):
            self._logger_active_since: "datetime.datetime | None" = datetime.datetime.now()
        elif not logger:
            self._logger_active_since = None

        _pill_map = [
            (self._pill_arp,    arp,    "ARP Watch"),
            (self._pill_dhcp,   dhcp,   "DHCP Watch"),
            (self._pill_storm,  storm,  "Broadcast Storm"),
            (self._pill_logger, logger, "Network Logger"),
        ]
        for btn, active, label in _pill_map:
            if active:
                btn.setText(f"●  {label}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:{alpha(GREEN, 0x22)}; color:{GREEN}; font-size:10px;"
                    f" font-weight:bold; border:1px solid {GREEN}; border-radius:11px;"
                    f" padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{alpha(GREEN, 0x44)}; }}"
                    f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
                )
            else:
                btn.setText(f"○  {label}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:10px;"
                    f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{BG_HOVER}; }}"
                    f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
                )
        all_off = not any([arp, dhcp, storm, logger])
        self._monitoring_nudge.setVisible(all_off)
        if hasattr(self, "_btn_start_logger"):
            self._btn_start_logger.setVisible(all_off)
        self._freshness_strip.update_freshness(arp=arp, dhcp=dhcp, storm=storm, logger=logger)
        # Enrich logger pill tooltip with "since X ago"
        if logger and getattr(self, "_logger_active_since", None):
            _since = self._logger_active_since
            _delta = datetime.datetime.now() - _since
            _secs = int(_delta.total_seconds())
            if _secs < 60:
                _since_str = "just now"
            elif _secs < 3600:
                _since_str = f"{_secs // 60} min ago"
            else:
                _h = _secs // 3600
                _m = (_secs % 3600) // 60
                _since_str = f"{_h}h {_m}m ago" if _m else f"{_h}h ago"
            self._freshness_strip.update_logger_tooltip(since_str=_since_str)

        _rec_map = [
            (self._rec_pill_arp,    arp,    "ARP Watch"),
            (self._rec_pill_dhcp,   dhcp,   "DHCP Watch"),
            (self._rec_pill_storm,  storm,  "Broadcast Storm"),
            (self._rec_pill_logger, logger, "Network Logger"),
        ]
        for rbtn, active, rlabel in _rec_map:
            if active:
                rbtn.setText(f"●  {rlabel}")
                rbtn.setStyleSheet(
                    f"QPushButton {{ background:{alpha(GREEN, 0x22)}; color:{GREEN}; font-size:10px;"
                    f" font-weight:bold; border:1px solid {GREEN}; border-radius:11px;"
                    f" padding:1px 10px; }}"
                    f"QPushButton:hover {{ background:{alpha(GREEN, 0x44)}; }}"
                    f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
                )
            else:
                rbtn.setText(f"○  {rlabel}")
                rbtn.setStyleSheet(
                    f"QPushButton {{ background:{BG_HOVER}; color:{TEXT_MUTED}; font-size:10px;"
                    f" border:1px solid {BORDER}; border-radius:11px; padding:1px 10px; }}"
                    f"QPushButton:hover {{ border-color:{ACCENT}; }}"
                    f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
                )

    # ── Action-needed card ────────────────────────────────────────────────────

    def set_action_needed(self, pending_alerts: int, offline_devices: int) -> None:
        """Hide the action card when alerts clear (offline devices are not actionable)."""
        if pending_alerts == 0 and self._ac_alert_rows_lay.count() == 0:
            self._action_card.setVisible(False)

    def set_pending_alert_rows(self, alerts: list) -> None:
        """ALERT-3: Populate the action-needed card with per-alert rows + inline ack."""
        import time as _time

        while self._ac_alert_rows_lay.count():
            item = self._ac_alert_rows_lay.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        alerts = alerts[:5]

        for alert in alerts:
            alert_id   = alert.get("id")
            severity   = alert.get("severity", "WARNING")
            rule       = alert.get("rule_name", "Alert")
            msg        = alert.get("message", "")
            ts         = float(alert.get("ts") or 0)
            elapsed    = max(0, int(_time.time()) - int(ts))
            if elapsed < 60:
                time_str = f"{elapsed}s ago"
            elif elapsed < 3600:
                time_str = f"{elapsed // 60}m ago"
            else:
                time_str = f"{elapsed // 3600}h ago"

            dot_color  = RED if severity == "CRITICAL" else AMBER
            label_text = f"{rule} · {msg[:50]}" if msg else rule

            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 1, 0, 1)
            row_lay.setSpacing(6)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{dot_color}; background:transparent; border:none;"
            )

            msg_lbl = QLabel(label_text)
            msg_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
            )
            msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            msg_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            msg_lbl.setToolTip("Click to view in Notifications")
            msg_lbl.mousePressEvent = lambda _e, a=alert: self.alert_view_requested.emit(a)

            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )

            ack_btn = QPushButton("✓")
            ack_btn.setFixedSize(22, 18)
            ack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            ack_btn.setToolTip("Acknowledge this alert")
            ack_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
                f" border:1px solid {BORDER}; border-radius:3px; font-size:10px; }}"
                f"QPushButton:hover {{ color:{GREEN}; border-color:{GREEN}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
            )
            ack_btn.clicked.connect(lambda _=False, aid=alert_id, w=row_w: self._ack_alert_row(aid, w))

            row_lay.addWidget(dot)
            row_lay.addWidget(msg_lbl, 1)
            row_lay.addWidget(time_lbl)
            row_lay.addWidget(ack_btn)
            self._ac_alert_rows_lay.addWidget(row_w)

        has_alerts = len(alerts) > 0
        self._ac_alert_rows_widget.setVisible(has_alerts)
        self._ac_view_all_btn.setVisible(has_alerts)
        self._action_card.setVisible(has_alerts)

    def _ack_alert_row(self, alert_id, row_widget) -> None:
        if self._store and alert_id is not None:
            try:
                self._store.acknowledge_alert(int(alert_id))
            except Exception:
                pass  # non-fatal
        row_widget.setVisible(False)
        row_widget.deleteLater()
        remaining = sum(
            1 for i in range(self._ac_alert_rows_lay.count())
            if self._ac_alert_rows_lay.itemAt(i) and
               self._ac_alert_rows_lay.itemAt(i).widget() and
               self._ac_alert_rows_lay.itemAt(i).widget().isVisible()
        )
        if remaining == 0:
            self._ac_alert_rows_widget.setVisible(False)
            self._ac_view_all_btn.setVisible(False)
            self._action_card.setVisible(False)

    def _scroll_to_setup_card(self) -> None:
        """Scroll to / expand the Getting Started card."""
        if hasattr(self, "_setup_card_top"):
            self._setup_card_top.ensure_expanded()

    # ── Diag summary / scanning state ────────────────────────────────────────

    def refresh_diag_summary(self) -> None:
        import json as _json_mod
        if not hasattr(self, "_rec_diag_lbl"):
            return
        s = QSettings("NetSentinel", "NetSentinel")
        try:
            history = _json_mod.loads(s.value("diagnosis/history", "[]"))
        except Exception:
            history = []
        if not history:
            self._rec_diag_lbl.setText("Last diagnosis:  none yet")
            self._rec_diag_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )
            return
        e = history[0]
        ts = e.get("ts", 0)
        if ts:
            secs = datetime.datetime.now().timestamp() - ts
            if secs < 60:
                ago = "just now"
            elif secs < 3600:
                ago = f"{int(secs // 60)}m ago"
            elif secs < 86400:
                ago = f"{int(secs // 3600)}h ago"
            else:
                ago = f"{int(secs // 86400)}d ago"
        else:
            ago = "—"
        sev = e.get("severity", "INFO")
        n = len(e.get("findings", []))
        sev_colors = {"CRITICAL": RED, "HIGH": RED, "MEDIUM": AMBER, "LOW": GREEN, "INFO": ACCENT}
        color = sev_colors.get(sev, TEXT_MUTED)
        txt = f"Last diagnosis:  {sev} · {n} finding{'s' if n != 1 else ''} · {ago}"
        self._rec_diag_lbl.setText(txt)
        self._rec_diag_lbl.setStyleSheet(
            f"font-size:11px; color:{color}; background:transparent; border:none;"
        )

    def set_scanning(self, running: bool) -> None:
        self._btn_scan.setEnabled(not running)
        if running:
            self._btn_scan.setText("Scanning…")
            self._hero_sub.setText(
                "Scan in progress — tiles will update as each module completes."
            )
            if hasattr(self, "_radar"):
                self._radar.start()
                self._radar.setVisible(True)
        else:
            self._update_scan_button_label()
            self._hero_sub.setText("Discover devices · check stability · detect threats")
            if hasattr(self, "_scan_progress_lbl"):
                self._scan_progress_lbl.setVisible(False)
                self._scan_progress_lbl.setText("")
            if hasattr(self, "_radar"):
                self._radar.stop()
                _t = QTimer(self)
                _t.setSingleShot(True)
                _t.timeout.connect(lambda: self._radar.setVisible(False))
                _t.start(400)

    @pyqtSlot(dict)
    def on_device_found(self, info: dict) -> None:
        """Forward a discovered device to the radar animation."""
        if hasattr(self, "_radar"):
            self._radar.add_device(
                info.get("ip", ""),
                info.get("name", ""),
                info.get("type", ""),
            )

    @pyqtSlot(str)
    def set_scan_progress(self, message: str) -> None:
        """Show per-host scan status inline in the action bar."""
        if hasattr(self, "_scan_progress_lbl"):
            self._scan_progress_lbl.setText(message)
            self._scan_progress_lbl.setVisible(bool(message))
        self._freshness_strip.set_scan_progress("")

    # ── Data preload ──────────────────────────────────────────────────────────

    def _preload_from_store(self) -> None:
        """Populate cards with the most-recent persisted data on first show."""
        if self._store is None:
            return
        try:
            self.objectName()
        except RuntimeError:
            return
        try:
            speed_rows = self._store.query_speed_test_history(hours=168, limit=10)
            if speed_rows:
                row = speed_rows[0]
                dl = row.download_mbps or 0.0
                ul = row.upload_mbps or 0.0
                colour = GREEN if dl > 25 else (AMBER if dl > 5 else RED)
                self._speed_card.set_value(
                    f"{dl:.0f} Mbps",
                    f"/ up {ul:.0f} Mbps",
                    "(last scan)",
                    colour,
                )
                dl_points = [r.download_mbps or 0.0 for r in reversed(speed_rows)]
                self._speed_card.set_sparkline_data(dl_points, colour)
        except Exception:
            pass  # non-fatal

        try:
            self._events_ticker.set_store(self._store)
        except Exception:
            pass  # non-fatal
        try:
            devices = self._store.get_known_devices()
            n = len(devices)
            self._device_count = n
            self._update_scan_button_label()
            if n > 0:
                self._devices_card.set_value(
                    str(n),
                    "on network",
                    "(last scan)",
                    GREEN,
                )
        except Exception:
            pass  # non-fatal
        if self._device_count == 0:
            self._set_first_run_mode(True)
        else:
            self._check_recurring_mode()
        try:
            self._usage_card.refresh()
        except Exception:
            pass  # non-fatal

    # ── Public slots: scan results ────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, result: dict) -> None:
        """Refresh devices and stability cards from an availability cycle result."""
        _now = datetime.datetime.now()
        self._last_scan_ts = _now
        QSettings("NetSentinel", "NetSentinel").setValue("home/last_scan_ts", _now.isoformat())
        self._freshness_strip.set_scan_timestamp(
            "Last scan: just now",
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;",
        )

        devices = result.get("devices", [])
        rtts = result.get("rtts", {})
        n_total = len(devices)
        if n_total > 0 and self._first_run_mode:
            self._set_first_run_mode(False)

        import json as _json
        _qs_delta = QSettings("NetSentinel", "NetSentinel")
        _current_macs = {
            (d.get("mac") or getattr(d, "mac", None) or "")
            for d in devices
            if (d.get("mac") if isinstance(d, dict) else getattr(d, "mac", None))
        }
        _prev_raw = _qs_delta.value("home/last_scan_macs", "[]")
        try:
            _prev_macs = set(_json.loads(_prev_raw))
        except Exception:
            _prev_macs = set()
        _qs_delta.setValue("home/last_scan_macs", _json.dumps(list(_current_macs)))

        # Collect all change chips: devices, CVEs, threat intel
        _parts: list = []
        if _prev_macs:
            _new_count  = len(_current_macs - _prev_macs)
            _gone_count = len(_prev_macs - _current_macs)
            if _new_count:
                _parts.append(f'<span style="color:{AMBER};">+{_new_count} new device{"s" if _new_count != 1 else ""}</span>')
            if _gone_count:
                _parts.append(f'<span style="color:{RED};">−{_gone_count} device{"s" if _gone_count != 1 else ""} missing</span>')

        # CVE delta — new CVE findings added since last scan
        _store = getattr(self, "_store", None)
        if _store is not None:
            try:
                _cve_count = len(_store.list_cve_lifecycles())
                _prev_cve_str = _qs_delta.value("home/last_cve_count", "")
                _prev_cve_count = int(_prev_cve_str) if _prev_cve_str else None
                _qs_delta.setValue("home/last_cve_count", str(_cve_count))
                if _prev_cve_count is not None and _cve_count > _prev_cve_count:
                    _d = _cve_count - _prev_cve_count
                    _parts.append(
                        f'<span style="color:{RED};">+{_d} new CVE{"s" if _d != 1 else ""}</span>'
                    )
            except Exception:
                pass  # non-fatal — store may not have CVE table yet

        if _parts:
            self._delta_chips_lbl.setText("  ·  ".join(_parts))
            self._delta_chips_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._delta_banner.setVisible(True)
        elif _prev_macs:
            # no device or security changes
            self._delta_chips_lbl.setText(
                f'<span style="color:{GREEN};">● No changes since last scan</span>'
            )
            self._delta_chips_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._delta_banner.setVisible(True)

        n_at_risk = sum(
            1 for d in devices
            if d.get("risk_level", "UNKNOWN") in ("HIGH", "UNKNOWN")
        )
        dev_colour = GREEN if n_at_risk == 0 else AMBER
        n_new = sum(1 for d in devices if d.get("is_new", False))
        dev_sub = f"on network" + (f" · {n_new} new" if n_new else "")
        dev_status = (
            f"{n_at_risk} at risk" if n_at_risk
            else ("All healthy" if n_total > 0 else "Run a scan to discover devices")
        )
        self._device_count = n_total
        self._update_scan_button_label()
        self._devices_card.set_value(str(n_total), dev_sub, dev_status, dev_colour)

        avg_rtt: float | None = None
        if rtts:
            all_vals: list[float] = []
            for v in rtts.values():
                if isinstance(v, (int, float)):
                    all_vals.append(float(v))
                elif isinstance(v, list):
                    all_vals.extend(float(x) for x in v if x is not None)
            if all_vals:
                avg_rtt = sum(all_vals) / len(all_vals)
                if avg_rtt < 50:
                    stab_colour, stab_status = GREEN, "Stable connection"
                elif avg_rtt < 150:
                    stab_colour, stab_status = AMBER, "Moderate latency"
                else:
                    stab_colour, stab_status = RED, "High latency"
                self._stability_card.set_value(
                    f"{avg_rtt:.0f} ms", "avg latency", stab_status, stab_colour
                )

        if n_total > 0:
            rtt_part = f" · {avg_rtt:.0f} ms avg latency" if avg_rtt is not None else ""
            risk_part = (
                f" · {n_at_risk} device{'s' if n_at_risk != 1 else ''} at risk"
                if n_at_risk else " · No alerts"
            )
            self._hero_title.setText(
                "Your network is in great shape"
                if n_at_risk == 0 else
                f"{n_at_risk} device{'s' if n_at_risk != 1 else ''} need attention"
            )
            self._hero_sub.setText(
                f"{n_total} device{'s' if n_total != 1 else ''} online"
                f"{rtt_part}{risk_part}"
            )

        if n_total > 0:
            _s = "s" if n_total != 1 else ""
            _new = f"  ·  {n_new} new" if n_new else ""
            self._res_devices_lbl.setText(f"{n_total} device{_s} found{_new}")
            _dev_colour = GREEN if n_at_risk == 0 else AMBER
            self._res_devices_dot.setStyleSheet(
                f"font-size:8px; color:{_dev_colour};"
                " background:transparent; border:none;"
            )

            if avg_rtt is not None:
                _conn_colour = GREEN if avg_rtt < 50 else (AMBER if avg_rtt < 150 else RED)
                self._res_conn_lbl.setText(f"{avg_rtt:.0f} ms avg latency")
            else:
                _conn_colour = GREEN
                self._res_conn_lbl.setText("Connection monitoring active")
            self._res_conn_dot.setStyleSheet(
                f"font-size:8px; color:{_conn_colour};"
                " background:transparent; border:none;"
            )

            if n_at_risk == 0:
                _sec_colour = GREEN
                self._res_security_lbl.setText("No security findings")
            else:
                _sec_colour = RED
                _i = "s" if n_at_risk != 1 else ""
                self._res_security_lbl.setText(f"{n_at_risk} device{_i} need attention")
            self._res_security_dot.setStyleSheet(
                f"font-size:8px; color:{_sec_colour};"
                " background:transparent; border:none;"
            )

            self._results_strip.setVisible(True)

        if n_total > 0:
            self._maybe_show_post_scan_sheet(n_total, n_new, n_at_risk)
        self.refresh_checklist()
        if n_total > 0:
            self._last_scan_ts = datetime.datetime.now()
            qs = QSettings("NetSentinel", "NetSentinel")
            new_count = int(qs.value("home/scan_count", 0)) + 1
            qs.setValue("home/scan_count", new_count)
            if self._recurring_mode:
                self._update_recurring_scan_time()
            else:
                self._check_recurring_mode()
            self._check_scan_milestones(new_count)

    def _check_scan_milestones(self, scan_count: int) -> None:
        """Show one-time milestone banner when scan count crosses a threshold."""
        qs = QSettings("NetSentinel", "NetSentinel")
        if scan_count == 1 and not qs.value("milestone/first_scan_nudge", False, type=bool):
            qs.setValue("milestone/first_scan_nudge", True)
            self._show_first_scan_banner()
        if scan_count == 10 and not qs.value("milestone/scan_10", False, type=bool):
            qs.setValue("milestone/scan_10", True)
            grade = getattr(self, "_current_grade", "") or "—"
            self._show_milestone(
                f"You've run 10 scans — great momentum! "
                f"Your current network grade is {grade}. "
                "Check Network Grade for a full breakdown."
            )

    def _show_first_scan_banner(self) -> None:
        """Display the post-first-scan guidance banner with nav links."""
        if not hasattr(self, "_first_scan_banner"):
            return
        n = self._device_count
        s = "s" if n != 1 else ""
        self._first_scan_lbl.setText(
            f"First scan complete — found {n} device{s}. Here's where to look:"
        )
        self._first_scan_banner.setVisible(True)

    def _dismiss_first_scan_banner(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(
            "milestone/first_scan_nudge_dismissed", True
        )
        if hasattr(self, "_first_scan_banner"):
            self._first_scan_banner.setVisible(False)
        self.window().activateWindow()

    def _check_logger_milestones(self) -> None:
        """Check 24h / 7d logging milestones; call at startup after store is ready."""
        if self._store is None:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            rows = self._store._conn.execute(
                "SELECT MIN(ts), COUNT(*), AVG(rtt_ms) FROM rtt_sample"
            ).fetchone()
        except Exception:
            return
        if not rows or not rows[0]:
            return
        import time as _t
        oldest_ts = rows[0]
        n_rows = rows[1] or 0
        avg_rtt = rows[2] or 0.0
        elapsed_h = (_t.time() - oldest_ts) / 3600.0
        if elapsed_h >= 168 and not qs.value("milestone/logger_7d", False, type=bool):
            qs.setValue("milestone/logger_7d", True)
            self._show_milestone(
                f"7 days of network data! Your logger has recorded {n_rows:,} samples "
                f"with an average RTT of {avg_rtt:.0f} ms. "
                "See Network Logger for trend charts."
            )
        elif elapsed_h >= 24 and not qs.value("milestone/logger_24h", False, type=bool):
            qs.setValue("milestone/logger_24h", True)
            self._show_milestone(
                f"You've been monitoring for 24 hours — {n_rows:,} samples logged, "
                f"average RTT {avg_rtt:.0f} ms. "
                "Check Network Logger to see your stability trends."
            )

    def _show_milestone(self, text: str) -> None:
        """Display text in the milestone banner on the home page."""
        if not hasattr(self, "_milestone_banner"):
            return
        self._milestone_lbl.setText(text)
        self._milestone_banner.setVisible(True)

    @pyqtSlot(object)
    def on_speed_result(self, result) -> None:
        """Refresh the speed mini-card from a SpeedTestResult."""
        dl = getattr(result, "download_mbps", 0.0) or 0.0
        ul = getattr(result, "upload_mbps", 0.0) or 0.0
        colour = GREEN if dl > 25 else (AMBER if dl > 5 else RED)
        self._speed_card.set_value(
            f"{dl:.0f} Mbps",
            f"/ up {ul:.0f} Mbps",
            "last result",
            colour,
        )

    @pyqtSlot(object)
    def on_alert(self, alert) -> None:
        """Prepend an alert row; keep at most 3 rows."""
        if self._alert_count == 0:
            self._no_alerts_lbl.setVisible(False)
            self._no_other_alerts_lbl.setText("No other alerts in the last 24 hours")
            self._no_other_alerts_lbl.setVisible(True)

        if self._alert_count >= 3:
            item = self._alert_inner.takeAt(self._alert_inner.count() - 3)
            if item and item.widget():
                item.widget().deleteLater()
            self._alert_count -= 1

        severity = getattr(alert, "severity", "WARNING")
        msg = str(getattr(alert, "message", alert))
        colour = RED if any(k in severity.upper() for k in ("HIGH", "CRITICAL")) else AMBER
        time_str = datetime.datetime.now().strftime("%H:%M")
        row = _AlertRow(colour, msg[:80], time_str, alert=alert)
        row.clicked.connect(self.alert_view_requested.emit)
        self._alert_inner.insertWidget(0, row)
        self._alert_count += 1

    # ── Monitoring status cards ───────────────────────────────────────────────

    @pyqtSlot(str, float)
    def set_monitoring_status(self, running: bool, elapsed_str: str = "",
                              outage_count: int = 0) -> None:
        """Update the stability monitoring card on the home page."""
        if running:
            outage_txt = f" · {outage_count} outage{'s' if outage_count != 1 else ''}" if outage_count else " · no outages"
            elapsed_txt = f"  {elapsed_str}" if elapsed_str else ""
            self._mon_status_lbl.setText(
                f"Running{elapsed_txt}{outage_txt} — leave the app open to keep logging."
            )
            self._mon_status_lbl.setStyleSheet(
                f"font-size:11px; color:{GREEN}; background:transparent; border:none;"
            )
            self._mon_dot.setStyleSheet(
                f"font-size:9px; color:{GREEN}; background:transparent; border:none;"
            )
            self._btn_mon_start.setText("Stop")
            self._btn_mon_start.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
                f" border-radius:4px; font-size:11px; padding:0 12px; }}"
                f"QPushButton:hover {{ background:{BORDER}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
            )
        else:
            self._mon_status_lbl.setText(
                "Not running — start to log connection stability over time."
            )
            self._mon_status_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            self._mon_dot.setStyleSheet(
                f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            self._btn_mon_start.setText("Start Monitoring")
            self._btn_mon_start.setStyleSheet(
                f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
                f" border-radius:4px; font-size:11px; font-weight:600; padding:0 12px; }}"
                f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )

    def set_last_visit_summary(
        self,
        joined_count: int,
        outage_count: int,
        last_visit_str: str,
        logger_summary: str = "",
        alert_count: int = 0,
        prominent: bool = False,
    ) -> None:
        """Show or hide the 'Since you were last here' banner.

        ``prominent`` (S9-6) swaps in a more visible "welcome back" treatment
        for extended absences (7+ days) — used by tabs_logger._compute_last_visit_summary.
        """
        parts = []
        if joined_count > 0:
            s = "s" if joined_count != 1 else ""
            parts.append(f"{joined_count} new device{s} joined")
        if outage_count > 0:
            s = "s" if outage_count != 1 else ""
            parts.append(f"{outage_count} outage{s} recorded")
        if alert_count > 0:
            s = "s" if alert_count != 1 else ""
            parts.append(f"{alert_count} alert{s} fired")
        if logger_summary:
            parts.append(logger_summary)

        if not parts and not prominent:
            self._last_visit_card.setVisible(False)
            return

        self._apply_last_visit_style(prominent)
        if parts:
            self._lv_text.setText(f"Since {last_visit_str}: {'  ·  '.join(parts)}.")
        else:
            self._lv_text.setText(
                f"Since {last_visit_str}: nothing changed — your network has been healthy."
            )
        self._last_visit_card.setVisible(True)

    def _apply_last_visit_style(self, prominent: bool) -> None:
        """Swap the 'since last visit' card between routine and prominent styles (S9-6)."""
        if prominent:
            self._last_visit_card.setStyleSheet(
                f"QFrame#lastVisitCard {{ background:{BG_CARD}; border:1px solid {alpha(ACCENT, 0x44)};"
                f" border-left:3px solid {ACCENT}; border-radius:{CARD_RADIUS}; }}"
            )
            self._lv_icon.setStyleSheet(
                f"font-size:18px; color:{ACCENT}; background:transparent; border:none;"
            )
            self._lv_title.setText("Welcome back!")
            self._lv_title.setStyleSheet(
                f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._lv_title.setVisible(True)
            self._lv_text.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
        else:
            self._last_visit_card.setStyleSheet(
                f"QFrame#lastVisitCard {{ background:{PRO_WARN_BG}; border:1px solid {UPDATE_BAR_BORDER};"
                f" border-radius:{CARD_RADIUS}; }}"
            )
            self._lv_icon.setStyleSheet(
                f"font-size:13px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
            )
            self._lv_title.setVisible(False)
            self._lv_text.setStyleSheet(
                f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
            )

    # ── Grade display ─────────────────────────────────────────────────────────

    def _update_grade_delta(self, current_score: float) -> None:
        """HOME-2: show week-over-week grade delta chip beside the grade ring."""
        import time as _t
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            history: list = json.loads(qs.value(_GRADE_HISTORY_KEY, "[]", type=str))
        except Exception:
            history = []
        now = _t.time()
        week_ago = now - 7 * 86400
        two_weeks_ago = now - 14 * 86400
        this_week  = [e["score"] for e in history if e.get("ts", 0) >= week_ago and "score" in e]
        last_week  = [e["score"] for e in history
                      if two_weeks_ago <= e.get("ts", 0) < week_ago and "score" in e]
        if len(this_week) < 2 or not last_week:
            self._grade_delta_lbl.setVisible(False)
            return
        this_avg = sum(this_week) / len(this_week)
        last_avg = sum(last_week) / len(last_week)
        delta = this_avg - last_avg
        if abs(delta) < 1:
            text  = "— no change"
            color = TEXT_SECONDARY
        elif delta > 0:
            text  = f"↑ +{delta:.0f} vs last week"
            color = GREEN
        else:
            text  = f"↓ {delta:.0f} vs last week"
            color = RED
        self._grade_delta_lbl.setText(text)
        self._grade_delta_lbl.setStyleSheet(
            f"font-size:10px; color:{color}; background:transparent; border:none;"
        )
        self._grade_delta_lbl.setVisible(True)

    def on_grade(self, grade: str, score: float) -> None:
        """Update the hero grade ring and sparkline."""
        from ui.widgets.home_widgets import _append_grade_history
        self._current_grade = grade
        self._grade_circle.set_grade(grade, score)
        _append_grade_history(grade, score)
        self._update_grade_delta(score)
        self._refresh_sparkline()
        if self._recurring_mode:
            self._update_recurring_grade_display()
        if grade and grade not in ("?", "—", ""):
            self._maybe_show_coach_grade()

    def _maybe_show_coach_grade(self) -> None:
        if not self.isVisible():
            return
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("tour/v1_done", False, type=bool):
            return
        key = "coach/grade_shown"
        if qs.value(key, False, type=bool):
            return
        win = self.window()
        if not (win and win.isVisible()):
            return
        circle = getattr(self, "_grade_circle", None)
        if not circle:
            return
        from ui.widgets.coach_mark import CoachMarkChain
        CoachMarkChain(
            win,
            [{
                "target": lambda c=circle: c,
                "title": "Your network grade",
                "body": (
                    "This score reflects 8 dimensions of network health. "
                    "Click the ring to see the breakdown and improve your score."
                ),
            }],
            on_done=lambda: QSettings("NetSentinel", "NetSentinel").setValue(key, True),
        ).start()

    def on_grade_details(self, grade: str, score: float, dimensions: list) -> None:
        """Store grade sub-score dimensions and reveal the (?) button."""
        self.on_grade(grade, score)
        self._grade_dimensions = dimensions or []
        self._grade_details_btn.setVisible(bool(dimensions))

    def _show_grade_breakdown(self) -> None:
        dlg = _GradeBreakdownDialog(
            self._current_grade,
            self._grade_dimensions,
            parent=self,
        )
        dlg.exec()

    def on_live_challenge(self, scenario) -> None:
        """Show a persistent amber notice when Network Logger flags a network event.

        The banner leads with the event's own framing (e.g. "New device detected")
        rather than a hard-coded "Connectivity issue" — most Network Logger events
        (new devices, inventory changes) are notices, not faults, so alarming
        wording is reserved for events that describe an actual problem.
        """
        if not hasattr(self, "_live_challenge_banner"):
            return
        import datetime as _dt
        time_str = _dt.datetime.now().strftime("%H:%M")
        title = (getattr(scenario, "title", "") or "").strip() if scenario else ""
        lead = title if title else "Network event detected"
        self._lc_text.setText(f"{lead} at {time_str}")
        self._live_challenge_banner.setVisible(True)

    def on_hardware_added(self, path: str = "", label: str = "") -> None:
        """Called when a hardware plugin is successfully registered."""
        card = getattr(self, "_setup_card_top", None)
        if card and hasattr(card, "refresh_checklist"):
            card.refresh_checklist(self._device_count)
        if hasattr(self, "_refresh_hw_nudge"):
            self._refresh_hw_nudge()

    def on_hw_detected(self, matches: list) -> None:
        """Called when hw_detect_worker finds compatible hardware on the network."""
        card = getattr(self, "_setup_card_top", None)
        if card is None or not hasattr(card, "notify_hw_detected"):
            return
        for match in matches:
            hw_type = match.get("type", "") if isinstance(match, dict) else ""
            if hw_type:
                card.notify_hw_detected(hw_type)

    # ── Scan Center card ──────────────────────────────────────────────────────

    def _build_scan_center_card(self) -> "QFrame":
        """Build the compact Scan Center card — 5 scan categories with state dots."""
        from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
        from PyQt6.QtCore import Qt

        card = QFrame()
        card.setObjectName("scanCenterCard")
        card.setStyleSheet(
            f"QFrame#scanCenterCard {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Card header
        hdr_frame = QFrame()
        hdr_frame.setFixedHeight(32)
        hdr_frame.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border-bottom:1px solid {BORDER}; }}"
        )
        hdr_lay = QHBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(12, 0, 10, 0)
        hdr_lay.setSpacing(8)
        hdr_lbl = QLabel("SCAN CENTER")
        hdr_lbl.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY}; border:none;"
            " letter-spacing:1.5px;"
        )
        run_all_btn = QPushButton("▶  Rescan")
        run_all_btn.setFixedHeight(22)
        run_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        run_all_btn.setToolTip(
            "Runs a full device scan. For Security Audit, Speed Test, and other "
            "categories, use each row's own button below."
        )
        run_all_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; font-size:10px;"
            f" border:none; border-radius:3px; padding:0 8px; }}"
            f"QPushButton:hover   {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        run_all_btn.clicked.connect(self.rescan_requested)
        hdr_lay.addWidget(hdr_lbl)
        hdr_lay.addStretch()
        hdr_lay.addWidget(run_all_btn)
        outer.addWidget(hdr_frame)

        # Row definitions: (display_name, registry_key, btn_text, nav_target)
        # nav_target=None → emit rescan_requested
        _ROWS: list = [
            ("Device Scan",    "Devices",             "Rescan",      None),
            ("Security Audit", "_security_aggregate", "Run Audit →", "Security Overview"),
            ("Speed Test",     "Speed Test",          "Run Test →",  "Speed Test"),
            ("Service Health", "Service Diagnostics", "View →",      "Service Diagnostics"),
            ("Network Logger", "_logger",             "View →",      "Network Logger"),
        ]
        self._scan_center_row_configs: list = _ROWS
        self._scan_center_dot_labels:  list = []
        self._scan_center_age_labels:  list = []

        rows_frame = QFrame()
        rows_frame.setStyleSheet(f"QFrame {{ background:{BG_CARD}; border:none; }}")
        rows_lay = QVBoxLayout(rows_frame)
        rows_lay.setContentsMargins(12, 2, 10, 4)
        rows_lay.setSpacing(0)

        for display, _, btn_text, nav_target in _ROWS:
            row_lay = QHBoxLayout()
            row_lay.setContentsMargins(0, 3, 0, 3)
            row_lay.setSpacing(8)

            dot = QLabel("●")
            dot.setFixedWidth(14)
            dot.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )

            name_lbl = QLabel(display)
            name_lbl.setFixedWidth(110)
            name_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
            )

            age_lbl = QLabel("Never")
            age_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            )

            btn = QPushButton(btn_text)
            btn.setFixedHeight(22)
            btn.setFixedWidth(96)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{ACCENT}; font-size:10px;"
                f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; }}"
                f"QPushButton:hover   {{ background:{BG_HOVER}; border-color:{ACCENT}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
            )
            if nav_target is None:
                btn.clicked.connect(self.rescan_requested)
            else:
                btn.clicked.connect(lambda _=False, t=nav_target: self.navigate_to.emit(t))

            row_lay.addWidget(dot)
            row_lay.addWidget(name_lbl)
            row_lay.addWidget(age_lbl, 1)
            row_lay.addWidget(btn)
            rows_lay.addLayout(row_lay)

            self._scan_center_dot_labels.append(dot)
            self._scan_center_age_labels.append(age_lbl)

        outer.addWidget(rows_frame)
        return card

    def _refresh_scan_center(self) -> None:
        """Refresh Scan Center dots and age strings from the persisted scan registry."""
        if not hasattr(self, "_scan_center_dot_labels"):
            return
        import json as _json
        from ui.tabs_helpers import _scan_age_str

        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            registry: dict = _json.loads(qs.value("scan_registry/state", "{}", type=str))
        except Exception:
            registry = {}

        _SEC_LABELS = [
            "Port Scan (TCP)", "CVE Lookup", "OS Detection",
            "Login Test", "Threat Intel", "TLS & Exposure",
            "Exposed to Internet", "Full Device Discovery",
        ]
        _sec_ts    = 0.0
        _sec_state = "never"
        for sec_lbl in _SEC_LABELS:
            entry = registry.get(sec_lbl, {})
            st = entry.get("state", "never")
            ts = entry.get("ts", 0.0) or 0.0
            if st == "fresh" and (_sec_state != "fresh" or ts > _sec_ts):
                _sec_ts    = ts
                _sec_state = "fresh"
            elif st == "stale" and _sec_state == "never":
                _sec_ts    = ts
                _sec_state = "stale"

        _STATE_COLOR = {
            "fresh":   GREEN,
            "stale":   AMBER,
            "running": ACCENT,
            "error":   RED,
            "never":   TEXT_MUTED,
        }

        for i, (_, reg_key, _, _nav) in enumerate(self._scan_center_row_configs):
            dot     = self._scan_center_dot_labels[i]
            age_lbl = self._scan_center_age_labels[i]

            if reg_key == "_security_aggregate":
                state = _sec_state
                ts    = _sec_ts
            elif reg_key == "_logger":
                state = "never"
                ts    = 0.0
            else:
                entry = registry.get(reg_key, {})
                state = entry.get("state", "never")
                ts    = entry.get("ts", 0.0) or 0.0

            color = _STATE_COLOR.get(state, TEXT_MUTED)
            dot.setStyleSheet(
                f"font-size:10px; color:{color}; background:transparent; border:none;"
            )
            age_lbl.setText(_scan_age_str(ts) if ts else "Never")

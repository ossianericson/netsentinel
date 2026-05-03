"""
HomePage — introductory landing page shown in Home mode.

Hero card (network grade), three mini metric cards (speed / stability / devices),
and a recent-alerts strip.

Architecture rules observed:
  • All colours from ui.styles — no hardcoded hex values.
  • No blocking I/O. Pure display widget; all data arrives via public slots.
  • Outer scroll area so the content is never clipped on small windows.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    AMBER,
    BG_CARD,
    BG_DARK,
    BORDER,
    GREEN,
    PRO_WARN_BG,
    RED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    UPDATE_BAR_BG,
    UPDATE_BAR_BORDER,
    UPDATE_BAR_FG,
)


class HomePage(QWidget):
    """Simple landing page for new / Home-mode users."""

    #: Emitted when a mini-card is clicked; carries the target page label string.
    navigate_to = pyqtSignal(str)

    # ── _MiniCard ─────────────────────────────────────────────────────────────

    class _MiniCard(QFrame):
        """One of the three top-line metric summary cards."""

        #: Emitted when the card is clicked.
        clicked = pyqtSignal()

        def mousePressEvent(self, event) -> None:  # type: ignore[override]
            self.clicked.emit()
            super().mousePressEvent(event)

        def __init__(self, icon: str, title: str, val: str, sub: str,
                     parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setMinimumHeight(100)
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setStyleSheet(
                f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:0px; }}"
            )
            lay = QVBoxLayout(self)
            lay.setContentsMargins(12, 8, 12, 8)
            lay.setSpacing(2)

            self._icon_lbl = QLabel(icon)
            self._icon_lbl.setStyleSheet(
                f"font-size:13px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._title_lbl = QLabel(title)
            self._title_lbl.setStyleSheet(
                f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._val_lbl = QLabel(val)
            self._val_lbl.setStyleSheet(
                f"font-size:20px; font-weight:bold; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            self._sub_lbl = QLabel(sub)
            self._sub_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )

            self._dot_lbl = QLabel("\u25cf")
            self._dot_lbl.setStyleSheet(
                f"font-size:8px; color:{GREEN}; background:transparent; border:none;"
            )
            self._dot_lbl.setFixedWidth(12)
            self._status_lbl = QLabel("")
            self._status_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            status_row = QHBoxLayout()
            status_row.setContentsMargins(0, 0, 0, 0)
            status_row.setSpacing(3)
            status_row.addWidget(self._dot_lbl)
            status_row.addWidget(self._status_lbl)
            status_row.addStretch()

            lay.addWidget(self._icon_lbl)
            lay.addWidget(self._title_lbl)
            lay.addWidget(self._val_lbl)
            lay.addWidget(self._sub_lbl)
            lay.addLayout(status_row)

        def set_value(self, val: str, sub: str, status: str, colour: str) -> None:
            """Update the card's main value, subtitle, status dot and label."""
            self._val_lbl.setText(val)
            self._val_lbl.setStyleSheet(
                f"font-size:20px; font-weight:bold; color:{colour};"
                " background:transparent; border:none;"
            )
            self._sub_lbl.setText(sub)
            self._dot_lbl.setStyleSheet(
                f"font-size:8px; color:{colour};"
                " background:transparent; border:none;"
            )
            self._status_lbl.setText(status)

    # ── _AlertRow ─────────────────────────────────────────────────────────────

    class _AlertRow(QFrame):
        """Single row in the recent-alerts strip."""

        def __init__(self, colour: str, msg: str, time_str: str,
                     parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setFixedHeight(28)
            self.setStyleSheet("QFrame { background:transparent; border:none; }")
            lay = QHBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)

            dot = QLabel("\u25cf")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{colour};"
                " background:transparent; border:none;"
            )
            msg_lbl = QLabel(msg)
            msg_lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            msg_lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            time_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            lay.addWidget(dot)
            lay.addWidget(msg_lbl, 1)
            lay.addWidget(time_lbl)

    # ── Constructor ───────────────────────────────────────────────────────────

    def __init__(self, store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._alert_count = 0
        self._device_count: int = 0
        self._signals_connected: bool = False
        self._setup_ui()
        if self._store is not None:
            from PyQt6.QtCore import QTimer
            # Use a parented QTimer so it is automatically destroyed with this
            # widget.  QTimer.singleShot(0, slot) creates an un-parented timer
            # that can fire after the widget's C++ object has been deleted,
            # corrupting the heap on Linux (SIGABRT ~30 tests later).
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._preload_from_store)
            _t.start(0)

    # ── UI build ──────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("homePageRoot")
        self.setStyleSheet(f"QWidget#homePageRoot {{ background:{BG_DARK}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        inner = QWidget()
        inner.setObjectName("homepageInner")
        inner.setStyleSheet(f"QWidget#homepageInner {{ background:{BG_DARK}; }}")
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # ── Guided Troubleshooter banner ──────────────────────────────────────
        banner = QFrame()
        banner.setStyleSheet(
            f"QFrame {{ background:{UPDATE_BAR_BG}; border:1px solid {UPDATE_BAR_BORDER};"
            f" border-radius:4px; }}"
        )
        banner_lay = QHBoxLayout(banner)
        banner_lay.setContentsMargins(12, 6, 12, 6)
        banner_lay.setSpacing(8)
        _banner_icon = QLabel("✦")
        _banner_icon.setStyleSheet(
            f"font-size:13px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        _banner_icon.setFixedWidth(18)
        _banner_text = QLabel(
            "Not sure where to start? The Guided Troubleshooter walks you through"
            " common network issues."
        )
        _banner_text.setStyleSheet(
            f"font-size:11px; color:{UPDATE_BAR_FG}; background:transparent; border:none;"
        )
        _banner_text.setWordWrap(True)
        self._btn_diagnose = QPushButton("✦  Guided Troubleshooter")
        banner_lay.addWidget(_banner_icon)
        banner_lay.addWidget(_banner_text, 1)
        banner_lay.addWidget(self._btn_diagnose)
        lay.addWidget(banner)

        # ── Hero card ─────────────────────────────────────────────────────────
        hero = QFrame()
        hero.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:0px; }}"
        )
        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(16, 16, 16, 16)
        hero_lay.setSpacing(16)

        self._grade_circle = QLabel("\u2013")
        self._grade_circle.setFixedSize(68, 68)
        self._grade_circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grade_circle.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{TEXT_SECONDARY};"
            f" border:3px solid {BORDER}; border-radius:34px;"
            f" background:{BG_CARD};"
        )
        hero_lay.addWidget(self._grade_circle)

        right = QVBoxLayout()
        right.setSpacing(4)

        self._hero_title = QLabel("What's on your network?")
        self._hero_title.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        self._hero_sub = QLabel(
            "One scan discovers every device, checks connection health, and"
            " fills in the Devices, DNS, and Security tabs with live data."
        )
        self._hero_sub.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._hero_sub.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._btn_scan = QPushButton("\u25b6  Discover My Network")
        self._btn_scan.setObjectName("btnScanHero")
        self._btn_isp = QPushButton("\ud83d\udcca  View ISP Report")
        self._btn_isp.setStyleSheet(
            "QPushButton { min-height: 34px; font-size: 12px; font-weight: 600; }"
        )
        btn_row.addWidget(self._btn_scan)
        btn_row.addWidget(self._btn_isp)
        btn_row.addStretch()

        right.addWidget(self._hero_title)
        right.addWidget(self._hero_sub)
        right.addLayout(btn_row)
        hero_lay.addLayout(right, 1)
        lay.addWidget(hero)

        # ── "Three things" section label ──────────────────────────────────────
        _sec1 = QLabel("THE THREE THINGS THAT MATTER")
        _sec1.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(_sec1)

        # ── Mini-card row — three equal-width columns ────────────────────────
        card_row = QHBoxLayout()
        card_row.setSpacing(8)
        self._speed_card     = HomePage._MiniCard("\u26a1", "Speed",     "\u2013", "\u2013")
        self._stability_card = HomePage._MiniCard("\u25ce", "Stability", "\u2013", "\u2013")
        self._devices_card   = HomePage._MiniCard("\u2295", "Devices",   "\u2013", "\u2013")
        for _card in (self._speed_card, self._stability_card, self._devices_card):
            card_row.addWidget(_card, 1)  # stretch=1 → equal width
        self._speed_card.clicked.connect(
            lambda: self.navigate_to.emit("Speed Test"))
        self._stability_card.clicked.connect(
            lambda: self.navigate_to.emit("DNS & Outages"))
        self._devices_card.clicked.connect(
            lambda: self.navigate_to.emit("Devices on Network"))
        lay.addLayout(card_row)

        # ── Post-scan results strip (hidden until first scan completes) ────────
        self._results_strip = QFrame()
        self._results_strip.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        self._results_strip.setVisible(False)
        _strip_lay = QVBoxLayout(self._results_strip)
        _strip_lay.setContentsMargins(12, 8, 12, 8)
        _strip_lay.setSpacing(6)

        _strip_hdr = QLabel("EXPLORE YOUR RESULTS")
        _strip_hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        _strip_lay.addWidget(_strip_hdr)

        def _result_row(default_text: str, btn_label: str, target: str):
            rw = QWidget()
            rw.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(rw)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none;"
            )
            lbl = QLabel(default_text)
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY};"
                " background:transparent; border:none;"
            )
            btn = QPushButton(btn_label)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px;"
                f" background:transparent; border:none; padding:0; }}"
                f"QPushButton:hover {{ color:#005A9E; }}"
            )
            btn.clicked.connect(lambda: self.navigate_to.emit(target))
            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            return rw, lbl, dot

        _dev_row, self._res_devices_lbl, self._res_devices_dot = \
            _result_row("–", "View Devices →", "Devices on Network")
        _conn_row, self._res_conn_lbl, self._res_conn_dot = \
            _result_row("–", "View Connection →", "DNS & Outages")
        _sec_row, self._res_security_lbl, self._res_security_dot = \
            _result_row("–", "View Overview →", "Overview")

        _strip_lay.addWidget(_dev_row)
        _strip_lay.addWidget(_conn_row)
        _strip_lay.addWidget(_sec_row)
        lay.addWidget(self._results_strip)

        # ── Recent alerts section label ───────────────────────────────────────
        _sec2 = QLabel("RECENT ALERTS")
        _sec2.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; padding-top:4px; letter-spacing:1px;"
        )
        lay.addWidget(_sec2)

        # ── Alert card ────────────────────────────────────────────────────────
        alert_card = QFrame()
        alert_card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:0px; }}"
        )
        self._alert_inner = QVBoxLayout(alert_card)
        self._alert_inner.setContentsMargins(12, 8, 12, 8)
        self._alert_inner.setSpacing(2)

        self._no_alerts_lbl = QLabel("No alerts \u2014 configure alerts in Settings to get notified")
        self._no_alerts_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_alerts_lbl)
        # Permanent footer — always visible; text changes to "No other alerts" once rows appear
        self._no_other_alerts_lbl = QLabel()
        self._no_other_alerts_lbl.setVisible(False)
        self._no_other_alerts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        self._alert_inner.addWidget(self._no_other_alerts_lbl)
        lay.addWidget(alert_card)
        lay.addStretch()

    def _update_scan_button_label(self) -> None:
        label = (
            "▶  Discover My Network" if self._device_count == 0
            else "▶  Rescan"
        )
        self._btn_scan.setText(label)

    # ── Startup preload ───────────────────────────────────────────────────────

    def _preload_from_store(self) -> None:
        """Populate cards with the most-recent persisted data on first show."""
        if self._store is None:
            return
        try:
            # Guard against the widget being deleted before the timer fires.
            self.objectName()
        except RuntimeError:
            return
        try:
            # Speed card — last recorded test result
            speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
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
        except Exception:
            pass
        try:
            # Devices card — count of known devices
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
            pass

    # ── Public slots ──────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def on_cycle_done(self, result: dict) -> None:
        """Refresh devices and stability cards from an availability cycle result."""
        devices = result.get("devices", [])
        rtts = result.get("rtts", {})

        # Devices card
        n_total = len(devices)
        n_at_risk = sum(
            1 for d in devices
            if d.get("risk_level", "UNKNOWN") in ("HIGH", "UNKNOWN")
        )
        dev_colour = GREEN if n_at_risk == 0 else AMBER
        n_new = sum(1 for d in devices if d.get("is_new", False))
        dev_sub = f"on network" + (f" \u00b7 {n_new} new" if n_new else "")
        dev_status = (
            f"{n_at_risk} at risk" if n_at_risk
            else ("All healthy" if n_total > 0 else "Run a scan to discover devices")
        )
        self._device_count = n_total
        self._update_scan_button_label()
        self._devices_card.set_value(str(n_total), dev_sub, dev_status, dev_colour)

        # Stability card \u2014 average RTT across all hosts
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

        # Hero title + inline stats subtitle
        if n_total > 0:
            rtt_part = f" \u00b7 {avg_rtt:.0f} ms avg latency" if avg_rtt is not None else ""
            risk_part = (
                f" \u00b7 {n_at_risk} device{'s' if n_at_risk != 1 else ''} at risk"
                if n_at_risk else " \u00b7 No alerts"
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

        # \u2500\u2500 Results strip \u2014 show after first scan, update on every cycle \u2500\u2500\u2500\u2500\u2500\u2500
        if n_total > 0:
            # Devices row
            _s = "s" if n_total != 1 else ""
            _new = f"  \u00b7  {n_new} new" if n_new else ""
            self._res_devices_lbl.setText(
                f"{n_total} device{_s} found{_new}"
            )
            _dev_colour = GREEN if n_at_risk == 0 else AMBER
            self._res_devices_dot.setStyleSheet(
                f"font-size:8px; color:{_dev_colour};"
                " background:transparent; border:none;"
            )

            # Connection row
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

            # Security row
            if n_at_risk == 0:
                _sec_colour = GREEN
                self._res_security_lbl.setText("No security issues detected")
            else:
                _sec_colour = RED
                _i = "s" if n_at_risk != 1 else ""
                self._res_security_lbl.setText(
                    f"{n_at_risk} device{_i} need attention"
                )
            self._res_security_dot.setStyleSheet(
                f"font-size:8px; color:{_sec_colour};"
                " background:transparent; border:none;"
            )

            self._results_strip.setVisible(True)

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
            # Switch from the initial label to the "no other alerts" footer
            self._no_alerts_lbl.setVisible(False)
            self._no_other_alerts_lbl.setText("No other alerts in the last 24 hours")
            self._no_other_alerts_lbl.setVisible(True)

        # Remove oldest if already at limit (insert position 0 = first widget slot)
        if self._alert_count >= 3:
            # The bottom 2 items are the two footer labels; remove item at count()-3
            item = self._alert_inner.takeAt(self._alert_inner.count() - 3)
            if item and item.widget():
                item.widget().deleteLater()
            self._alert_count -= 1

        severity = getattr(alert, "severity", "WARNING")
        msg = str(getattr(alert, "message", alert))
        colour = RED if any(k in severity.upper() for k in ("HIGH", "CRITICAL")) else AMBER
        time_str = datetime.datetime.now().strftime("%H:%M")
        row = HomePage._AlertRow(colour, msg[:80], time_str)
        # Insert before the footer labels (at index 0 — top of list)
        self._alert_inner.insertWidget(0, row)
        self._alert_count += 1

    @pyqtSlot(str, float)
    def on_grade(self, grade: str, score: float) -> None:  # noqa: ARG002
        """Update the hero grade circle text and colour."""
        if grade in ("A", "B"):
            colour = GREEN
        elif grade == "C":
            colour = AMBER
        else:
            colour = RED
        self._grade_circle.setText(grade)
        self._grade_circle.setStyleSheet(
            f"font-size:28px; font-weight:bold; color:{colour};"
            f" border:3px solid {colour}; border-radius:34px;"
            f" background:{BG_CARD};"
        )


# ── Standard mode welcome page ────────────────────────────────────────────────

class StandardWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Standard mode.
    Displays a 2-column feature card grid: 'WHAT EACH SECTION GIVES YOU'.
    """

    _FEATURES = [
        ("\u26a1", "Speed test",      AMBER,        ["Download / upload speed",
                                                      "Ookla or fallback backends",
                                                      "Historical trend chart"]),
        ("\u25ce", "DNS & Stability", ACCENT,        ["Live ping + DNS latency graph",
                                                      "Outage detection & log",
                                                      "STP reconvergence signature"]),
        ("\u2295", "Devices",         TEXT_PRIMARY,  ["IP, MAC, vendor, model",
                                                      "Right-click How to Fix",
                                                      "Availability history per device"]),
        ("\u25b2", "Live Bandwidth",  TEXT_PRIMARY,  ["Per-device rx/tx Mbps",
                                                      "60-second rolling area chart",
                                                      "Session totals table"]),
        ("\u25fc", "Network Grade",   TEXT_PRIMARY,  ["A\u2013F across 8 dimensions",
                                                      "Colour-coded verdict per metric",
                                                      "Actionable fix tip per grade"]),
        ("\u2197", "ISP Report",      TEXT_PRIMARY,  ["Self-contained HTML export",
                                                      "MTR hop table + outage log",
                                                      "Print-to-PDF for ISP support"]),
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
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        hdr = QLabel("WHAT EACH SECTION GIVES YOU")
        hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " letter-spacing:1px; padding-bottom:2px;"
        )
        lay.addWidget(hdr)

        # 2-column grid of feature cards
        from PyQt6.QtWidgets import QGridLayout
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
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(6)

        # Icon + title row
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
            b = QLabel(f"\u2022 {bullet}")
            b.setStyleSheet(
                f"font-size:11px; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; padding-left:4px;"
            )
            card_lay.addWidget(b)

        return card


# ── Pro mode welcome page ─────────────────────────────────────────────────────

class ProWelcomePage(QWidget):
    """
    Landing page shown when 'Home' is selected in Pro mode.
    Shows an admin-required warning and security audit capability cards.
    """

    _CAPABILITIES = [
        ("\u25ce", "Port scanning",       ["\u2022 TCP connect + SYN (Scapy)",
                                           "\u2022 UDP scanner (DNS/SNMP/NTP)",
                                           "\u2022 Stealth / normal / fast modes"]),
        ("\u25ce", "CVE tracker",         ["\u2022 NVD API v2 lookup per host",
                                           "\u2022 Lifecycle state machine",
                                           "\u2022 Days-open counter, owner field"]),
        ("\u25ce", "Threat Intelligence", ["\u2022 Feodo Tracker + Emerging Threats",
                                           "\u2022 AbuseIPDB v2 lookup",
                                           "\u2022 Blocklist KPI tiles"]),
        ("\u25fc", "TLS & exposure",      ["\u2022 Per-host cert expiry monitor",
                                           "\u2022 WAN / CGNAT / UPnP exposure",
                                           "\u2022 Cloud metadata probe"]),
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
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        # Red warning box
        warn = QFrame()
        warn.setStyleSheet(
            f"QFrame {{ background:{PRO_WARN_BG}; border:1px solid {RED}; }}"
        )
        warn_lay = QHBoxLayout(warn)
        warn_lay.setContentsMargins(12, 10, 12, 10)
        warn_icon = QLabel("\u26a0")
        warn_icon.setStyleSheet(
            f"font-size:16px; color:{RED}; background:transparent; border:none;"
        )
        warn_icon.setFixedWidth(22)
        warn_text = QLabel(
            "Security Audit tools require administrator privileges and Npcap. "
            "They are intentionally separated from home-user features to avoid confusion."
        )
        warn_text.setWordWrap(True)
        warn_text.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent; border:none;"
        )
        warn_lay.addWidget(warn_icon)
        warn_lay.addWidget(warn_text, 1)
        lay.addWidget(warn)

        hdr = QLabel("SECURITY AUDIT CAPABILITIES")
        hdr.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;"
            " letter-spacing:1px; padding-top:4px; padding-bottom:2px;"
        )
        lay.addWidget(hdr)

        # 2-column grid
        from PyQt6.QtWidgets import QGridLayout
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
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; }}"
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

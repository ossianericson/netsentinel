"""
notif_extra_channels.py — _NotifExtraChannelsMixin: Pushover, Ntfy, Telegram, Escalation, Weekly Digest channel builders.

Extracted from ui/pages/notif_channel_panels.py (Sprint 13) to keep that file within budget.
NotificationsPage imports both _NotifChannelsMixin and _NotifExtraChannelsMixin.
"""
from __future__ import annotations


from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.pages.notif_channel_panels import (
    _KR_PUSHOVER_TOKEN_KEY, _KR_PUSHOVER_USER_KEY,
    _KR_NTFY_TOKEN_KEY, _KR_TELEGRAM_TOKEN_KEY, _card, _field_row, _lineedit, _severity_combo,
)
from ui import styles as _s


class _NotifExtraChannelsMixin:
    """Mixin providing Pushover, Ntfy, Telegram, Escalation, and Weekly Digest card builders.

    Extracted from ui/pages/notif_channel_panels.py (Sprint 13).
    """

    def _build_pushover_card(self) -> QWidget:
        card, bl = _card("Pushover Mobile Push")
        self._chk_pushover = QCheckBox("Enable Pushover notifications")
        _s.themed_ss(self._chk_pushover, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_pushover.stateChanged.connect(self._save)
        bl.addWidget(self._chk_pushover)
        self._pushover_token = _lineedit("App API Token", password=True)
        self._pushover_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("API Token:", self._pushover_token))
        bl.addWidget(self._kr_note_row(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token))
        self._pushover_user = _lineedit("User / Group Key", password=True)
        self._pushover_user.editingFinished.connect(self._save)
        bl.addLayout(_field_row("User Key:", self._pushover_user))
        bl.addWidget(self._kr_note_row(_KR_PUSHOVER_USER_KEY, self._pushover_user))
        self._pushover_severity = _severity_combo("WARNING")
        self._pushover_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._pushover_severity))
        note = QLabel(
            "Delivers instant push notifications to iOS and Android via Pushover. "
            "Create an app at pushover.net to get an API token. "
            "Both the API Token and User Key are stored in the OS keychain."
        )
        note.setWordWrap(True)
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Push")
        btn_test.setFixedHeight(26)
        _s.themed_ss(btn_test, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            "border-radius:2px;padding:0 14px;font-size:11px;}}"
            "QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
        btn_test.clicked.connect(self._test_pushover)
        self._test_btns["pushover"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["pushover"] = _lbl
        bl.addWidget(_lbl)
        return card

    def _build_ntfy_card(self) -> QWidget:
        card, bl = _card("ntfy Push Notification (ntfy.sh / self-hosted)")
        self._chk_ntfy = QCheckBox("Enable ntfy notifications")
        _s.themed_ss(self._chk_ntfy, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_ntfy.stateChanged.connect(self._save)
        bl.addWidget(self._chk_ntfy)
        self._ntfy_url = _lineedit("https://ntfy.sh/my-netsentinel-topic")
        self._ntfy_url.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Topic URL:", self._ntfy_url))
        self._ntfy_token = _lineedit("Access token (optional)", password=True)
        self._ntfy_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Access Token:", self._ntfy_token))
        bl.addWidget(self._kr_note_row(_KR_NTFY_TOKEN_KEY, self._ntfy_token))
        self._ntfy_severity = _severity_combo("WARNING")
        self._ntfy_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._ntfy_severity))
        note = QLabel(
            "ntfy.sh is a free, open-source push notification service. "
            "Subscribe to your topic in the ntfy mobile app or browser. "
            "The access token (required only for protected topics) is stored in the OS keychain."
        )
        note.setWordWrap(True)
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Notification")
        btn_test.setFixedHeight(26)
        _s.themed_ss(btn_test, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            "border-radius:2px;padding:0 14px;font-size:11px;}}"
            "QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
        btn_test.clicked.connect(self._test_ntfy)
        self._test_btns["ntfy"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["ntfy"] = _lbl
        bl.addWidget(_lbl)
        return card

    def _build_telegram_card(self) -> QWidget:
        card, bl = _card("Telegram Bot Notification")
        self._chk_telegram = QCheckBox("Enable Telegram notifications")
        _s.themed_ss(self._chk_telegram, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_telegram.stateChanged.connect(self._save)
        bl.addWidget(self._chk_telegram)
        self._telegram_token = _lineedit("Bot token from @BotFather", password=True)
        self._telegram_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Bot Token:", self._telegram_token))
        bl.addWidget(self._kr_note_row(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token))
        self._telegram_chat = _lineedit("Chat ID (e.g. -100123456789)")
        self._telegram_chat.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Chat / Channel ID:", self._telegram_chat))
        self._telegram_severity = _severity_combo("WARNING")
        self._telegram_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._telegram_severity))
        note = QLabel(
            "Create a bot via @BotFather on Telegram to get a token. "
            "Add the bot to a group/channel and get the chat ID via @getidsbot. "
            "The bot token is stored in the OS keychain; the chat ID is stored in settings."
        )
        note.setWordWrap(True)
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Message")
        btn_test.setFixedHeight(26)
        _s.themed_ss(btn_test, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            "border-radius:2px;padding:0 14px;font-size:11px;}}"
            "QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
        btn_test.clicked.connect(self._test_telegram)
        self._test_btns["telegram"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["telegram"] = _lbl
        bl.addWidget(_lbl)
        return card

    # ── Escalation card ───────────────────────────────────────────────────────

    def _build_escalation_card(self) -> QWidget:
        card, bl = _card("Alert Escalation")
        self._escalation_expand_btn = QPushButton("▶  Advanced: Escalation")
        self._escalation_expand_btn.setFlat(True)
        self._escalation_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(self._escalation_expand_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; font-weight:bold;"
            " background:transparent; border:none; padding:2px 0; text-align:left; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        bl.addWidget(self._escalation_expand_btn)

        self._escalation_body = QWidget()
        self._escalation_body.setVisible(False)
        body_lay = QVBoxLayout(self._escalation_body)
        body_lay.setContentsMargins(0, 6, 0, 0)
        body_lay.setSpacing(8)

        explainer = QLabel(
            "If this channel fails to deliver, NetSentinel will try the escalation channel instead."
        )
        _s.themed_ss(explainer, "font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        explainer.setWordWrap(True)
        body_lay.addWidget(explainer)

        flow_lbl = QLabel("[Primary]  →  fails  →  [Escalation]")
        _s.themed_ss(flow_lbl, "font-size:11px; color:{TEXT_MUTED}; font-style:italic; border:none; padding:2px 0;")
        body_lay.addWidget(flow_lbl)

        self._chk_escalation = QCheckBox("Enable escalation")
        _s.themed_ss(self._chk_escalation, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_escalation.stateChanged.connect(self._save)
        body_lay.addWidget(self._chk_escalation)

        wait_row = QHBoxLayout()
        wait_row.setSpacing(8)
        wait_lbl = QLabel("Escalate if unacknowledged for")
        _s.themed_ss(wait_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._spin_escalation_wait = QSpinBox()
        self._spin_escalation_wait.setRange(1, 1440)
        self._spin_escalation_wait.setValue(15)
        self._spin_escalation_wait.setSuffix(" min")
        self._spin_escalation_wait.setFixedWidth(_s.SPINBOX_WIDTH_WITH_SUFFIX)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(self._spin_escalation_wait, "font-size:11px; color:{TEXT_PRIMARY}; background:{BG_DARK};")
        _s.style_spinbox(self._spin_escalation_wait)
        self._spin_escalation_wait.valueChanged.connect(self._save)
        wait_row.addWidget(wait_lbl)
        wait_row.addWidget(self._spin_escalation_wait)
        wait_row.addStretch()
        body_lay.addLayout(wait_row)

        ch_row = QHBoxLayout()
        ch_row.setSpacing(8)
        ch_lbl = QLabel("Escalate via channel")
        _s.themed_ss(ch_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._combo_escalation_channel = QComboBox()
        self._combo_escalation_channel.addItems(["Email", "Webhook", "Pushover", "ntfy", "Telegram"])
        self._combo_escalation_channel.setFixedWidth(140)
        _s.themed_ss(self._combo_escalation_channel, "font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;")
        self._combo_escalation_channel.currentTextChanged.connect(self._save)
        ch_row.addWidget(ch_lbl)
        ch_row.addWidget(self._combo_escalation_channel)
        ch_row.addStretch()
        body_lay.addLayout(ch_row)

        rules_row = QHBoxLayout()
        rules_row.setSpacing(8)
        rules_lbl = QLabel("Watch rules (blank = all):")
        _s.themed_ss(rules_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._txt_escalation_rules = QLineEdit()
        self._txt_escalation_rules.setPlaceholderText(
            "Host Down, High RTT  (comma-separated, blank = all)"
        )
        _s.themed_ss(self._txt_escalation_rules, "font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;")
        self._txt_escalation_rules.editingFinished.connect(self._save)
        rules_row.addWidget(rules_lbl)
        rules_row.addWidget(self._txt_escalation_rules, 1)
        body_lay.addLayout(rules_row)

        bl.addWidget(self._escalation_body)
        self._escalation_expand_btn.clicked.connect(self._toggle_escalation_body)
        return card

    def _toggle_escalation_body(self) -> None:
        expanded = self._escalation_body.isVisible()
        self._escalation_body.setVisible(not expanded)
        arrow = "▼" if not expanded else "▶"
        self._escalation_expand_btn.setText(f"{arrow}  Advanced: Escalation")

    # ── Weekly digest card ────────────────────────────────────────────────────

    def _build_weekly_digest_card(self) -> QWidget:
        card, bl = _card("Weekly Digest")
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._chk_weekly_digest = QCheckBox("Send weekly summary every Sunday at")
        _s.themed_ss(self._chk_weekly_digest, "QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; }}"
            "QCheckBox::indicator {{ width:12px; height:12px;"
            " border:1px solid {BORDER}; border-radius:2px; background:{BG_CARD}; }}"
            "QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}")
        self._chk_weekly_digest.toggled.connect(self._save_digest_settings)
        self._combo_digest_time = QComboBox()
        for h in range(6, 23):
            self._combo_digest_time.addItem(f"{h:02d}:00")
        self._combo_digest_time.setCurrentText("09:00")
        self._combo_digest_time.setFixedWidth(80)
        _s.themed_ss(self._combo_digest_time, "QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 6px;font-size:11px;}}"
            "QComboBox::drop-down{{border:none;}}"
            "QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            "border:1px solid {BORDER};selection-background-color:{ACCENT};}}")
        self._combo_digest_time.currentTextChanged.connect(self._save_digest_settings)
        row1.addWidget(self._chk_weekly_digest)
        row1.addWidget(self._combo_digest_time)
        row1.addStretch()
        bl.addLayout(row1)

        hint = QLabel(
            "Includes: network grade, top alerts, new devices, new open ports, "
            "CVE matches, certificates expiring soon, and device uptime."
        )
        _s.themed_ss(hint, "color:{TEXT_MUTED}; font-size:10px; border:none;")
        bl.addWidget(hint)

        btn_gen = QPushButton("Generate now — copy to clipboard")
        btn_gen.setFixedHeight(26)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(btn_gen, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 12px;font-size:11px;}}"
            "QPushButton:hover{{border-color:{ACCENT};}}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}")
        btn_gen.clicked.connect(self._on_generate_digest)
        bl.addWidget(btn_gen)

        self._digest_status_lbl = QLabel("")
        _s.themed_ss(self._digest_status_lbl, "color:{GREEN}; font-size:10px; border:none; background:transparent;")
        self._digest_status_lbl.setVisible(False)
        bl.addWidget(self._digest_status_lbl)

        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_weekly_digest.setChecked(
            qs.value("notif/weekly_digest_enabled", False, type=bool)
        )
        t = qs.value("notif/weekly_digest_time", "09:00")
        idx = self._combo_digest_time.findText(t)
        if idx >= 0:
            self._combo_digest_time.setCurrentIndex(idx)
        return card

    def _save_digest_settings(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("notif/weekly_digest_enabled", self._chk_weekly_digest.isChecked())
        qs.setValue("notif/weekly_digest_time", self._combo_digest_time.currentText())

    def _on_generate_digest(self) -> None:
        text = self._generate_weekly_summary()
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        lbl = getattr(self, "_digest_status_lbl", None)
        if lbl:
            lbl.setText("✓ Copied to clipboard")
            lbl.setVisible(True)
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(lambda: lbl.setVisible(False))
            _t.start(3000)

    # ── Morning briefing card (S8-1) ──────────────────────────────────────────

    def _build_morning_briefing_card(self) -> QWidget:
        card, bl = _card("Morning Briefing")
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._chk_morning_briefing = QCheckBox("Send a daily briefing notification at")
        _s.themed_ss(self._chk_morning_briefing, "QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; }}"
            "QCheckBox::indicator {{ width:12px; height:12px;"
            " border:1px solid {BORDER}; border-radius:2px; background:{BG_CARD}; }}"
            "QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}")
        self._chk_morning_briefing.toggled.connect(self._save_morning_briefing_settings)
        self._spin_briefing_hour = QSpinBox()
        self._spin_briefing_hour.setRange(0, 23)
        self._spin_briefing_hour.setValue(8)
        self._spin_briefing_hour.setSuffix(":00")
        self._spin_briefing_hour.setFixedWidth(_s.SPINBOX_WIDTH_WITH_SUFFIX)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(self._spin_briefing_hour, "font-size:11px; color:{TEXT_PRIMARY}; background:{BG_DARK};")
        _s.style_spinbox(self._spin_briefing_hour)
        self._spin_briefing_hour.valueChanged.connect(self._save_morning_briefing_settings)
        row1.addWidget(self._chk_morning_briefing)
        row1.addWidget(self._spin_briefing_hour)
        row1.addStretch()
        bl.addLayout(row1)

        hint = QLabel(
            "A 3-bullet tray notification: network status, what changed overnight, "
            "and your last speed test result. Disabled by default."
        )
        hint.setWordWrap(True)
        _s.themed_ss(hint, "color:{TEXT_MUTED}; font-size:10px; border:none;")
        bl.addWidget(hint)

        extra_hint = QLabel(
            "If Service Down alerts or Automatic Speed Tests are enabled above, the "
            "briefing also summarizes overnight service outages and speed drops."
        )
        extra_hint.setWordWrap(True)
        _s.themed_ss(extra_hint, "color:{TEXT_MUTED}; font-size:10px; border:none;")
        bl.addWidget(extra_hint)

        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_morning_briefing.setChecked(
            qs.value("briefing/enabled", False, type=bool)
        )
        self._spin_briefing_hour.setValue(int(qs.value("briefing/hour", 8)))
        return card

    def _save_morning_briefing_settings(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("briefing/enabled", self._chk_morning_briefing.isChecked())
        qs.setValue("briefing/hour", self._spin_briefing_hour.value())

    def _generate_weekly_summary(self) -> str:
        import datetime as _dt2
        now = _dt2.datetime.now()
        week_ago = now - _dt2.timedelta(days=7)
        lines = [
            f"NetSentinel Weekly Summary — {now.strftime('%A %d %B %Y')}",
            f"Period: {week_ago.strftime('%d %b')} – {now.strftime('%d %b %Y')}",
            "",
        ]
        if self._store:
            try:
                alerts = self._store.get_recent_alerts(hours=168)
                lines.append(f"Alerts fired:        {len(alerts)}")
            except Exception:
                lines.append("Alerts fired:        —")
            try:
                devices = self._store.get_known_devices()
                lines.append(f"Known devices:       {len(devices)}")
            except Exception:
                lines.append("Known devices:       —")
            try:
                grade = self._store.query_last_grade()
                if grade:
                    lines.append(
                        f"Network grade:       {grade.get('grade', '—')} "
                        f" ({grade.get('score', '—'):.0f}/100)"
                    )
            except Exception:
                pass  # non-fatal
        else:
            lines.append("(Store not available — open the app to generate live data)")
        lines += ["", "Generated by NetSentinel"]
        return "\n".join(lines)


"""
notif_channel_panels.py — mixin helpers for NotificationsPage.

Extracted from notifications_page.py (S14-3a) to keep that file within a
manageable size.  This module provides:

  • Module-level helpers:  _save_secret, _load_secret, _page_header,
                           _card, _field_row, _lineedit, _severity_combo
  • Constants:  keyring keys, rule definitions
  • _NotifChannelsMixin:  keychain field helpers, alert-rules card,
                          Toast/Webhook/Email card builders, and channel
                          test helper methods

Pushover/Ntfy/Telegram/Escalation/Weekly-Digest card builders live in
notif_extra_channels.py (_NotifExtraChannelsMixin).

Alert history table and delivery-log panel live in
notif_alert_history.py (_NotifAlertHistoryMixin).

Usage in notifications_page.py:

    from ui.pages.notif_channel_panels import _NotifChannelsMixin, ...
    from ui.pages.notif_extra_channels import _NotifExtraChannelsMixin
    from ui.pages.notif_alert_history  import _NotifAlertHistoryMixin
    class NotificationsPage(
        _NotifAlertHistoryMixin, _NotifExtraChannelsMixin,
        _NotifChannelsMixin, QWidget,
    ): ...
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG,
    BG_CARD, BG_HOVER,
    BORDER, CARD_HDR_BORDER, CARD_RADIUS,
    GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)

# ── Keyring constants (exported so notifications_page.py can import them) ─────

_KR_SERVICE            = "NetSentinel"
_KR_EMAIL_PASS_KEY     = "notif/email_pass"
_KR_PUSHOVER_TOKEN_KEY = "notif/pushover_token"
_KR_PUSHOVER_USER_KEY  = "notif/pushover_user"
_KR_NTFY_TOKEN_KEY     = "notif/ntfy_token"
_KR_TELEGRAM_TOKEN_KEY = "notif/telegram_token"

try:
    import keyring as _keyring
    _KEYRING_OK = True
except ImportError:
    _keyring = None  # type: ignore
    _KEYRING_OK = False


def _save_secret(key: str, value: str) -> None:
    if _KEYRING_OK and value:
        _keyring.set_password(_KR_SERVICE, key, value)
    elif _KEYRING_OK and not value:
        try:
            _keyring.delete_password(_KR_SERVICE, key)
        except Exception:
            pass


def _load_secret(key: str) -> str:
    if not _KEYRING_OK:
        return ""
    try:
        return _keyring.get_password(_KR_SERVICE, key) or ""
    except Exception:
        return ""


# ── Shared widget helpers ─────────────────────────────────────────────────────

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


def _card(title: str) -> "tuple[QFrame, QVBoxLayout]":
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:{CARD_RADIUS};}}"
    )
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    tb = QFrame()
    tb.setFixedHeight(32)
    tb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)
    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(8)
    cl.addWidget(body)
    return card, bl


def _field_row(label: str, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(10)
    lbl = QLabel(label)
    lbl.setFixedWidth(160)
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


def _lineedit(placeholder: str = "", password: bool = False) -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    le.setFixedHeight(26)
    if password:
        le.setEchoMode(QLineEdit.EchoMode.Password)
    le.setStyleSheet(
        f"QLineEdit{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
        f"border-radius:2px;padding:0 6px;font-size:11px;}}"
        f"QLineEdit:focus{{border-color:{ACCENT};}}"
    )
    return le


def _severity_combo(default: str = "WARNING") -> QComboBox:
    cb = QComboBox()
    for lvl in ("INFO", "WARNING", "CRITICAL"):
        cb.addItem(lvl)
    cb.setCurrentText(default)
    cb.setFixedHeight(26)
    cb.setStyleSheet(
        f"QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
        f"border-radius:2px;padding:0 6px;font-size:11px;}}"
        f"QComboBox::drop-down{{border:none;}}"
        f"QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
        f"border:1px solid {BORDER};selection-background-color:{ACCENT};}}"
    )
    return cb


# ── Constants ─────────────────────────────────────────────────────────────────

_RECOMMENDED_RULES = {"Host Down", "New Device", "High RTT", "Cert Expiring", "Host Flapping"}

_ALERT_RULE_DEFS = [
    ("High RTT",      "RTT_THRESHOLD",  "Fires when a host's round-trip time exceeds the threshold"),
    ("Host Down",     "HOST_DOWN",      "Fires when a monitored host becomes unreachable"),
    ("Host Degraded", "HOST_DEGRADED",  "Fires when a host responds slowly or intermittently"),
    ("New Device",    "NEW_DEVICE",     "Fires when a device with a new MAC address is seen on the network"),
    ("Device Gone",   "DEVICE_GONE",    "Fires when a known device has not been seen recently"),
    ("Cert Expiring", "CERT_EXPIRY",    "Fires when a TLS certificate is within the expiry threshold"),
    ("Cert Expired",  "CERT_EXPIRED",   "Fires when a TLS certificate has already expired"),
    ("Host Flapping", "FLAP",           "Fires when a host oscillates between UP and DOWN repeatedly"),
    ("Service Down",  "SERVICE_DOWN",   "Fires when a monitored TCP service stops responding"),
]


# ── Mixin — keychain helpers, alert-rules card, core channel cards, test helpers

class _NotifChannelsMixin:
    """Pure-Python mixin.  NotificationsPage inherits this alongside QWidget.

    All methods reference ``self`` which will be the NotificationsPage instance
    at runtime.  No __init__ needed — state is set up by NotificationsPage.
    """

    # ── Keychain field helpers ────────────────────────────────────────────────

    def _kr_note_row(self, kr_key: str, field: QLineEdit) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        note = QLabel("Stored securely in your OS keychain — not in any config file")
        note.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
        )
        row.addWidget(note)
        change_btn = QPushButton("Change ›")
        change_btn.setFixedHeight(18)
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:10px; padding:0; }}"
            f"QPushButton:hover {{ text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        change_btn.setVisible(False)
        change_btn.clicked.connect(
            lambda _=False, k=kr_key, f=field, b=change_btn:
            self._unlock_kr_field(k, f, b)
        )
        row.addWidget(change_btn)
        row.addStretch()
        self._kr_change_btns[kr_key] = change_btn
        return w

    def _unlock_kr_field(self, kr_key: str, field: QLineEdit, btn: QPushButton) -> None:
        self._kr_locked.pop(kr_key, None)
        field.setPlaceholderText("")
        btn.setVisible(False)
        field.setFocus()

    def _kr_restore_field(self, kr_key: str, field: QLineEdit) -> None:
        val = _load_secret(kr_key)
        if val:
            field.clear()
            field.setPlaceholderText("●●●●●●●●")
            self._kr_locked[kr_key] = field
            if kr_key in self._kr_change_btns:
                self._kr_change_btns[kr_key].setVisible(True)
        else:
            field.clear()
            field.setPlaceholderText("")
            self._kr_locked.pop(kr_key, None)
            if kr_key in self._kr_change_btns:
                self._kr_change_btns[kr_key].setVisible(False)

    def _kr_save_field(self, kr_key: str, field: QLineEdit) -> None:
        if kr_key in self._kr_locked and not field.text():
            return
        _save_secret(kr_key, field.text())
        self._kr_locked.pop(kr_key, None)

    # ── Alert rules card ──────────────────────────────────────────────────────

    def _build_alert_rules_card(self) -> QWidget:
        card, bl = _card("Alert Rules")
        self._active_rules_lbl = QLabel("0 rules active")
        self._active_rules_lbl.setStyleSheet(
            f"font-size:11px; color:{AMBER}; font-weight:bold; border:none;"
        )
        bl.addWidget(self._active_rules_lbl)
        info = QLabel(
            "All alert rules are disabled by default — you must opt in. "
            "Enable the rules you want; alerts only fire for rules that are active."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none; padding-bottom:4px;"
        )
        bl.addWidget(info)

        self._zero_rules_banner = QFrame()
        self._zero_rules_banner.setStyleSheet(
            f"QFrame {{ background:{AMBER_BG}; border:1px solid {AMBER}; border-radius:4px; }}"
        )
        banner_lay = QHBoxLayout(self._zero_rules_banner)
        banner_lay.setContentsMargins(10, 6, 10, 6)
        banner_lay.setSpacing(10)
        banner_txt = QLabel(
            "No alert rules are active — you won't receive any alerts."
        )
        banner_txt.setStyleSheet(
            f"color:{AMBER}; font-size:11px; border:none; background:transparent;"
        )
        banner_lay.addWidget(banner_txt, 1)
        rec_btn = QPushButton("Enable recommended rules →")
        rec_btn.setFlat(True)
        rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rec_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        rec_btn.clicked.connect(self._enable_recommended_rules)
        banner_lay.addWidget(rec_btn)
        self._zero_rules_banner.setVisible(False)
        bl.addWidget(self._zero_rules_banner)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for row_idx, (name, _rule_type, description) in enumerate(_ALERT_RULE_DEFS):
            chk = QCheckBox(name)
            chk.setFixedWidth(140)
            chk.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
            chk.stateChanged.connect(self._save)
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY}; border:none;")
            grid.addWidget(chk, row_idx, 0)
            grid.addWidget(desc_lbl, row_idx, 1)
            self._rule_checkboxes[name] = chk
        bl.addLayout(grid)
        return card

    def _update_rules_badge(self) -> None:
        count = sum(1 for chk in self._rule_checkboxes.values() if chk.isChecked())
        lbl    = getattr(self, "_active_rules_lbl", None)
        banner = getattr(self, "_zero_rules_banner", None)
        if lbl is None:
            return
        noun = "rule" if count == 1 else "rules"
        lbl.setText(f"{count} {noun} active")
        if count == 0:
            lbl.setStyleSheet(f"font-size:11px; color:{AMBER}; font-weight:bold; border:none;")
            if banner:
                banner.setVisible(True)
        else:
            lbl.setStyleSheet(f"font-size:11px; color:{GREEN}; font-weight:bold; border:none;")
            if banner:
                banner.setVisible(False)

    def _enable_recommended_rules(self) -> None:
        for name, chk in self._rule_checkboxes.items():
            if name in _RECOMMENDED_RULES:
                chk.setChecked(True)
        self._save()

    # ── Channel cards ─────────────────────────────────────────────────────────

    def _build_toast_card(self) -> QWidget:
        card, bl = _card("Desktop Notification (Toast)")
        self._chk_toast = QCheckBox("Enable desktop toast notifications")
        self._chk_toast.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_toast.stateChanged.connect(self._save)
        bl.addWidget(self._chk_toast)
        self._toast_severity = _severity_combo("WARNING")
        self._toast_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._toast_severity))
        note = QLabel(
            "Toast notifications appear in the system tray area. "
            "Requires NetSentinel to be running."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        return card

    def _build_webhook_card(self) -> QWidget:
        card, bl = _card("Webhook (Slack / Teams / Generic HTTP POST)")
        self._chk_webhook = QCheckBox("Enable webhook")
        self._chk_webhook.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_webhook.stateChanged.connect(self._save)
        bl.addWidget(self._chk_webhook)
        self._webhook_url = _lineedit("https://hooks.slack.com/services/…")
        self._webhook_url.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Webhook URL:", self._webhook_url))
        self._webhook_severity = _severity_combo("CRITICAL")
        self._webhook_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._webhook_severity))
        note = QLabel(
            "Sends a JSON POST to the URL on each matching alert. "
            "Compatible with Slack Incoming Webhooks, Microsoft Teams connectors, "
            "and any HTTP endpoint that accepts JSON."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Alert")
        btn_test.setFixedHeight(26)
        btn_test.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:2px;padding:0 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
        )
        btn_test.clicked.connect(self._test_webhook)
        self._test_btns["webhook"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["webhook"] = _lbl
        bl.addWidget(_lbl)
        return card

    def _build_email_card(self) -> QWidget:
        card, bl = _card("Email Alert (SMTP)")
        self._chk_email = QCheckBox("Enable email alerts")
        self._chk_email.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_email.stateChanged.connect(self._save)
        bl.addWidget(self._chk_email)
        self._email_host = _lineedit("smtp.gmail.com")
        self._email_host.editingFinished.connect(self._save)
        bl.addLayout(_field_row("SMTP host:", self._email_host))
        self._email_port = _lineedit("587")
        self._email_port.editingFinished.connect(self._save)
        bl.addLayout(_field_row("SMTP port:", self._email_port))
        self._email_user = _lineedit("you@example.com")
        self._email_user.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Username:", self._email_user))
        self._email_pass = _lineedit("App password", password=True)
        self._email_pass.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Password:", self._email_pass))
        bl.addWidget(self._kr_note_row(_KR_EMAIL_PASS_KEY, self._email_pass))
        self._email_from = _lineedit("netsentinel@example.com")
        self._email_from.editingFinished.connect(self._save)
        bl.addLayout(_field_row("From address:", self._email_from))
        self._email_to = _lineedit("admin@example.com, ops@example.com")
        self._email_to.editingFinished.connect(self._save)
        bl.addLayout(_field_row("To addresses:", self._email_to))
        self._email_severity = _severity_combo("CRITICAL")
        self._email_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._email_severity))
        note = QLabel(
            "Uses STARTTLS on port 587 (or SSL on port 465 — change port to switch). "
            "For Gmail, create an App Password in Google Account settings."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Email")
        btn_test.setFixedHeight(26)
        btn_test.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:2px;padding:0 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
        )
        btn_test.clicked.connect(self._test_email)
        self._test_btns["email"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["email"] = _lbl
        bl.addWidget(_lbl)
        return card

    # ── Channel test helpers ──────────────────────────────────────────────────

    def _run_test(self, key: str, deliver_fn, ch, alert) -> None:
        lbl = self._test_labels.get(key)
        btn = self._test_btns.get(key)
        if lbl:
            lbl.setTextFormat(Qt.TextFormat.PlainText)
            lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
            )
            lbl.setText("Testing…")
            lbl.setVisible(True)
        if btn:
            btn.setEnabled(False)

        def _worker() -> None:
            try:
                deliver_fn(ch, alert)
                html = (
                    f'<span style="color:{GREEN};">'
                    f"✓ Sent — check your channel for a test alert.</span>"
                )
                self._test_done.emit(key, html)
                t = threading.Timer(5.0, lambda: self._test_done.emit(key, ""))
                t.daemon = True
                t.start()
            except Exception as exc:
                err = f"{type(exc).__name__}: {str(exc)[:120]}"
                html = f'<span style="color:{RED};">✗ {err}</span>'
                self._test_done.emit(key, html)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_done(self, key: str, html: str) -> None:
        lbl = self._test_labels.get(key)
        btn = self._test_btns.get(key)
        if btn:
            btn.setEnabled(True)
        if lbl:
            if html:
                lbl.setTextFormat(Qt.TextFormat.RichText)
                lbl.setText(html)
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

    def _test_webhook(self) -> None:
        from modules.notification_router import WebhookChannel, _deliver_webhook
        from modules.alert_engine import AlertFired
        import time as _t
        url = self._webhook_url.text().strip()
        if not url:
            return
        ch = WebhookChannel(enabled=True, url=url,
                            min_severity=self._webhook_severity.currentText())
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test", message="This is a test alert from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        self._run_test("webhook", _deliver_webhook, ch, alert)

    def _test_email(self) -> None:
        from modules.notification_router import EmailChannel, _deliver_email
        from modules.alert_engine import AlertFired
        import time as _t
        try:
            port = int(self._email_port.text().strip() or "587")
        except ValueError:
            port = 587
        to_addrs = [a.strip() for a in self._email_to.text().split(",") if a.strip()]
        ch = EmailChannel(
            enabled=True,
            smtp_host=self._email_host.text().strip(),
            smtp_port=port,
            use_tls=port != 465,
            username=self._email_user.text().strip(),
            password=self._email_pass.text(),
            from_addr=self._email_from.text().strip(),
            to_addrs=to_addrs,
            min_severity=self._email_severity.currentText(),
        )
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test", message="This is a test alert from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        self._run_test("email", _deliver_email, ch, alert)

    def _test_pushover(self) -> None:
        from modules.notification_router import PushoverChannel, _deliver_pushover
        from modules.alert_engine import AlertFired
        import time as _t
        ch = PushoverChannel(
            enabled=True,
            api_token=self._pushover_token.text(),
            user_key=self._pushover_user.text(),
            min_severity=self._pushover_severity.currentText(),
        )
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test", message="This is a test push from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        self._run_test("pushover", _deliver_pushover, ch, alert)

    def _test_ntfy(self) -> None:
        from modules.notification_router import NtfyChannel, _deliver_ntfy
        from modules.alert_engine import AlertFired
        import time as _t
        ch = NtfyChannel(
            enabled=True,
            topic_url=self._ntfy_url.text().strip(),
            access_token=self._ntfy_token.text(),
            min_severity=self._ntfy_severity.currentText(),
        )
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test",
            message="This is a test notification from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        self._run_test("ntfy", _deliver_ntfy, ch, alert)

    def _test_telegram(self) -> None:
        from modules.notification_router import TelegramChannel, _deliver_telegram
        from modules.alert_engine import AlertFired
        import time as _t
        ch = TelegramChannel(
            enabled=True,
            bot_token=self._telegram_token.text(),
            chat_id=self._telegram_chat.text().strip(),
            min_severity=self._telegram_severity.currentText(),
        )
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test", message="This is a test message from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        self._run_test("telegram", _deliver_telegram, ch, alert)

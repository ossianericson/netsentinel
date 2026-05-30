"""
NotificationsPage — notification routing configuration and delivery log.

Card builders, log panel, and channel test helpers live in
notif_channel_panels.py (S14-3a split).  This module owns only the core
state (router/engine/store injection), save/restore, and the apply-to-live
methods.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.styles import BG_DARK, BG_HOVER, BORDER
from modules.alert_engine import rule_settings_key as _rule_key
from ui.widgets.alert_drawer import AlertDrawer
from ui.widgets.skeleton import insert_skeleton_rows

from ui.pages.notif_channel_panels import (
    _NotifChannelsMixin,
    _KR_EMAIL_PASS_KEY,
    _KR_PUSHOVER_TOKEN_KEY,
    _KR_PUSHOVER_USER_KEY,
    _KR_NTFY_TOKEN_KEY,
    _KR_TELEGRAM_TOKEN_KEY,
    _save_secret,
    _ALERT_RULE_DEFS,
    _page_header,
)


class NotificationsPage(_NotifChannelsMixin, QWidget):
    """Notification routing configuration and delivery log page."""

    navigate_to              = pyqtSignal(str)
    view_in_log_hub          = pyqtSignal(float, str)
    automation_rule_requested = pyqtSignal(str, str)
    select_inventory_device  = pyqtSignal(str)
    alert_acknowledged       = pyqtSignal()
    _test_done               = pyqtSignal(str, str)

    def __init__(self, router=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._router = router
        self._store  = None
        self._alert_engine = None
        self._rule_checkboxes: dict = {}
        self._test_labels:     dict = {}
        self._test_btns:       dict = {}
        self._kr_locked:       dict = {}
        self._kr_change_btns:  dict = {}
        self._test_done.connect(self._on_test_done)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(_page_header(
            "Notification Routing",
            "Route alerts to desktop notifications, webhooks, or email by severity",
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)

        il.addWidget(self._build_alert_rules_card())
        il.addWidget(self._build_toast_card())
        il.addWidget(self._build_webhook_card())
        il.addWidget(self._build_email_card())
        il.addWidget(self._build_pushover_card())
        il.addWidget(self._build_ntfy_card())
        il.addWidget(self._build_telegram_card())
        il.addWidget(self._build_escalation_card())
        il.addWidget(self._build_weekly_digest_card())
        il.addWidget(self._build_log_card())
        il.addStretch()

        scroll.setWidget(inner)

        self._alert_drawer = AlertDrawer(self)
        self._alert_drawer.acknowledged.connect(self._on_drawer_acknowledged)
        self._alert_drawer.navigate_to.connect(self.navigate_to)
        self._alert_drawer.view_in_log_hub.connect(self.view_in_log_hub)

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(scroll, 1)
        body_row.addWidget(self._alert_drawer)
        outer.addLayout(body_row, 1)

        self._restore()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        if getattr(self, "_restoring", False):
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("notif/toast_enabled",    self._chk_toast.isChecked())
        qs.setValue("notif/toast_severity",   self._toast_severity.currentText())
        qs.setValue("notif/webhook_enabled",  self._chk_webhook.isChecked())
        qs.setValue("notif/webhook_url",      self._webhook_url.text().strip())
        qs.setValue("notif/webhook_severity", self._webhook_severity.currentText())
        qs.setValue("notif/email_enabled",    self._chk_email.isChecked())
        qs.setValue("notif/email_host",       self._email_host.text().strip())
        qs.setValue("notif/email_port",       self._email_port.text().strip())
        qs.setValue("notif/email_user",       self._email_user.text().strip())
        self._kr_save_field(_KR_EMAIL_PASS_KEY, self._email_pass)
        qs.setValue("notif/email_from",       self._email_from.text().strip())
        qs.setValue("notif/email_to",         self._email_to.text().strip())
        qs.setValue("notif/email_severity",   self._email_severity.currentText())
        qs.setValue("notif/pushover_enabled",  self._chk_pushover.isChecked())
        qs.setValue("notif/pushover_severity", self._pushover_severity.currentText())
        self._kr_save_field(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token)
        self._kr_save_field(_KR_PUSHOVER_USER_KEY,  self._pushover_user)
        qs.setValue("notif/ntfy_enabled",    self._chk_ntfy.isChecked())
        qs.setValue("notif/ntfy_url",        self._ntfy_url.text().strip())
        qs.setValue("notif/ntfy_severity",   self._ntfy_severity.currentText())
        self._kr_save_field(_KR_NTFY_TOKEN_KEY, self._ntfy_token)
        qs.setValue("notif/telegram_enabled",  self._chk_telegram.isChecked())
        qs.setValue("notif/telegram_chat",     self._telegram_chat.text().strip())
        qs.setValue("notif/telegram_severity", self._telegram_severity.currentText())
        self._kr_save_field(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token)
        qs.setValue("notif/escalation_enabled",  self._chk_escalation.isChecked())
        qs.setValue("notif/escalation_wait",     self._spin_escalation_wait.value())
        qs.setValue("notif/escalation_channel",  self._combo_escalation_channel.currentText())
        qs.setValue("notif/escalation_rules",    self._txt_escalation_rules.text().strip())
        any_rule_on = False
        for name, chk in self._rule_checkboxes.items():
            qs.setValue(_rule_key(name), chk.isChecked())
            if chk.isChecked():
                any_rule_on = True
        qs.setValue("notif/any_rule_enabled", any_rule_on)
        self._update_rules_badge()
        self._apply_to_engine()
        self._apply_to_router()

    def _restore(self) -> None:
        self._restoring = True
        try:
            qs = QSettings("NetSentinel", "NetSentinel")
            self._chk_toast.setChecked(qs.value("notif/toast_enabled",    False, type=bool))
            self._toast_severity.setCurrentText(qs.value("notif/toast_severity", "WARNING"))
            self._chk_webhook.setChecked(qs.value("notif/webhook_enabled", False, type=bool))
            self._webhook_url.setText(qs.value("notif/webhook_url",        ""))
            self._webhook_severity.setCurrentText(qs.value("notif/webhook_severity", "CRITICAL"))
            self._chk_email.setChecked(qs.value("notif/email_enabled",     False, type=bool))
            self._email_host.setText(qs.value("notif/email_host",          ""))
            self._email_port.setText(qs.value("notif/email_port",          "587"))
            self._email_user.setText(qs.value("notif/email_user",          ""))
            self._kr_restore_field(_KR_EMAIL_PASS_KEY, self._email_pass)
            self._email_from.setText(qs.value("notif/email_from",          ""))
            self._email_to.setText(qs.value("notif/email_to",              ""))
            self._email_severity.setCurrentText(qs.value("notif/email_severity", "CRITICAL"))
            legacy = qs.value("notif/email_pass", "")
            if legacy:
                _save_secret(_KR_EMAIL_PASS_KEY, legacy)
                qs.remove("notif/email_pass")
                self._kr_restore_field(_KR_EMAIL_PASS_KEY, self._email_pass)
            self._chk_pushover.setChecked(qs.value("notif/pushover_enabled", False, type=bool))
            self._pushover_severity.setCurrentText(qs.value("notif/pushover_severity", "WARNING"))
            self._kr_restore_field(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token)
            self._kr_restore_field(_KR_PUSHOVER_USER_KEY,  self._pushover_user)
            self._chk_ntfy.setChecked(qs.value("notif/ntfy_enabled", False, type=bool))
            self._ntfy_url.setText(qs.value("notif/ntfy_url", ""))
            self._ntfy_severity.setCurrentText(qs.value("notif/ntfy_severity", "WARNING"))
            self._kr_restore_field(_KR_NTFY_TOKEN_KEY, self._ntfy_token)
            self._chk_telegram.setChecked(qs.value("notif/telegram_enabled", False, type=bool))
            self._telegram_chat.setText(qs.value("notif/telegram_chat", ""))
            self._telegram_severity.setCurrentText(qs.value("notif/telegram_severity", "WARNING"))
            self._kr_restore_field(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token)
            self._chk_escalation.setChecked(qs.value("notif/escalation_enabled", False, type=bool))
            self._spin_escalation_wait.setValue(int(qs.value("notif/escalation_wait", 15)))
            ch = qs.value("notif/escalation_channel", "Email")
            idx = self._combo_escalation_channel.findText(ch)
            if idx >= 0:
                self._combo_escalation_channel.setCurrentIndex(idx)
            self._txt_escalation_rules.setText(qs.value("notif/escalation_rules", ""))
            for name, chk in self._rule_checkboxes.items():
                chk.setChecked(qs.value(_rule_key(name), False, type=bool))
        finally:
            self._restoring = False
        self._apply_to_router()
        self._update_rules_badge()

    # ── Live object injection ─────────────────────────────────────────────────

    def set_router(self, router) -> None:
        self._router = router
        self._apply_to_router()
        if hasattr(self, "_alert_drawer"):
            self._alert_drawer.set_router(router)

    def set_alert_engine(self, engine) -> None:
        self._alert_engine = engine
        self._apply_to_engine()

    def set_store(self, store) -> None:
        self._store = store
        if hasattr(self, "_alert_drawer"):
            self._alert_drawer.set_store(store)

    def set_global_hours(self, hours: float) -> None:
        self._hist_hours = hours
        self._refresh_alert_history()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._alert_history_table.rowCount() == 0:
            insert_skeleton_rows(self._alert_history_table, count=4)

    # ── Apply to live objects ─────────────────────────────────────────────────

    def _apply_to_router(self) -> None:
        if self._router is None:
            return
        from modules.notification_router import (
            ToastChannel, WebhookChannel, EmailChannel,
            PushoverChannel, NtfyChannel, TelegramChannel,
        )
        channels = []
        channels.append(ToastChannel(
            enabled=self._chk_toast.isChecked(),
            min_severity=self._toast_severity.currentText(),
        ))
        url = self._webhook_url.text().strip()
        channels.append(WebhookChannel(
            enabled=self._chk_webhook.isChecked() and bool(url),
            url=url,
            min_severity=self._webhook_severity.currentText(),
        ))
        try:
            port = int(self._email_port.text().strip() or "587")
        except ValueError:
            port = 587
        to_addrs = [a.strip() for a in self._email_to.text().split(",") if a.strip()]
        channels.append(EmailChannel(
            enabled=self._chk_email.isChecked() and bool(self._email_host.text().strip()),
            smtp_host=self._email_host.text().strip(),
            smtp_port=port,
            use_tls=port != 465,
            username=self._email_user.text().strip(),
            password=self._email_pass.text(),
            from_addr=self._email_from.text().strip(),
            to_addrs=to_addrs,
            min_severity=self._email_severity.currentText(),
        ))
        channels.append(PushoverChannel(
            enabled=self._chk_pushover.isChecked()
                    and bool(self._pushover_token.text())
                    and bool(self._pushover_user.text()),
            api_token=self._pushover_token.text(),
            user_key=self._pushover_user.text(),
            min_severity=self._pushover_severity.currentText(),
        ))
        channels.append(NtfyChannel(
            enabled=self._chk_ntfy.isChecked() and bool(self._ntfy_url.text().strip()),
            topic_url=self._ntfy_url.text().strip(),
            access_token=self._ntfy_token.text(),
            min_severity=self._ntfy_severity.currentText(),
        ))
        channels.append(TelegramChannel(
            enabled=self._chk_telegram.isChecked()
                    and bool(self._telegram_token.text())
                    and bool(self._telegram_chat.text().strip()),
            bot_token=self._telegram_token.text(),
            chat_id=self._telegram_chat.text().strip(),
            min_severity=self._telegram_severity.currentText(),
        ))
        self._router.set_channels(channels)

    def _apply_to_engine(self) -> None:
        if self._alert_engine is None:
            return
        rules = self._alert_engine.get_rules()
        for rule in rules:
            chk = self._rule_checkboxes.get(rule.name)
            if chk is not None:
                rule.enabled = chk.isChecked()
        self._alert_engine.set_rules(rules)

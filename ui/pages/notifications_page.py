"""
NotificationsPage — notification routing configuration and delivery log.

Card builders, log panel, and channel test helpers live in
notif_channel_panels.py (S14-3a split).  This module owns only the core
state (router/engine/store injection), save/restore, and the apply-to-live
methods.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _s
from modules.alert_suppressor import (
    default_enabled as _rule_default,
    rule_settings_key as _rule_key,
)
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
    _page_header,
    _ALERT_RULE_DEFS,  # noqa: F401 — re-exported for test imports
)
from ui.pages.notif_extra_channels import _NotifExtraChannelsMixin
from ui.pages.notif_alert_history import _NotifAlertHistoryMixin
from ui.pages.notif_dep_card import _NotifDepMixin
from ui.pages.notif_routing_matrix import _NotifRoutingMatrixMixin


class NotificationsPage(
    _NotifDepMixin, _NotifAlertHistoryMixin, _NotifExtraChannelsMixin,
    _NotifRoutingMatrixMixin, _NotifChannelsMixin, QWidget
):
    """Notification routing configuration and delivery log page."""

    navigate_to              = pyqtSignal(str)
    view_in_log_hub          = pyqtSignal(float, str)
    automation_rule_requested = pyqtSignal(str, str)
    select_inventory_device  = pyqtSignal(str)
    alert_acknowledged       = pyqtSignal()
    notify_dep_changed       = pyqtSignal(str, list)  # (parent_ip, children_list)
    _test_done               = pyqtSignal(str, str)

    def __init__(self, router=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._router = router
        self._store  = None
        from ui.device_labels import DeviceLabelResolver
        self._resolver = DeviceLabelResolver(store=None)
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

        # ── Primary tabs: Configure / Alert History ───────────────────────────
        _tab_qss = (
            "QTabWidget::pane {{ border:none; }}"
            "QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            " border-bottom:none; padding:5px 18px; font-size:11px; font-weight:600; }}"
            "QTabBar::tab:selected {{ color:{TEXT_PRIMARY}; border-bottom:2px solid {ACCENT}; }}"
            "QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._notif_tabs = QTabWidget()
        _s.themed_ss(self._notif_tabs, _tab_qss)
        self._notif_tabs.currentChanged.connect(self._on_notif_tab_changed)

        # Tab 0 — Configure: all channel and rule cards
        _cfg_widget = QWidget()
        _s.themed_ss(_cfg_widget, "background:{BG_DARK};")
        _cfg_layout = QVBoxLayout(_cfg_widget)
        _cfg_layout.setContentsMargins(0, 0, 0, 0)
        _cfg_layout.setSpacing(0)

        self._notif_scroll = QScrollArea()
        self._notif_scroll.setWidgetResizable(True)
        self._notif_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._notif_scroll.setStyleSheet("background:transparent;")

        inner = QWidget()
        _s.themed_ss(inner, "background:{BG_DARK};")
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
        il.addWidget(self._build_routing_matrix_card())
        il.addWidget(self._build_morning_briefing_card())
        il.addWidget(self._build_weekly_digest_card())
        il.addWidget(self._build_dep_card())
        il.addStretch()

        self._notif_scroll.setWidget(inner)
        _cfg_layout.addWidget(self._notif_scroll, 1)
        self._notif_tabs.addTab(_cfg_widget, "Configure")

        # Tab 1 — Alert History: history table + delivery log
        _hist_widget = QWidget()
        _s.themed_ss(_hist_widget, "background:{BG_DARK};")
        _hist_layout = QVBoxLayout(_hist_widget)
        _hist_layout.setContentsMargins(16, 12, 16, 12)
        _hist_layout.setSpacing(0)
        _hist_layout.addWidget(self._build_log_card(), 1)
        self._notif_tabs.addTab(_hist_widget, "Alert History")

        self._alert_drawer = AlertDrawer(self)
        self._alert_drawer.acknowledged.connect(self._on_drawer_acknowledged)
        self._alert_drawer.navigate_to.connect(self.navigate_to)
        self._alert_drawer.view_in_log_hub.connect(self.view_in_log_hub)

        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)
        body_row.addWidget(self._notif_tabs, 1)
        body_row.addWidget(self._alert_drawer)
        outer.addLayout(body_row, 1)

        self._restore()

    # ── Tab management ────────────────────────────────────────────────────────

    def _on_notif_tab_changed(self, idx: int) -> None:
        if idx == 1:
            self._refresh_alert_history()
            self.refresh_log()

    def switch_to_history_tab(self, unacked_only: bool = False) -> None:
        """Navigate directly to the Alert History tab (called by external signals).

        unacked_only=True also checks the "Unacknowledged only" filter, so an
        alert older than any selectable window is reachable from a single call
        (e.g. Home's "View all alerts" / the status-bar alert indicator)."""
        self._notif_tabs.setCurrentIndex(1)
        if unacked_only:
            self._chk_unacked_only.setChecked(True)

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
        qs.setValue("notif/service_escalation_enabled", self._chk_service_escalation.isChecked())
        self._save_routing_matrix()
        for name, chk in self._rule_checkboxes.items():
            qs.setValue(_rule_key(name), chk.isChecked())
        qs.setValue("alerts/sensitivity", self._combo_sensitivity.currentData())
        qs.setValue("alerts/ack_hold_hours", int(self._combo_ack_hold.currentData()))
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
            self._chk_service_escalation.setChecked(
                qs.value("notif/service_escalation_enabled", True, type=bool)
            )
            for name, chk in self._rule_checkboxes.items():
                chk.setChecked(
                    qs.value(_rule_key(name), _rule_default(name), type=bool)
                )
            from modules.alert_sensitivity import DEFAULT_SENSITIVITY
            level = qs.value("alerts/sensitivity", DEFAULT_SENSITIVITY, type=str)
            idx = self._combo_sensitivity.findData(level)
            self._combo_sensitivity.setCurrentIndex(idx if idx >= 0 else 1)
            from modules.alert_types import DEFAULT_ACK_HOLD_SECONDS
            hold_h = qs.value(
                "alerts/ack_hold_hours", DEFAULT_ACK_HOLD_SECONDS // 3600, type=int
            )
            idx = self._combo_ack_hold.findData(int(hold_h))
            self._combo_ack_hold.setCurrentIndex(
                idx if idx >= 0 else self._combo_ack_hold.findData(24)
            )
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
        self._resolver.set_store(store)
        if hasattr(self, "_alert_drawer"):
            self._alert_drawer.set_store(store)

    def set_global_hours(self, hours: float) -> None:
        if getattr(self, "_chk_unacked_only", None) is not None and self._chk_unacked_only.isChecked():
            return  # unacked filter active -- the header picker must not override it
        self._hist_hours = hours
        if hasattr(self, "_hist_time_combo"):
            _rev = {1.0: "1h", 6.0: "6h", 24.0: "24h", 72.0: "72h", 168.0: "7d"}
            text = _rev.get(hours)
            if text is not None:
                self._hist_time_combo.blockSignals(True)
                self._hist_time_combo.setCurrentText(text)
                self._hist_time_combo.blockSignals(False)
        self._refresh_alert_history()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._notif_tabs.currentIndex() == 1:
            # switch_to_history_tab() sets the inner tab index synchronously,
            # before _nav_crossfade_to()'s deferred setCurrentWidget() actually
            # makes this page visible -- so the currentChanged-driven refresh
            # bails on isVisible() and never retries. showEvent fires exactly
            # when isVisible() becomes true, so redo it here.
            self._refresh_alert_history()
            self.refresh_log()
        elif self._alert_history_table.rowCount() == 0:
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
            enabled=self._chk_toast.isChecked() and not self._route_channel_disabled("toast"),
            min_severity=self._toast_severity.currentText(),
            rule_types=self._route_types_for("toast"),
        ))
        url = self._webhook_url.text().strip()
        channels.append(WebhookChannel(
            enabled=self._chk_webhook.isChecked() and bool(url)
                    and not self._route_channel_disabled("webhook"),
            url=url,
            min_severity=self._webhook_severity.currentText(),
            rule_types=self._route_types_for("webhook"),
        ))
        try:
            port = int(self._email_port.text().strip() or "587")
        except ValueError:
            port = 587
        to_addrs = [a.strip() for a in self._email_to.text().split(",") if a.strip()]
        # Keychain-backed fields read "" from .text() on every restart (the
        # widget shows only a masked placeholder) -- _kr_value() falls back to
        # the live keychain value the placeholder stands in for (Phase 5).
        _email_pw = self._kr_value(_KR_EMAIL_PASS_KEY, self._email_pass)
        channels.append(EmailChannel(
            enabled=self._chk_email.isChecked() and bool(self._email_host.text().strip())
                    and not self._route_channel_disabled("email"),
            smtp_host=self._email_host.text().strip(),
            smtp_port=port,
            use_tls=port != 465,
            username=self._email_user.text().strip(),
            password=_email_pw,
            from_addr=self._email_from.text().strip(),
            to_addrs=to_addrs,
            min_severity=self._email_severity.currentText(),
            rule_types=self._route_types_for("email"),
        ))
        _po_token = self._kr_value(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token)
        _po_user  = self._kr_value(_KR_PUSHOVER_USER_KEY,  self._pushover_user)
        channels.append(PushoverChannel(
            enabled=self._chk_pushover.isChecked() and bool(_po_token) and bool(_po_user)
                    and not self._route_channel_disabled("pushover"),
            api_token=_po_token,
            user_key=_po_user,
            min_severity=self._pushover_severity.currentText(),
            rule_types=self._route_types_for("pushover"),
        ))
        _ntfy_token = self._kr_value(_KR_NTFY_TOKEN_KEY, self._ntfy_token)
        channels.append(NtfyChannel(
            enabled=self._chk_ntfy.isChecked() and bool(self._ntfy_url.text().strip())
                    and not self._route_channel_disabled("ntfy"),
            topic_url=self._ntfy_url.text().strip(),
            access_token=_ntfy_token,
            min_severity=self._ntfy_severity.currentText(),
            rule_types=self._route_types_for("ntfy"),
        ))
        _tg_token = self._kr_value(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token)
        channels.append(TelegramChannel(
            enabled=self._chk_telegram.isChecked()
                    and bool(_tg_token)
                    and bool(self._telegram_chat.text().strip())
                    and not self._route_channel_disabled("telegram"),
            bot_token=_tg_token,
            chat_id=self._telegram_chat.text().strip(),
            min_severity=self._telegram_severity.currentText(),
            rule_types=self._route_types_for("telegram"),
        ))
        self._router.set_channels(channels)

    def _apply_to_engine(self) -> None:
        if self._alert_engine is None:
            return
        # apply_sensitivity() mutates AlertRule objects in place and is NOT
        # idempotent (calling it twice compounds: 200 -> 140 -> 98), so the
        # live rule set must be rebuilt from _default_rules() on every save
        # rather than re-scaling the already-scaled objects -- same sequence
        # app.py's own startup bootstrap uses.
        from modules.alert_suppressor import _default_rules
        from modules.alert_sensitivity import apply_sensitivity
        rules = _default_rules()
        apply_sensitivity(rules, self._combo_sensitivity.currentData())
        for rule in rules:
            chk = self._rule_checkboxes.get(rule.name)
            rule.enabled = bool(chk is not None and chk.isChecked())
        self._alert_engine.set_rules(rules)
        self._alert_engine.set_ack_hold_seconds(
            int(self._combo_ack_hold.currentData()) * 3600
        )

        from modules.alert_suppressor import EscalationPolicy
        wait_minutes = self._spin_escalation_wait.value()
        channel = self._combo_escalation_channel.currentText()
        enabled = self._chk_escalation.isChecked()
        rules_text = self._txt_escalation_rules.text().strip()
        # alert_engine.py::check_escalations() compares rule_name
        # case-sensitively, so free text like "host down" previously
        # escalated nothing. Canonicalise against the live rule set and
        # surface any token that doesn't match one.
        name_lookup = {r.name.casefold(): r.name for r in rules}
        unknown: list[str] = []
        if rules_text:
            rule_names = []
            for token in (t.strip() for t in rules_text.split(",")):
                if not token:
                    continue
                canonical = name_lookup.get(token.casefold())
                if canonical:
                    rule_names.append(canonical)
                else:
                    unknown.append(token)
        else:
            rule_names = [r.name for r in rules if r.enabled]
        policies = [
            EscalationPolicy(
                rule_name=name, wait_minutes=wait_minutes,
                notify_channels=[channel], enabled=enabled,
            )
            for name in rule_names
        ]
        self._alert_engine.set_escalation_policies(policies)
        if hasattr(self, "_escalation_rules_warning"):
            if unknown:
                self._escalation_rules_warning.setText(
                    "Not a known rule: " + ", ".join(unknown)
                )
                self._escalation_rules_warning.setVisible(True)
            else:
                self._escalation_rules_warning.setVisible(False)

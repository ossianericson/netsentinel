"""
NotificationsPage — UI for configuring notification routing rules.

Allows users to:
  - Enable/disable each channel (Toast, Webhook, Email SMTP)
  - Set minimum severity per channel (INFO / WARNING / CRITICAL)
  - Filter by rule type (all, or specific rule types)
  - Configure webhook URL and headers
  - Configure SMTP credentials
  - View the recent delivery log

Config is persisted via QSettings("NetSentinel", "NetSentinel").
Passwords are stored in QSettings (local machine config file, not cloud).

Architecture rules observed:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread.
  • NotificationRouter injected via set_router(); page builds with router=None.
"""
from __future__ import annotations

import json
import time

from PyQt6.QtCore import Qt, QSettings, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BG_DARK,
    BORDER, BTN_HOVER_BG, CARD_HDR_BORDER, GREEN, GREEN_BG, RED, RED_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)


# ── Helpers (shared with settings_page pattern) ───────────────────────────────

def _page_header(title: str, subtitle: str = ""):
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY};font-size:18px;font-weight:bold;"
        "padding:0;background:transparent;border:none;"
    )
    s = QLabel(subtitle)
    s.setStyleSheet(
        f"color:{TEXT_SECONDARY};font-size:11px;"
        "padding:0 0 8px 0;background:transparent;border:none;"
    )
    return t, s


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:0px;}}"
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


_SEV_COLOR = {"INFO": ACCENT, "WARNING": AMBER, "CRITICAL": RED}
_SEV_BG    = {"INFO": BG_CARD, "WARNING": AMBER_BG, "CRITICAL": RED_BG}
_CH_COLOR  = {"TOAST": ACCENT, "WEBHOOK": GREEN, "EMAIL": AMBER}


class NotificationsPage(QWidget):
    """Notification routing configuration and delivery log page."""

    def __init__(self, router=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._router = router

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        pt, ps = _page_header(
            "Notification Routing",
            "Route alerts to desktop notifications, webhooks, or email by severity",
        )
        outer.addWidget(pt)
        outer.addWidget(ps)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)

        il.addWidget(self._build_toast_card())
        il.addWidget(self._build_webhook_card())
        il.addWidget(self._build_email_card())
        il.addWidget(self._build_log_card())
        il.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._restore()

    # ── Toast card ────────────────────────────────────────────────────────────

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

    # ── Webhook card ──────────────────────────────────────────────────────────

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
        )
        btn_test.clicked.connect(self._test_webhook)
        btn_test.setToolTip("Sends a test alert through the configured webhook")
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    # ── Email card ────────────────────────────────────────────────────────────

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
        )
        btn_test.clicked.connect(self._test_email)
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    # ── Delivery log card ─────────────────────────────────────────────────────

    def _build_log_card(self) -> QWidget:
        card, bl = _card("Recent Delivery Log")

        self._log_table = QTableWidget(0, 5)
        self._log_table.setHorizontalHeaderLabels(
            ["Time", "Channel", "Severity", "Host", "Message"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(True)
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._log_table.setAlternatingRowColors(True)
        self._log_table.setFixedHeight(200)
        self._log_table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((110, 90, 80, 120), range(4)):
            self._log_table.setColumnWidth(col, w)
        bl.addWidget(self._log_table)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh Log")
        btn_refresh.setFixedHeight(24)
        btn_refresh.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
        )
        btn_refresh.clicked.connect(self.refresh_log)
        btn_clear = QPushButton("Clear Log")
        btn_clear.setFixedHeight(24)
        btn_clear.setStyleSheet(btn_refresh.styleSheet())
        btn_clear.clicked.connect(self._clear_log)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        bl.addLayout(btn_row)
        return card

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
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
        qs.setValue("notif/email_pass",       self._email_pass.text())
        qs.setValue("notif/email_from",       self._email_from.text().strip())
        qs.setValue("notif/email_to",         self._email_to.text().strip())
        qs.setValue("notif/email_severity",   self._email_severity.currentText())
        self._apply_to_router()

    def _restore(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_toast.setChecked(qs.value("notif/toast_enabled",    True,  type=bool))
        self._toast_severity.setCurrentText(qs.value("notif/toast_severity", "WARNING"))
        self._chk_webhook.setChecked(qs.value("notif/webhook_enabled", False, type=bool))
        self._webhook_url.setText(qs.value("notif/webhook_url",        ""))
        self._webhook_severity.setCurrentText(qs.value("notif/webhook_severity", "CRITICAL"))
        self._chk_email.setChecked(qs.value("notif/email_enabled",     False, type=bool))
        self._email_host.setText(qs.value("notif/email_host",          ""))
        self._email_port.setText(qs.value("notif/email_port",          "587"))
        self._email_user.setText(qs.value("notif/email_user",          ""))
        self._email_pass.setText(qs.value("notif/email_pass",          ""))
        self._email_from.setText(qs.value("notif/email_from",          ""))
        self._email_to.setText(qs.value("notif/email_to",              ""))
        self._email_severity.setCurrentText(qs.value("notif/email_severity", "CRITICAL"))
        self._apply_to_router()

    def _apply_to_router(self) -> None:
        """Push current UI state into the live NotificationRouter."""
        if self._router is None:
            return
        from modules.notification_router import (
            ToastChannel, WebhookChannel, EmailChannel,
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
        self._router.set_channels(channels)

    # ── Router injection ──────────────────────────────────────────────────────

    def set_router(self, router) -> None:
        self._router = router
        self._apply_to_router()

    # ── Log refresh ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def refresh_log(self) -> None:
        if self._router is None:
            return
        entries = self._router.get_delivery_log()
        self._log_table.setRowCount(0)
        for entry in reversed(entries):
            row = self._log_table.rowCount()
            self._log_table.insertRow(row)
            ts_str = time.strftime("%H:%M:%S", time.localtime(entry.get("ts", 0)))
            sev    = entry.get("severity", "")
            sev_color = _SEV_COLOR.get(sev, TEXT_PRIMARY)
            ch_type   = entry.get("channel_type", "")
            ch_color  = _CH_COLOR.get(ch_type, TEXT_PRIMARY)

            for col, val in enumerate([
                ts_str,
                entry.get("channel_name", ""),
                sev,
                entry.get("host", ""),
                entry.get("message", ""),
            ]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2:
                    item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(sev_color))
                if col == 1:
                    item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(ch_color))
                self._log_table.setItem(row, col, item)

    @pyqtSlot()
    def _clear_log(self) -> None:
        if self._router:
            self._router.clear_delivery_log()
        self._log_table.setRowCount(0)

    # ── Test helpers ──────────────────────────────────────────────────────────

    def _test_webhook(self) -> None:
        from modules.notification_router import WebhookChannel, _deliver_webhook
        from modules.alert_engine import AlertFired
        import threading, time as _t
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
        threading.Thread(target=_deliver_webhook, args=(ch, alert), daemon=True).start()

    def _test_email(self) -> None:
        from modules.notification_router import EmailChannel, _deliver_email
        from modules.alert_engine import AlertFired
        import threading, time as _t
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
        threading.Thread(target=_deliver_email, args=(ch, alert), daemon=True).start()

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
SMTP password is stored in the OS keychain via `keyring` (RULE 22-A).
All other notification settings (host, port, username, enabled flags) use QSettings.

Architecture rules observed:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread.
  • NotificationRouter injected via set_router(); page builds with router=None.
  • RULE 22-A: SMTP password stored in OS keychain via keyring, never in QSettings/INI.
  • RULE 22-D: Password QLineEdit uses EchoMode.Password.
"""
from __future__ import annotations

import json
import time

# ── Keyring helpers (RULE 22-A) ───────────────────────────────────────────────
_KR_SERVICE = "NetSentinel"
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
    """Store a secret in the OS keychain. No-op if keyring unavailable."""
    if _KEYRING_OK and value:
        _keyring.set_password(_KR_SERVICE, key, value)
    elif _KEYRING_OK and not value:
        try:
            _keyring.delete_password(_KR_SERVICE, key)
        except Exception:
            pass


def _load_secret(key: str) -> str:
    """Retrieve a secret from the OS keychain. Returns empty string if unavailable."""
    if not _KEYRING_OK:
        return ""
    try:
        return _keyring.get_password(_KR_SERVICE, key) or ""
    except Exception:
        return ""

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
    BORDER, BTN_HOVER_BG, CARD_HDR_BORDER, CARD_RADIUS, GREEN, GREEN_BG, RED, RED_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

from modules.alert_engine import rule_settings_key as _rule_key


# ── Helpers (shared with settings_page pattern) ───────────────────────────────

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


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
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


_SEV_COLOR = {"INFO": ACCENT, "WARNING": AMBER, "CRITICAL": RED}
_SEV_BG    = {"INFO": BG_CARD, "WARNING": AMBER_BG, "CRITICAL": RED_BG}
_CH_COLOR  = {"TOAST": ACCENT, "WEBHOOK": GREEN, "EMAIL": AMBER,
              "PUSHOVER": RED, "NTFY": GREEN, "TELEGRAM": ACCENT}

# (name, rule_type, friendly description) — matches _default_rules() in alert_engine.py
_ALERT_RULE_DEFS = [
    ("High RTT",      "RTT_THRESHOLD",  "Fires when a host\'s round-trip time exceeds the threshold"),
    ("Host Down",     "HOST_DOWN",      "Fires when a monitored host becomes unreachable"),
    ("Host Degraded", "HOST_DEGRADED",  "Fires when a host responds slowly or intermittently"),
    ("New Device",    "NEW_DEVICE",     "Fires when a device with a new MAC address is seen on the network"),
    ("Device Gone",   "DEVICE_GONE",    "Fires when a known device has not been seen recently"),
    ("Cert Expiring", "CERT_EXPIRY",    "Fires when a TLS certificate is within the expiry threshold"),
    ("Cert Expired",  "CERT_EXPIRED",   "Fires when a TLS certificate has already expired"),
    ("Host Flapping", "FLAP",           "Fires when a host oscillates between UP and DOWN repeatedly"),
    ("Service Down",  "SERVICE_DOWN",   "Fires when a monitored TCP service stops responding"),
]


class NotificationsPage(QWidget):
    """Notification routing configuration and delivery log page."""

    def __init__(self, router=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._router = router
        self._alert_engine = None
        self._rule_checkboxes: dict = {}

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
        il.addWidget(self._build_log_card())
        il.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._restore()

    # ── Alert rules card ──────────────────────────────────────────────────────

    def _build_alert_rules_card(self) -> QWidget:
        card, bl = _card("Alert Rules")

        info = QLabel(
            "All alert rules are disabled by default \u2014 you must opt in. "
            "Enable the rules you want; alerts only fire for rules that are active."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none; padding-bottom:4px;"
        )
        bl.addWidget(info)

        from PyQt6.QtWidgets import QGridLayout
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
            desc_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; border:none;"
            )
            grid.addWidget(chk, row_idx, 0)
            grid.addWidget(desc_lbl, row_idx, 1)
            self._rule_checkboxes[name] = chk

        bl.addLayout(grid)
        return card

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

    # ── Pushover card ─────────────────────────────────────────────────────────

    def _build_pushover_card(self) -> QWidget:
        card, bl = _card("Pushover Mobile Push")

        self._chk_pushover = QCheckBox("Enable Pushover notifications")
        self._chk_pushover.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_pushover.stateChanged.connect(self._save)
        bl.addWidget(self._chk_pushover)

        self._pushover_token = _lineedit("App API Token", password=True)
        self._pushover_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("API Token:", self._pushover_token))

        self._pushover_user = _lineedit("User / Group Key", password=True)
        self._pushover_user.editingFinished.connect(self._save)
        bl.addLayout(_field_row("User Key:", self._pushover_user))

        self._pushover_severity = _severity_combo("WARNING")
        self._pushover_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._pushover_severity))

        note = QLabel(
            "Delivers instant push notifications to iOS and Android via Pushover. "
            "Create an app at pushover.net to get an API token. "
            "Both the API Token and User Key are stored in the OS keychain."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)

        btn_test = QPushButton("Send Test Push")
        btn_test.setFixedHeight(26)
        btn_test.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:2px;padding:0 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
        )
        btn_test.clicked.connect(self._test_pushover)
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    # ── ntfy card ─────────────────────────────────────────────────────────────

    def _build_ntfy_card(self) -> QWidget:
        card, bl = _card("ntfy Push Notification (ntfy.sh / self-hosted)")

        self._chk_ntfy = QCheckBox("Enable ntfy notifications")
        self._chk_ntfy.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_ntfy.stateChanged.connect(self._save)
        bl.addWidget(self._chk_ntfy)

        self._ntfy_url = _lineedit("https://ntfy.sh/my-netsentinel-topic")
        self._ntfy_url.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Topic URL:", self._ntfy_url))

        self._ntfy_token = _lineedit("Access token (optional)", password=True)
        self._ntfy_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Access Token:", self._ntfy_token))

        self._ntfy_severity = _severity_combo("WARNING")
        self._ntfy_severity.currentTextChanged.connect(self._save)
        bl.addLayout(_field_row("Minimum severity:", self._ntfy_severity))

        note = QLabel(
            "ntfy.sh is a free, open-source push notification service. "
            "Subscribe to your topic in the ntfy mobile app or browser. "
            "The access token (required only for protected topics) is stored in the OS keychain."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)

        btn_test = QPushButton("Send Test Notification")
        btn_test.setFixedHeight(26)
        btn_test.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:2px;padding:0 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
        )
        btn_test.clicked.connect(self._test_ntfy)
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    # ── Telegram card ─────────────────────────────────────────────────────────

    def _build_telegram_card(self) -> QWidget:
        card, bl = _card("Telegram Bot Notification")

        self._chk_telegram = QCheckBox("Enable Telegram notifications")
        self._chk_telegram.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_telegram.stateChanged.connect(self._save)
        bl.addWidget(self._chk_telegram)

        self._telegram_token = _lineedit("Bot token from @BotFather", password=True)
        self._telegram_token.editingFinished.connect(self._save)
        bl.addLayout(_field_row("Bot Token:", self._telegram_token))

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
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)

        btn_test = QPushButton("Send Test Message")
        btn_test.setFixedHeight(26)
        btn_test.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            f"border-radius:2px;padding:0 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
        )
        btn_test.clicked.connect(self._test_telegram)
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        return card

    # ── Delivery log card ─────────────────────────────────────────────────────

    def _build_escalation_card(self) -> QWidget:
        card, bl = _card("Alert Escalation")

        info = QLabel(
            "Re-notify a second channel when an alert is not acknowledged within a set time. "
            "Acknowledgement is available by right-clicking an alert in any alert table."
        )
        info.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        info.setWordWrap(True)
        bl.addWidget(info)

        self._chk_escalation = QCheckBox("Enable escalation")
        self._chk_escalation.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_escalation.stateChanged.connect(self._save)
        bl.addWidget(self._chk_escalation)

        # Wait time row
        wait_row = QHBoxLayout()
        wait_row.setSpacing(8)
        wait_lbl = QLabel("Escalate if unacknowledged for")
        wait_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        from PyQt6.QtWidgets import QSpinBox
        self._spin_escalation_wait = QSpinBox()
        self._spin_escalation_wait.setRange(1, 1440)
        self._spin_escalation_wait.setValue(15)
        self._spin_escalation_wait.setSuffix(" min")
        self._spin_escalation_wait.setFixedWidth(90)
        self._spin_escalation_wait.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        self._spin_escalation_wait.valueChanged.connect(self._save)
        wait_row.addWidget(wait_lbl)
        wait_row.addWidget(self._spin_escalation_wait)
        wait_row.addStretch()
        bl.addLayout(wait_row)

        # Channel to escalate to
        ch_row = QHBoxLayout()
        ch_row.setSpacing(8)
        ch_lbl = QLabel("Escalate via channel")
        ch_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._combo_escalation_channel = QComboBox()
        self._combo_escalation_channel.addItems([
            "Email", "Webhook", "Pushover", "ntfy", "Telegram"
        ])
        self._combo_escalation_channel.setFixedWidth(140)
        self._combo_escalation_channel.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        self._combo_escalation_channel.currentTextChanged.connect(self._save)
        ch_row.addWidget(ch_lbl)
        ch_row.addWidget(self._combo_escalation_channel)
        ch_row.addStretch()
        bl.addLayout(ch_row)

        # Rules to watch (comma-separated)
        rules_row = QHBoxLayout()
        rules_row.setSpacing(8)
        rules_lbl = QLabel("Watch rules (blank = all):")
        rules_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        self._txt_escalation_rules = QLineEdit()
        self._txt_escalation_rules.setPlaceholderText("Host Down, High RTT  (comma-separated, blank = all)")
        self._txt_escalation_rules.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;"
        )
        self._txt_escalation_rules.editingFinished.connect(self._save)
        rules_row.addWidget(rules_lbl)
        rules_row.addWidget(self._txt_escalation_rules, 1)
        bl.addLayout(rules_row)

        return card

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
        # RULE 22-A: password goes to OS keychain, never QSettings
        _save_secret(_KR_EMAIL_PASS_KEY, self._email_pass.text())
        qs.setValue("notif/email_from",       self._email_from.text().strip())
        qs.setValue("notif/email_to",         self._email_to.text().strip())
        qs.setValue("notif/email_severity",   self._email_severity.currentText())
        # Pushover — tokens to keychain (RULE 22-A)
        qs.setValue("notif/pushover_enabled",  self._chk_pushover.isChecked())
        qs.setValue("notif/pushover_severity", self._pushover_severity.currentText())
        _save_secret(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token.text())
        _save_secret(_KR_PUSHOVER_USER_KEY,  self._pushover_user.text())
        # ntfy — access token to keychain (RULE 22-A); topic URL to QSettings (not a secret)
        qs.setValue("notif/ntfy_enabled",    self._chk_ntfy.isChecked())
        qs.setValue("notif/ntfy_url",        self._ntfy_url.text().strip())
        qs.setValue("notif/ntfy_severity",   self._ntfy_severity.currentText())
        _save_secret(_KR_NTFY_TOKEN_KEY, self._ntfy_token.text())
        # Telegram — bot token to keychain (RULE 22-A); chat_id to QSettings (not a secret)
        qs.setValue("notif/telegram_enabled",  self._chk_telegram.isChecked())
        qs.setValue("notif/telegram_chat",     self._telegram_chat.text().strip())
        qs.setValue("notif/telegram_severity", self._telegram_severity.currentText())
        _save_secret(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token.text())
        # Escalation policy
        qs.setValue("notif/escalation_enabled",  self._chk_escalation.isChecked())
        qs.setValue("notif/escalation_wait",     self._spin_escalation_wait.value())
        qs.setValue("notif/escalation_channel",  self._combo_escalation_channel.currentText())
        qs.setValue("notif/escalation_rules",    self._txt_escalation_rules.text().strip())
        # Alert rule enabled states (one key per rule, opt-in defaults to False)
        for name, chk in self._rule_checkboxes.items():
            qs.setValue(_rule_key(name), chk.isChecked())
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
            # RULE 22-A: load password from OS keychain, never from QSettings
            self._email_pass.setText(_load_secret(_KR_EMAIL_PASS_KEY))
            self._email_from.setText(qs.value("notif/email_from",          ""))
            self._email_to.setText(qs.value("notif/email_to",              ""))
            self._email_severity.setCurrentText(qs.value("notif/email_severity", "CRITICAL"))
            # Migrate: if an old plaintext password exists in QSettings, move it to keychain
            legacy = qs.value("notif/email_pass", "")
            if legacy:
                _save_secret(_KR_EMAIL_PASS_KEY, legacy)
                self._email_pass.setText(legacy)
                qs.remove("notif/email_pass")   # delete from INI immediately
            # Pushover
            self._chk_pushover.setChecked(qs.value("notif/pushover_enabled", False, type=bool))
            self._pushover_severity.setCurrentText(qs.value("notif/pushover_severity", "WARNING"))
            self._pushover_token.setText(_load_secret(_KR_PUSHOVER_TOKEN_KEY))
            self._pushover_user.setText(_load_secret(_KR_PUSHOVER_USER_KEY))
            # ntfy
            self._chk_ntfy.setChecked(qs.value("notif/ntfy_enabled", False, type=bool))
            self._ntfy_url.setText(qs.value("notif/ntfy_url", ""))
            self._ntfy_severity.setCurrentText(qs.value("notif/ntfy_severity", "WARNING"))
            self._ntfy_token.setText(_load_secret(_KR_NTFY_TOKEN_KEY))
            # Telegram
            self._chk_telegram.setChecked(qs.value("notif/telegram_enabled", False, type=bool))
            self._telegram_chat.setText(qs.value("notif/telegram_chat", ""))
            self._telegram_severity.setCurrentText(qs.value("notif/telegram_severity", "WARNING"))
            self._telegram_token.setText(_load_secret(_KR_TELEGRAM_TOKEN_KEY))
            # Escalation
            self._chk_escalation.setChecked(qs.value("notif/escalation_enabled", False, type=bool))
            self._spin_escalation_wait.setValue(int(qs.value("notif/escalation_wait", 15)))
            ch = qs.value("notif/escalation_channel", "Email")
            idx = self._combo_escalation_channel.findText(ch)
            if idx >= 0:
                self._combo_escalation_channel.setCurrentIndex(idx)
            self._txt_escalation_rules.setText(qs.value("notif/escalation_rules", ""))
            # Alert rule enabled states (missing key → False, opt-in only)
            for name, chk in self._rule_checkboxes.items():
                chk.setChecked(qs.value(_rule_key(name), False, type=bool))
        finally:
            self._restoring = False
        self._apply_to_router()

    def _apply_to_router(self) -> None:
        """Push current UI state into the live NotificationRouter."""
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

    # ── Router injection ──────────────────────────────────────────────────────

    def set_router(self, router) -> None:
        self._router = router
        self._apply_to_router()

    # ── Alert engine injection ────────────────────────────────────────────────

    def set_alert_engine(self, engine) -> None:
        """Inject the live AlertEngine so rule changes take effect immediately."""
        self._alert_engine = engine
        self._apply_to_engine()

    def _apply_to_engine(self) -> None:
        """Push current rule checkbox states into the live AlertEngine."""
        if self._alert_engine is None:
            return
        rules = self._alert_engine.get_rules()
        for rule in rules:
            chk = self._rule_checkboxes.get(rule.name)
            if chk is not None:
                rule.enabled = chk.isChecked()
        self._alert_engine.set_rules(rules)

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

    def _test_pushover(self) -> None:
        from modules.notification_router import PushoverChannel, _deliver_pushover
        from modules.alert_engine import AlertFired
        import threading, time as _t
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
        threading.Thread(target=_deliver_pushover, args=(ch, alert), daemon=True).start()

    def _test_ntfy(self) -> None:
        from modules.notification_router import NtfyChannel, _deliver_ntfy
        from modules.alert_engine import AlertFired
        import threading, time as _t
        ch = NtfyChannel(
            enabled=True,
            topic_url=self._ntfy_url.text().strip(),
            access_token=self._ntfy_token.text(),
            min_severity=self._ntfy_severity.currentText(),
        )
        alert = AlertFired(
            rule_name="Test Alert", rule_type="RTT_THRESHOLD",
            host="netsentinel-test", message="This is a test notification from NetSentinel.",
            severity="INFO", ts=int(_t.time()),
        )
        threading.Thread(target=_deliver_ntfy, args=(ch, alert), daemon=True).start()

    def _test_telegram(self) -> None:
        from modules.notification_router import TelegramChannel, _deliver_telegram
        from modules.alert_engine import AlertFired
        import threading, time as _t
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
        threading.Thread(target=_deliver_telegram, args=(ch, alert), daemon=True).start()

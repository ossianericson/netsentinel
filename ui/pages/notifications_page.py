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
import re
import time

# ── ALERT-2: sub-label enrichment helpers ─────────────────────────────────────

def _fmt_elapsed(seconds: int) -> str:
    """Format a duration in seconds into a human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h}h {m:02d}m" if m else f"{h}h"


def _enrich_alert_sublabel(alert: dict) -> str:
    """Return a short contextual sub-label for the given alert dict, or '' if not applicable."""
    rule    = (alert.get("rule_name") or "").upper()
    msg     = alert.get("message") or ""
    elapsed = max(0, int(time.time()) - int(alert.get("ts") or 0))

    if "RTT_THRESHOLD" in rule or "HIGH_RTT" in rule:
        m = re.search(r":\s*([\d.]+)\s*ms", msg)
        return f"RTT: {float(m.group(1)):.0f} ms at alert time" if m else ""

    if "HOST_DOWN" in rule:
        return f"Down for {_fmt_elapsed(elapsed)}"

    if "DEVICE_GONE" in rule:
        return f"Last seen {_fmt_elapsed(elapsed)} ago"

    if "SERVICE_DOWN" in rule:
        m = re.search(r"\((.+):(\d+)\)$", msg)
        prefix = f"Port {m.group(2)} · " if m else ""
        return f"{prefix}down for {_fmt_elapsed(elapsed)}"

    if "CERT_EXPIRY" in rule and "EXPIRED" not in rule:
        m = re.search(r"(\d+)\s+day", msg)
        if m:
            d = int(m.group(1))
            return f"Expires in {d} day{'s' if d != 1 else ''}"
        return ""

    if "CERT_EXPIRED" in rule:
        d = elapsed // 86400
        return f"Expired {max(d, 0)} day{'s' if d != 1 else ''} ago"

    if "THREAT_INTEL" in rule:
        m = re.search(r"score[:\s]+([\d.]+)", msg, re.IGNORECASE)
        return f"Abuse score: {float(m.group(1)):.0f}/100" if m else ""

    return ""


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

from PyQt6.QtCore import Qt, QEvent, QObject, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BG_DARK,
    BORDER, BTN_HOVER_BG, CARD_HDR_BORDER, CARD_RADIUS, GREEN, GREEN_BG, RED, RED_BG,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

from modules.alert_engine import rule_settings_key as _rule_key
from ui.widgets.alert_drawer import AlertDrawer
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.skeleton import clear_skeleton_rows, insert_skeleton_rows


# ── J/K table navigation event filter (KEYBOARD-2) ───────────────────────────

class _JKNavFilter(QObject):
    """Event filter that adds J/K row navigation to a QTableWidget."""

    def __init__(self, table: "QTableWidget", parent=None) -> None:
        super().__init__(parent)
        self._table = table

    def eventFilter(self, obj, event) -> bool:
        if (
            event.type() == QEvent.Type.KeyPress
            and obj is self._table.viewport()
        ):
            key = event.key()
            if key in (Qt.Key.Key_J, Qt.Key.Key_K):
                current = self._table.currentRow()
                step = 1 if key == Qt.Key.Key_J else -1
                target = max(0, min(self._table.rowCount() - 1, current + step))
                self._table.setCurrentCell(target, self._table.currentColumn())
                return True
        return False


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


_RECOMMENDED_RULES = {"Host Down", "New Device", "High RTT", "Cert Expiring", "Host Flapping"}

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

    navigate_to              = pyqtSignal(str)
    view_in_log_hub          = pyqtSignal(float, str)  # (alert_ts, source_key) — TIME-2 passthrough
    automation_rule_requested = pyqtSignal(str, str)   # (rule_name, match_value)
    select_inventory_device  = pyqtSignal(str)         # ip/mac — navigate + select row
    alert_acknowledged       = pyqtSignal()            # emitted after drawer acks; Home card refresh
    _test_done               = pyqtSignal(str, str)   # (channel_key, html_result)

    def __init__(self, router=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._router = router
        self._store = None
        self._alert_engine = None
        self._rule_checkboxes: dict = {}
        self._test_labels: dict[str, QLabel] = {}
        self._test_btns:   dict[str, QPushButton] = {}
        self._kr_locked:      dict[str, "QLineEdit"] = {}
        self._kr_change_btns: dict[str, QPushButton] = {}
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

        # ALERT-1: alert drawer sits to the right of the main scroll area
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

    # ── Keychain field helpers (NOTIF-3) ─────────────────────────────────────

    def _kr_note_row(self, kr_key: str, field: "QLineEdit") -> QWidget:
        """Note + 'Change ›' link placed below a keychain-backed password field."""
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

    def _unlock_kr_field(
        self, kr_key: str, field: "QLineEdit", btn: QPushButton
    ) -> None:
        self._kr_locked.pop(kr_key, None)
        field.setPlaceholderText("")
        btn.setVisible(False)
        field.setFocus()

    def _kr_restore_field(self, kr_key: str, field: "QLineEdit") -> None:
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

    def _kr_save_field(self, kr_key: str, field: "QLineEdit") -> None:
        if kr_key in self._kr_locked and not field.text():
            return  # user hasn't changed — keep existing keychain entry
        _save_secret(kr_key, field.text())
        self._kr_locked.pop(kr_key, None)

    # ── Alert rules card ──────────────────────────────────────────────────────

    def _build_alert_rules_card(self) -> QWidget:
        card, bl = _card("Alert Rules")

        # Active rules count \u2014 updated by _update_rules_badge()
        self._active_rules_lbl = QLabel("0 rules active")
        self._active_rules_lbl.setStyleSheet(
            f"font-size:11px; color:{AMBER}; font-weight:bold; border:none;"
        )
        bl.addWidget(self._active_rules_lbl)

        info = QLabel(
            "All alert rules are disabled by default \u2014 you must opt in. "
            "Enable the rules you want; alerts only fire for rules that are active."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none; padding-bottom:4px;"
        )
        bl.addWidget(info)

        # Banner shown when no rules are active
        self._zero_rules_banner = QFrame()
        self._zero_rules_banner.setStyleSheet(
            f"QFrame {{ background:{AMBER_BG}; border:1px solid {AMBER};"
            f" border-radius:4px; }}"
        )
        banner_lay = QHBoxLayout(self._zero_rules_banner)
        banner_lay.setContentsMargins(10, 6, 10, 6)
        banner_lay.setSpacing(10)
        banner_txt = QLabel("No alert rules are active \u2014 you won\u2019t receive any alerts.")
        banner_txt.setStyleSheet(
            f"color:{AMBER}; font-size:11px; border:none; background:transparent;"
        )
        banner_lay.addWidget(banner_txt, 1)
        rec_btn = QPushButton("Enable recommended rules \u2192")
        rec_btn.setFlat(True)
        rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rec_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
        )
        rec_btn.clicked.connect(self._enable_recommended_rules)
        banner_lay.addWidget(rec_btn)
        self._zero_rules_banner.setVisible(False)
        bl.addWidget(self._zero_rules_banner)

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
        self._test_btns["webhook"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["webhook"] = _lbl
        bl.addWidget(_lbl)
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
        self._test_btns["pushover"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["pushover"] = _lbl
        bl.addWidget(_lbl)
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
        self._test_btns["ntfy"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["ntfy"] = _lbl
        bl.addWidget(_lbl)
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
        self._test_btns["telegram"] = btn_test
        bl.addWidget(btn_test, alignment=Qt.AlignmentFlag.AlignLeft)
        _lbl = QLabel("")
        _lbl.setVisible(False)
        _lbl.setTextFormat(Qt.TextFormat.RichText)
        _lbl.setStyleSheet("font-size:10px; border:none; background:transparent;")
        self._test_labels["telegram"] = _lbl
        bl.addWidget(_lbl)
        return card

    # ── Delivery log card ─────────────────────────────────────────────────────

    def _build_escalation_card(self) -> QWidget:
        card, bl = _card("Alert Escalation")

        # Expander toggle — "Advanced: Escalation" collapsed by default
        self._escalation_expand_btn = QPushButton("▶  Advanced: Escalation")
        self._escalation_expand_btn.setFlat(True)
        self._escalation_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._escalation_expand_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; font-weight:bold;"
            f" background:transparent; border:none; padding:2px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
        )
        bl.addWidget(self._escalation_expand_btn)

        # Collapsible body — hidden by default
        self._escalation_body = QWidget()
        self._escalation_body.setVisible(False)
        body_lay = QVBoxLayout(self._escalation_body)
        body_lay.setContentsMargins(0, 6, 0, 0)
        body_lay.setSpacing(8)

        explainer = QLabel(
            "If this channel fails to deliver, NetSentinel will try the escalation channel instead."
        )
        explainer.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; border:none;")
        explainer.setWordWrap(True)
        body_lay.addWidget(explainer)

        flow_lbl = QLabel("[Primary]  →  fails  →  [Escalation]")
        flow_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; font-style:italic; border:none; padding:2px 0;"
        )
        body_lay.addWidget(flow_lbl)

        self._chk_escalation = QCheckBox("Enable escalation")
        self._chk_escalation.setStyleSheet(f"QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
        self._chk_escalation.stateChanged.connect(self._save)
        body_lay.addWidget(self._chk_escalation)

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
        body_lay.addLayout(wait_row)

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
        body_lay.addLayout(ch_row)

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
        body_lay.addLayout(rules_row)

        bl.addWidget(self._escalation_body)

        self._escalation_expand_btn.clicked.connect(self._toggle_escalation_body)
        return card

    def _toggle_escalation_body(self) -> None:
        expanded = self._escalation_body.isVisible()
        self._escalation_body.setVisible(not expanded)
        arrow = "▼" if not expanded else "▶"
        self._escalation_expand_btn.setText(f"{arrow}  Advanced: Escalation")

    def _build_log_card(self) -> QWidget:
        card, bl = _card("Alert History & Delivery Log")

        _tbl_qss = (
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )

        tabs = QTabWidget()
        tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; border-top:none; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-bottom:none; padding:4px 12px; font-size:11px; }}"
            f"QTabBar::tab:selected {{ color:{TEXT_PRIMARY}; border-bottom:2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}"
        )

        # ── Tab 1: Alert History ──────────────────────────────────────────────
        hist_tab = QWidget()
        hist_lay = QVBoxLayout(hist_tab)
        hist_lay.setContentsMargins(0, 6, 0, 0)
        hist_lay.setSpacing(4)

        # FILTER-3: severity chips + time range filter row
        self._hist_sev_filter: set[str] = {"INFO", "WARNING", "CRITICAL"}
        self._hist_hours = 72.0
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 0, 0, 2)
        sev_lbl = QLabel("Severity:")
        sev_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        filter_row.addWidget(sev_lbl)
        self._hist_sev_btns: dict[str, QPushButton] = {}
        for sev, col in _SEV_COLOR.items():
            btn = QPushButton(sev)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(20)
            btn.setStyleSheet(
                f"QPushButton {{ font-size:9px; font-weight:bold; border:1px solid {col};"
                f" border-radius:3px; padding:0 6px; color:{col}; background:transparent; }}"
                f"QPushButton:checked {{ background:{col}; color:#fff; }}"
                f"QPushButton:unchecked {{ background:transparent; }}"
            )
            btn.toggled.connect(lambda checked, s=sev: self._toggle_hist_sev(s, checked))
            self._hist_sev_btns[sev] = btn
            filter_row.addWidget(btn)
        filter_row.addSpacing(12)
        time_lbl = QLabel("Window:")
        time_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        filter_row.addWidget(time_lbl)
        self._hist_time_combo = QComboBox()
        self._hist_time_combo.setFixedHeight(22)
        self._hist_time_combo.addItems(["1h", "6h", "24h", "72h", "7d"])
        self._hist_time_combo.setCurrentText("72h")
        self._hist_time_combo.setStyleSheet(
            f"QComboBox {{ font-size:10px; background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 4px; }}"
        )
        self._hist_time_combo.currentTextChanged.connect(self._on_hist_time_changed)
        filter_row.addWidget(self._hist_time_combo)
        filter_row.addStretch()
        hist_lay.addLayout(filter_row)

        self._alert_history_table = QTableWidget(0, 5)
        self._alert_history_table.setHorizontalHeaderLabels(
            ["Time", "Rule", "Host", "Severity", "Status"]
        )
        self._alert_history_table.horizontalHeader().setStretchLastSection(False)
        self._alert_history_table.horizontalHeader().setSectionResizeMode(
            1, self._alert_history_table.horizontalHeader().ResizeMode.Stretch
        )
        self._alert_history_table.verticalHeader().setVisible(False)
        self._alert_history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._alert_history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._alert_history_table.setAlternatingRowColors(True)
        self._alert_history_table.verticalHeader().setDefaultSectionSize(26)
        self._alert_history_table.setFixedHeight(200)
        self._alert_history_table.setStyleSheet(_tbl_qss)
        for w, col in zip((100, 80, 100, 80), range(4)):
            self._alert_history_table.setColumnWidth(col, w)
        self._alert_history_table.itemClicked.connect(self._on_alert_row_single_click)
        self._alert_history_table.itemDoubleClicked.connect(self._on_alert_history_row_clicked)
        self._alert_history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._alert_history_table.customContextMenuRequested.connect(self._on_alert_history_context_menu)
        self._jk_filter_hist = _JKNavFilter(self._alert_history_table, self)
        self._alert_history_table.viewport().installEventFilter(self._jk_filter_hist)
        hist_lay.addWidget(self._alert_history_table)

        hist_btn_row = QHBoxLayout()
        btn_hist_refresh = QPushButton("Refresh")
        btn_hist_refresh.setFixedHeight(24)
        btn_hist_refresh.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
        )
        btn_hist_refresh.clicked.connect(self._refresh_alert_history)
        btn_hist_export = QPushButton("↓ Export CSV")
        btn_hist_export.setFixedHeight(24)
        btn_hist_export.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
        )
        btn_hist_export.clicked.connect(self._export_alert_history_csv)
        hist_btn_row.addWidget(btn_hist_refresh)
        hist_btn_row.addWidget(btn_hist_export)
        hist_btn_row.addStretch()
        hist_lay.addLayout(hist_btn_row)
        tabs.addTab(hist_tab, "Alert History")

        # ── Tab 2: Delivery & Retry ──────────────────────────────────────────
        log_tab = QWidget()
        log_lay = QVBoxLayout(log_tab)
        log_lay.setContentsMargins(0, 6, 0, 0)
        log_lay.setSpacing(4)

        self._log_table = QTableWidget(0, 6)
        self._log_table.setHorizontalHeaderLabels(
            ["Time", "Channel", "Severity", "Host", "Message", "Status"]
        )
        self._log_table.horizontalHeader().setStretchLastSection(False)
        self._log_table.horizontalHeader().setSectionResizeMode(
            4, self._log_table.horizontalHeader().ResizeMode.Stretch
        )
        self._log_table.verticalHeader().setVisible(False)
        self._log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._log_table.setAlternatingRowColors(True)
        self._log_table.verticalHeader().setDefaultSectionSize(26)
        self._log_table.setFixedHeight(200)
        self._log_table.setStyleSheet(_tbl_qss)
        for w, col in zip((110, 90, 80, 120, 80), range(5)):
            self._log_table.setColumnWidth(col, w)
        self._log_table.itemClicked.connect(self._on_log_row_clicked)
        self._jk_filter_log = _JKNavFilter(self._log_table, self)
        self._log_table.viewport().installEventFilter(self._jk_filter_log)
        log_lay.addWidget(self._log_table)

        # Detail panel — shown when a failed row is clicked
        self._log_detail = QFrame()
        self._log_detail.setVisible(False)
        self._log_detail.setStyleSheet(
            f"QFrame {{ background:{BG_ALT_ROW}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        _det_lay = QVBoxLayout(self._log_detail)
        _det_lay.setContentsMargins(10, 8, 10, 8)
        _det_lay.setSpacing(4)
        self._log_detail_error_lbl = QLabel("")
        self._log_detail_error_lbl.setWordWrap(True)
        self._log_detail_error_lbl.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent; border:none;"
        )
        _det_btn_row = QHBoxLayout()
        self._log_detail_retry_btn = QPushButton("Retry →")
        self._log_detail_retry_btn.setFixedHeight(24)
        self._log_detail_retry_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:4px; padding:0 12px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        _det_close_btn = QPushButton("Close")
        _det_close_btn.setFixedHeight(24)
        _det_close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:11px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        _det_close_btn.clicked.connect(lambda: self._log_detail.setVisible(False))
        _det_btn_row.addWidget(self._log_detail_retry_btn)
        _det_btn_row.addWidget(_det_close_btn)
        _det_btn_row.addStretch()
        _det_lay.addWidget(self._log_detail_error_lbl)
        _det_lay.addLayout(_det_btn_row)
        log_lay.addWidget(self._log_detail)
        self._log_detail_entry: dict | None = None

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
        log_lay.addLayout(btn_row)

        cta = QPushButton("＋  Create custom alert →")
        cta.setFlat(True)
        cta.setCursor(Qt.CursorShape.PointingHandCursor)
        cta.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:4px 0; text-align:left; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
        )
        cta.clicked.connect(lambda: self.navigate_to.emit("Custom Triggers"))
        log_lay.addWidget(cta)
        tabs.addTab(log_tab, "Delivery & Retry")

        bl.addWidget(tabs)
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
        self._kr_save_field(_KR_EMAIL_PASS_KEY, self._email_pass)
        qs.setValue("notif/email_from",       self._email_from.text().strip())
        qs.setValue("notif/email_to",         self._email_to.text().strip())
        qs.setValue("notif/email_severity",   self._email_severity.currentText())
        # Pushover — tokens to keychain (RULE 22-A)
        qs.setValue("notif/pushover_enabled",  self._chk_pushover.isChecked())
        qs.setValue("notif/pushover_severity", self._pushover_severity.currentText())
        self._kr_save_field(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token)
        self._kr_save_field(_KR_PUSHOVER_USER_KEY,  self._pushover_user)
        # ntfy — access token to keychain (RULE 22-A); topic URL to QSettings (not a secret)
        qs.setValue("notif/ntfy_enabled",    self._chk_ntfy.isChecked())
        qs.setValue("notif/ntfy_url",        self._ntfy_url.text().strip())
        qs.setValue("notif/ntfy_severity",   self._ntfy_severity.currentText())
        self._kr_save_field(_KR_NTFY_TOKEN_KEY, self._ntfy_token)
        # Telegram — bot token to keychain (RULE 22-A); chat_id to QSettings (not a secret)
        qs.setValue("notif/telegram_enabled",  self._chk_telegram.isChecked())
        qs.setValue("notif/telegram_chat",     self._telegram_chat.text().strip())
        qs.setValue("notif/telegram_severity", self._telegram_severity.currentText())
        self._kr_save_field(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token)
        # Escalation policy
        qs.setValue("notif/escalation_enabled",  self._chk_escalation.isChecked())
        qs.setValue("notif/escalation_wait",     self._spin_escalation_wait.value())
        qs.setValue("notif/escalation_channel",  self._combo_escalation_channel.currentText())
        qs.setValue("notif/escalation_rules",    self._txt_escalation_rules.text().strip())
        # Alert rule enabled states (one key per rule, opt-in defaults to False)
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
            # RULE 22-A: load password from OS keychain, never from QSettings
            self._kr_restore_field(_KR_EMAIL_PASS_KEY, self._email_pass)
            self._email_from.setText(qs.value("notif/email_from",          ""))
            self._email_to.setText(qs.value("notif/email_to",              ""))
            self._email_severity.setCurrentText(qs.value("notif/email_severity", "CRITICAL"))
            # Migrate: if an old plaintext password exists in QSettings, move it to keychain
            legacy = qs.value("notif/email_pass", "")
            if legacy:
                _save_secret(_KR_EMAIL_PASS_KEY, legacy)
                qs.remove("notif/email_pass")   # delete from INI immediately
                self._kr_restore_field(_KR_EMAIL_PASS_KEY, self._email_pass)
            # Pushover
            self._chk_pushover.setChecked(qs.value("notif/pushover_enabled", False, type=bool))
            self._pushover_severity.setCurrentText(qs.value("notif/pushover_severity", "WARNING"))
            self._kr_restore_field(_KR_PUSHOVER_TOKEN_KEY, self._pushover_token)
            self._kr_restore_field(_KR_PUSHOVER_USER_KEY,  self._pushover_user)
            # ntfy
            self._chk_ntfy.setChecked(qs.value("notif/ntfy_enabled", False, type=bool))
            self._ntfy_url.setText(qs.value("notif/ntfy_url", ""))
            self._ntfy_severity.setCurrentText(qs.value("notif/ntfy_severity", "WARNING"))
            self._kr_restore_field(_KR_NTFY_TOKEN_KEY, self._ntfy_token)
            # Telegram
            self._chk_telegram.setChecked(qs.value("notif/telegram_enabled", False, type=bool))
            self._telegram_chat.setText(qs.value("notif/telegram_chat", ""))
            self._telegram_severity.setCurrentText(qs.value("notif/telegram_severity", "WARNING"))
            self._kr_restore_field(_KR_TELEGRAM_TOKEN_KEY, self._telegram_token)
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
        self._update_rules_badge()

    def _update_rules_badge(self) -> None:
        count = sum(1 for chk in self._rule_checkboxes.values() if chk.isChecked())
        lbl = getattr(self, "_active_rules_lbl", None)
        banner = getattr(self, "_zero_rules_banner", None)
        if lbl is None:
            return
        noun = "rule" if count == 1 else "rules"
        lbl.setText(f"{count} {noun} active")
        if count == 0:
            lbl.setStyleSheet(
                f"font-size:11px; color:{AMBER}; font-weight:bold; border:none;"
            )
            if banner:
                banner.setVisible(True)
        else:
            lbl.setStyleSheet(
                f"font-size:11px; color:{GREEN}; font-weight:bold; border:none;"
            )
            if banner:
                banner.setVisible(False)

    def _enable_recommended_rules(self) -> None:
        for name, chk in self._rule_checkboxes.items():
            if name in _RECOMMENDED_RULES:
                chk.setChecked(True)
        self._save()

    def _run_test(self, key: str, deliver_fn, ch, alert) -> None:
        import threading
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

    @pyqtSlot(str, str)
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
        if hasattr(self, "_alert_drawer"):
            self._alert_drawer.set_router(router)

    # ── Alert engine injection ────────────────────────────────────────────────

    def set_alert_engine(self, engine) -> None:
        """Inject the live AlertEngine so rule changes take effect immediately."""
        self._alert_engine = engine
        self._apply_to_engine()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._alert_history_table.rowCount() == 0:
            insert_skeleton_rows(self._alert_history_table, count=4)

    # ── Store injection (RECUR-2) ─────────────────────────────────────────────

    def set_store(self, store) -> None:
        self._store = store
        if hasattr(self, "_alert_drawer"):
            self._alert_drawer.set_store(store)

    def set_global_hours(self, hours: float) -> None:
        self._hist_hours = hours
        self._refresh_alert_history()

    # ── Weekly digest (RECUR-2) ───────────────────────────────────────────────

    def _build_weekly_digest_card(self) -> "QWidget":
        card, bl = _card("Weekly Digest")

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._chk_weekly_digest = QCheckBox("Send weekly summary every Sunday at")
        self._chk_weekly_digest.setStyleSheet(
            f"QCheckBox {{ color:{TEXT_PRIMARY}; font-size:11px; }}"
            f"QCheckBox::indicator {{ width:12px; height:12px;"
            f" border:1px solid {BORDER}; border-radius:2px; background:{BG_CARD}; }}"
            f"QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}"
        )
        self._chk_weekly_digest.toggled.connect(self._save_digest_settings)

        self._combo_digest_time = QComboBox()
        for h in range(6, 23):
            self._combo_digest_time.addItem(f"{h:02d}:00")
        self._combo_digest_time.setCurrentText("09:00")
        self._combo_digest_time.setFixedWidth(80)
        self._combo_digest_time.setStyleSheet(
            f"QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 6px;font-size:11px;}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};selection-background-color:{ACCENT};}}"
        )
        self._combo_digest_time.currentTextChanged.connect(self._save_digest_settings)

        row1.addWidget(self._chk_weekly_digest)
        row1.addWidget(self._combo_digest_time)
        row1.addStretch()
        bl.addLayout(row1)

        hint = QLabel(
            "Includes: devices seen, new unknown devices, alerts fired, config drift, CVE matches."
        )
        hint.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; border:none;"
        )
        bl.addWidget(hint)

        from PyQt6.QtWidgets import QPushButton as _PB
        btn_gen = _PB("Generate now — copy to clipboard")
        btn_gen.setFixedHeight(26)
        btn_gen.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_gen.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
        )
        btn_gen.clicked.connect(self._on_generate_digest)
        bl.addWidget(btn_gen)

        self._digest_status_lbl = QLabel("")
        self._digest_status_lbl.setStyleSheet(
            f"color:{GREEN}; font-size:10px; border:none; background:transparent;"
        )
        self._digest_status_lbl.setVisible(False)
        bl.addWidget(self._digest_status_lbl)

        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_weekly_digest.setChecked(qs.value("notif/weekly_digest_enabled", False, type=bool))
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
            QTimer.singleShot(3000, lambda: lbl.setVisible(False))

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
                    lines.append(f"Network grade:       {grade.get('grade', '—')}  ({grade.get('score', '—'):.0f}/100)")
            except Exception:
                pass
        else:
            lines.append("(Store not available — open the app to generate live data)")
        lines += ["", "Generated by NetSentinel"]
        return "\n".join(lines)

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
        self._refresh_alert_history()
        if self._router is None:
            return
        from PyQt6.QtGui import QColor, QBrush
        entries = self._router.get_delivery_log()
        self._log_table.setRowCount(0)
        for entry in reversed(entries):
            row = self._log_table.rowCount()
            self._log_table.insertRow(row)
            ts_str    = time.strftime("%H:%M:%S", time.localtime(entry.get("ts", 0)))
            sev       = entry.get("severity", "")
            sev_color = _SEV_COLOR.get(sev, TEXT_PRIMARY)
            ch_type   = entry.get("channel_type", "")
            ch_color  = _CH_COLOR.get(ch_type, TEXT_PRIMARY)
            status    = entry.get("status", "PENDING")
            err       = entry.get("error", "")

            if status == "DELIVERED":
                status_txt, status_color = "✓ Delivered", GREEN
            elif status == "FAILED":
                status_txt, status_color = "✗ Failed", RED
            else:
                status_txt, status_color = "⟳ Pending", TEXT_MUTED

            for col, val in enumerate([
                ts_str,
                entry.get("channel_name", ""),
                sev,
                entry.get("host", ""),
                entry.get("message", ""),
                status_txt,
            ]):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 2:
                    item.setForeground(QColor(sev_color))
                elif col == 1:
                    item.setForeground(QColor(ch_color))
                elif col == 5:
                    item.setForeground(QColor(status_color))
                if status == "FAILED":
                    item.setBackground(QBrush(QColor(RED + "22")))
                    if err and col == 5:
                        item.setToolTip(err)
                self._log_table.setItem(row, col, item)
            # Store entry ref in first column for click handler
            self._log_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, entry
            )

    @pyqtSlot()
    def _on_log_row_clicked(self, item: "QTableWidgetItem") -> None:
        first = self._log_table.item(item.row(), 0)
        if first is None:
            return
        entry = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict) or entry.get("status") != "FAILED":
            self._log_detail.setVisible(False)
            return
        err = entry.get("error", "Unknown error")
        self._log_detail_error_lbl.setText(f"Error: {err}")
        self._log_detail_entry = entry
        try:
            self._log_detail_retry_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._log_detail_retry_btn.clicked.connect(self._retry_log_entry)
        self._log_detail.setVisible(True)

    def _retry_log_entry(self) -> None:
        if self._router and self._log_detail_entry:
            self._router.retry_delivery(self._log_detail_entry)
            self._log_detail.setVisible(False)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, self.refresh_log)

    @pyqtSlot()
    def _clear_log(self) -> None:
        if self._router:
            self._router.clear_delivery_log()
        self._log_table.setRowCount(0)
        self._log_detail.setVisible(False)

    def _refresh_alert_history(self) -> None:
        """NOTIF-6: populate Alert History tab from store (with dedup ×N and snooze status)."""
        if self._store is None:
            return
        from PyQt6.QtGui import QColor
        try:
            alerts = self._store.get_recent_alerts(hours=self._hist_hours, limit=500)
        except Exception:
            return
        if self._hist_sev_filter != {"INFO", "WARNING", "CRITICAL"}:
            alerts = [a for a in alerts if a.get("severity", "INFO") in self._hist_sev_filter]

        # ALERT-2: group by (rule_name, host) → keep most-recent, add count
        seen: dict = {}  # key → (alert_dict, count)
        for alert in alerts:
            key = (alert.get("rule_name", ""), alert.get("host", ""))
            if key not in seen:
                seen[key] = (alert, 1)
            else:
                seen[key] = (seen[key][0], seen[key][1] + 1)
        grouped = list(seen.values())

        # ALERT-1: get snooze state from router
        snoozes = self._router.get_all_snoozes() if self._router else {}

        clear_skeleton_rows(self._alert_history_table)
        self._alert_history_table.setRowCount(0)
        for alert, count in grouped:
            row = self._alert_history_table.rowCount()
            self._alert_history_table.insertRow(row)
            ts_str    = time.strftime("%m-%d %H:%M", time.localtime(alert.get("ts", 0)))
            sev       = alert.get("severity", "INFO")
            sev_col   = _SEV_COLOR.get(sev, TEXT_PRIMARY)
            rule_name = alert.get("rule_name", "")
            rule_disp = f"{rule_name}  ×{count}" if count > 1 else rule_name

            snooze_expiry = snoozes.get(rule_name)
            if snooze_expiry is not None:
                if snooze_expiry == 0:
                    status = "Snoozed ∞"
                else:
                    status = time.strftime("Snoozed →%H:%M", time.localtime(snooze_expiry))
                st_col = TEXT_MUTED
            elif alert.get("acked_ts"):
                status = "✓ Acked"
                st_col = GREEN
            else:
                status = "Pending"
                st_col = AMBER

            for col, val in enumerate([
                ts_str, rule_disp, alert.get("host", ""), sev, status,
            ]):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 3:
                    it.setForeground(QColor(sev_col))
                elif col == 4:
                    it.setForeground(QColor(st_col))
                self._alert_history_table.setItem(row, col, it)
            self._alert_history_table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, alert
            )

            # ALERT-2: overlay rule column with a two-line widget (rule name + live sub-label)
            sub_label = _enrich_alert_sublabel(alert)
            _cw = QWidget()
            _cw.setAutoFillBackground(False)
            _cl = QVBoxLayout(_cw)
            _cl.setContentsMargins(4, 2, 4, 1)
            _cl.setSpacing(0)
            _lr = QLabel(rule_disp)
            _lr.setStyleSheet(
                f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
            )
            _cl.addWidget(_lr)
            if sub_label:
                _ls = QLabel(sub_label)
                _ls.setStyleSheet(
                    f"color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
                )
                _cl.addWidget(_ls)
            _cl.addStretch()
            self._alert_history_table.setCellWidget(row, 1, _cw)
            if sub_label:
                self._alert_history_table.setRowHeight(row, 36)

    def _on_alert_row_single_click(self, item: "QTableWidgetItem") -> None:
        """ALERT-1: single-click opens the alert detail drawer."""
        first = self._alert_history_table.item(item.row(), 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if isinstance(alert, dict):
            self._alert_drawer.open(alert)

    def _on_drawer_acknowledged(self, alert_id: int) -> None:
        """ALERT-1: refresh alert history after the drawer acks an alert."""
        self._refresh_alert_history()
        self.alert_acknowledged.emit()

    def _on_alert_history_row_clicked(self, item: "QTableWidgetItem") -> None:
        """NOTIF-6: double-click an alert row to navigate to the relevant page."""
        first = self._alert_history_table.item(item.row(), 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(alert, dict):
            return
        rule = alert.get("rule_name", "")
        host = alert.get("host") or alert.get("ip") or ""
        if "Port Scan" in rule or "PORT_SCAN" in rule:
            self.navigate_to.emit("Port Scan (TCP)")
        elif "THREAT_INTEL" in rule or "CVE" in rule or "Cert" in rule:
            self.navigate_to.emit("Threat Intel")
        elif "RATE_SPIKE" in rule or "Bandwidth" in rule:
            self.navigate_to.emit("Live Bandwidth")
        elif "ARP" in rule:
            self.navigate_to.emit("ARP Spoof Watch")
        elif "DHCP" in rule:
            self.navigate_to.emit("DHCP Rogue Monitor")
        elif any(k in rule for k in ("HOST_DOWN", "DEVICE_GONE", "DEVICE_")):
            self.navigate_to.emit("Inventory Changes")
            if host:
                self.select_inventory_device.emit(host)
        else:
            self.navigate_to.emit("Notifications")

    @pyqtSlot("QPoint")
    def _on_alert_history_context_menu(self, pos) -> None:
        """Right-click snooze menu on alert history rows (ALERT-1)."""
        row = self._alert_history_table.rowAt(pos.y())
        if row < 0:
            return
        first = self._alert_history_table.item(row, 0)
        if first is None:
            return
        alert = first.data(Qt.ItemDataRole.UserRole)
        if not isinstance(alert, dict):
            return
        rule_name = alert.get("rule_name", "")
        if not rule_name or not self._router:
            return

        host = alert.get("host") or alert.get("ip") or "*"

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            f" font-size:11px; }}"
            f"QMenu::item:selected {{ background:{ACCENT}; color:#fff; }}"
        )
        _col = self._alert_history_table.currentColumn()
        act_copy_cell = menu.addAction("Copy cell")
        act_copy_row  = menu.addAction("Copy row")
        act_automate  = menu.addAction("Create automation rule…")
        menu.addSeparator()
        expiry = self._router.get_snooze_expiry(rule_name)
        if expiry is not None:
            label = "Snoozed ∞" if expiry == 0 else time.strftime("Snoozed until %H:%M", time.localtime(expiry))
            menu.addAction(f"  {label}").setEnabled(False)
            menu.addSeparator()
            menu.addAction("Un-snooze").triggered.connect(
                lambda: self._apply_snooze(rule_name, None)
            )
        else:
            menu.addAction(f"Snooze: {rule_name}").setEnabled(False)
            menu.addSeparator()
            menu.addAction("Snooze 1 hour").triggered.connect(
                lambda: self._apply_snooze(rule_name, time.time() + 3600)
            )
            menu.addAction("Snooze 8 hours").triggered.connect(
                lambda: self._apply_snooze(rule_name, time.time() + 28800)
            )
            menu.addAction("Snooze forever").triggered.connect(
                lambda: self._apply_snooze(rule_name, 0)
            )
        chosen = menu.exec(self._alert_history_table.viewport().mapToGlobal(pos))
        if chosen == act_automate:
            self.automation_rule_requested.emit(rule_name, host)
        elif chosen == act_copy_cell:
            from PyQt6.QtWidgets import QApplication as _QApp
            it = self._alert_history_table.item(row, _col) if _col >= 0 else None
            _QApp.clipboard().setText(it.text() if it else "")
        elif chosen == act_copy_row:
            from PyQt6.QtWidgets import QApplication as _QApp
            parts = [
                (self._alert_history_table.item(row, c).text()
                 if self._alert_history_table.item(row, c) else "")
                for c in range(self._alert_history_table.columnCount())
            ]
            _QApp.clipboard().setText("\t".join(parts))

    def _export_alert_history_csv(self) -> None:
        import csv as _csv
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Alert History", "alert_history.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        tbl = self._alert_history_table
        cols = [tbl.horizontalHeaderItem(c).text() for c in range(tbl.columnCount())]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(cols)
                for r in range(tbl.rowCount()):
                    w.writerow([
                        (tbl.item(r, c).text() if tbl.item(r, c) else "")
                        for c in range(tbl.columnCount())
                    ])
            import os
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    def _apply_snooze(self, rule_name: str, until_ts) -> None:
        if not self._router:
            return
        if until_ts is None:
            self._router.clear_snooze(rule_name)
        else:
            self._router.set_snooze(rule_name, until_ts)
        self._refresh_alert_history()

    def _toggle_hist_sev(self, sev: str, checked: bool) -> None:
        if checked:
            self._hist_sev_filter.add(sev)
        else:
            self._hist_sev_filter.discard(sev)
        self._refresh_alert_history()

    def _on_hist_time_changed(self, text: str) -> None:
        mapping = {"1h": 1.0, "6h": 6.0, "24h": 24.0, "72h": 72.0, "7d": 168.0}
        self._hist_hours = mapping.get(text, 72.0)
        self._refresh_alert_history()

    # ── Test helpers ──────────────────────────────────────────────────────────

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
            host="netsentinel-test", message="This is a test notification from NetSentinel.",
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

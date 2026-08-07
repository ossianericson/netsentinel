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

from modules.alert_suppressor import DEFAULT_ENABLED_RULES
from ui import styles as _s

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
            pass  # non-fatal


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
    _s.themed_ss(container, "QFrame#pageHeader {{ background: transparent; border: none;"
        " border-bottom: 1px solid {BORDER}; }}")
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    _s.themed_ss(t, "color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;")
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        _s.themed_ss(s, "color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;")
        vbox.addWidget(s)
    return container


def _card(title: str) -> "tuple[QFrame, QVBoxLayout]":
    card = QFrame()
    card.setObjectName("card")
    _s.themed_ss(card, "QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:{CARD_RADIUS};}}")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    tb = QFrame()
    tb.setFixedHeight(32)
    _s.themed_ss(tb, "background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    _s.themed_ss(lbl, "color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)
    body = QWidget()
    _s.themed_ss(body, "background:{BG_CARD};")
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
    _s.themed_ss(lbl, "color:{TEXT_SECONDARY};font-size:11px;")
    row.addWidget(lbl)
    row.addWidget(widget, 1)
    return row


def _lineedit(placeholder: str = "", password: bool = False) -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    le.setFixedHeight(26)
    if password:
        le.setEchoMode(QLineEdit.EchoMode.Password)
    _s.themed_ss(le, "QLineEdit{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
        "border-radius:2px;padding:0 6px;font-size:11px;}}"
        "QLineEdit:focus{{border-color:{ACCENT};}}")
    return le


def _severity_combo(default: str = "WARNING") -> QComboBox:
    cb = QComboBox()
    for lvl in ("INFO", "WARNING", "CRITICAL"):
        cb.addItem(lvl)
    cb.setCurrentText(default)
    cb.setFixedHeight(26)
    _s.themed_ss(cb, "QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
        "border-radius:2px;padding:0 6px;font-size:11px;}}"
        "QComboBox::drop-down{{border:none;}}"
        "QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
        "border:1px solid {BORDER};selection-background-color:{ACCENT};}}")
    return cb


# ── Constants ─────────────────────────────────────────────────────────────────

# The curated set, re-exported from the model layer rather than restated here.
# It used to be a second, older list — {Host Down, New Device, High RTT, Cert
# Expiring, Host Flapping} — that predated the Signal Quality program, so the
# first-run overlay and the "Enable recommended" button both offered a set with
# none of Phase 4's real signals in it and one level-triggered rule that has
# since been dropped. One definition, in modules/alert_suppressor.py.
_RECOMMENDED_RULES = DEFAULT_ENABLED_RULES

_ALERT_RULE_DEFS = [
    ("High RTT",      "RTT_THRESHOLD",  "Fires when a host's round-trip time exceeds the threshold"),
    ("Packet Loss",   "LOSS_THRESHOLD", "Fires when packets are lost reaching a monitored host"),
    ("Host Down",     "HOST_DOWN",      "Fires when a monitored host becomes unreachable"),
    ("Host Degraded", "HOST_DEGRADED",  "Fires when a host responds slowly or intermittently"),
    ("New Device",    "NEW_DEVICE",     "Fires when a device with a new MAC address is seen on the network"),
    ("Device Gone",   "DEVICE_GONE",    "Fires when a known device has not been seen recently"),
    ("Cert Expiring", "CERT_EXPIRY",    "Fires when a TLS certificate is within the expiry threshold"),
    ("Cert Expired",  "CERT_EXPIRED",   "Fires when a TLS certificate has already expired"),
    ("Host Flapping", "FLAP",           "Fires when a host oscillates between UP and DOWN repeatedly"),
    ("Service Down",  "SERVICE_DOWN",   "Fires when a monitored TCP service stops responding"),
    ("Baseline Speed Drop", "BASELINE_DROP",
     "Fires when a scheduled speed test shows a severe drop vs. your recent typical speed"),
    ("Jitter High", "JITTER_HIGH",
     "Fires when a host's jitter stays above threshold for several minutes"),
    ("Mesh Degraded", "MESH_DEGRADED",
     "Fires when a mesh node drops offline or has a weak signal"),
    ("Modem Signal Drop", "MODEM_SIGNAL_DROP",
     "Fires when your modem's signal drops well below normal or downgrades from 5G to LTE"),
    ("Grade Regression", "GRADE_REGRESSION",
     "Fires when your network health grade declines vs. the previous run"),
    ("IP Churn", "IP_CHURN",
     "Fires when a device uses 3 or more different IP addresses within 24 hours"),
    ("RTT Anomaly", "RTT_ANOMALY",
     "Fires when a host's response time rises above its own learned normal (needs 7+ days of data)"),
    ("IoT Behavior Anomaly", "IOT_BEHAVIOR",
     "Fires when a device's traffic deviates from its learned baseline (new destination, port, or rate spike)"),
    ("Trend Forecast", "TREND_FORECAST",
     "Fires an early warning when a metric is projected to cross its threshold soon"),
    ("New Open Port", "NEW_OPEN_PORT",
     "Fires when a known device opens a port that wasn't open on the last nightly sweep"),
    ("New CVE Found", "NEW_CVE",
     "Fires when a tracked service gains a newly published CVE"),
    ("New Internet Exposure", "NEW_EXPOSURE",
     "Fires when a port becomes newly reachable from the internet"),
    ("ARP Spoof Detected", "ARP_SPOOF",
     "Fires when a background ARP watch cycle detects a gateway hijack, IP takeover, or MAC clone"),
    ("Rogue DHCP Server", "ROGUE_DHCP",
     "Fires when a background DHCP watch cycle sees an offer from an unexpected server"),
    ("Config Drift", "CONFIG_DRIFT",
     "Fires when a device is added, removed, or changes role versus your blessed baseline snapshot"),
    ("Infrastructure Unreachable", "INFRA_UNREACHABLE",
     "Fires when a modem, router, access point or switch stops answering its poll — once per outage"),
    ("DNS Latency", "DNS_LATENCY",
     "Fires when DNS lookups get slow relative to what your resolver normally does — once per episode"),
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
        _s.themed_ss(note, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
        row.addWidget(note)
        change_btn = QPushButton("Change ›")
        change_btn.setFixedHeight(18)
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(change_btn, "QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            " font-size:10px; padding:0; }}"
            "QPushButton:hover {{ text-decoration:underline; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
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

    def _kr_value(self, kr_key: str, field: QLineEdit) -> str:
        """Live secret for building a router channel.

        _kr_restore_field() leaves the widget EMPTY and shows only a masked
        placeholder for a secret living in the OS keychain, so .text() is "" after
        every restart. Return the typed text when the user just entered a new
        secret; otherwise fall back to the keychain value the placeholder stands
        in for. Never written back to QSettings (RULE 22-A).
        """
        typed = field.text()
        if typed:
            return typed
        if kr_key in self._kr_locked:
            return _load_secret(kr_key)
        return ""

    def _kr_save_field(self, kr_key: str, field: QLineEdit) -> None:
        if kr_key in self._kr_locked and not field.text():
            return
        _save_secret(kr_key, field.text())
        self._kr_locked.pop(kr_key, None)

    # ── Alert rules card ──────────────────────────────────────────────────────

    def _build_alert_rules_card(self) -> QWidget:
        card, bl = _card("Alert Rules")
        self._active_rules_lbl = QLabel("0 rules active")
        _s.themed_ss(self._active_rules_lbl, "font-size:11px; color:{AMBER}; font-weight:bold; border:none;")
        bl.addWidget(self._active_rules_lbl)
        info = QLabel(
            "All alert rules are disabled by default — you must opt in. "
            "Enable the rules you want; alerts only fire for rules that are active."
        )
        info.setWordWrap(True)
        _s.themed_ss(info, "font-size:11px; color:{TEXT_SECONDARY}; border:none; padding-bottom:4px;")
        bl.addWidget(info)

        sens_row = QHBoxLayout()
        sens_row.setSpacing(8)
        sens_lbl = QLabel("Alert sensitivity:")
        _s.themed_ss(sens_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        sens_row.addWidget(sens_lbl)
        self._combo_sensitivity = QComboBox()
        self._combo_sensitivity.addItem("Conservative — fewer, higher-confidence alerts", "conservative")
        self._combo_sensitivity.addItem("Balanced (default)", "balanced")
        self._combo_sensitivity.addItem("Aggressive — more, earlier alerts", "aggressive")
        self._combo_sensitivity.setFixedWidth(280)
        _s.themed_ss(self._combo_sensitivity, "QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 6px;font-size:11px;}}"
            "QComboBox::drop-down{{border:none;}}"
            "QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            "border:1px solid {BORDER};selection-background-color:{ACCENT};}}")
        self._combo_sensitivity.currentIndexChanged.connect(self._save)
        sens_row.addWidget(self._combo_sensitivity)
        sens_row.addStretch()
        bl.addLayout(sens_row)
        self._sens_hint_lbl = QLabel(
            "Scales the trigger thresholds and cooldowns of every rule above — "
            "does not change which rules are enabled. Applies immediately."
        )
        self._sens_hint_lbl.setWordWrap(True)
        _s.themed_ss(self._sens_hint_lbl, "font-size:10px; color:{TEXT_MUTED}; border:none; padding-bottom:4px;")
        bl.addWidget(self._sens_hint_lbl)

        hold_row = QHBoxLayout()
        hold_row.setSpacing(8)
        hold_lbl = QLabel("Acknowledging mutes an alert for:")
        _s.themed_ss(hold_lbl, "font-size:11px; color:{TEXT_PRIMARY}; border:none;")
        hold_row.addWidget(hold_lbl)
        self._combo_ack_hold = QComboBox()
        for _label, _hours in (
            ("1 hour", 1), ("8 hours", 8), ("24 hours (default)", 24),
            ("7 days", 168), ("Don't mute — always re-alert", 0),
        ):
            self._combo_ack_hold.addItem(_label, _hours)
        self._combo_ack_hold.setFixedWidth(280)
        _s.themed_ss(self._combo_ack_hold, "QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            "border-radius:2px;padding:0 6px;font-size:11px;}}"
            "QComboBox::drop-down{{border:none;}}"
            "QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            "border:1px solid {BORDER};selection-background-color:{ACCENT};}}")
        self._combo_ack_hold.currentIndexChanged.connect(self._save)
        hold_row.addWidget(self._combo_ack_hold)
        hold_row.addStretch()
        bl.addLayout(hold_row)
        _hold_hint = QLabel(
            "A condition that stays true (a service still down, a device still "
            "gone) otherwise re-alerts every few minutes forever. Acknowledging "
            "silences that device + rule for this long. A recovery always clears "
            "the mute, so a genuinely new problem still alerts."
        )
        _hold_hint.setWordWrap(True)
        _s.themed_ss(_hold_hint, "font-size:10px; color:{TEXT_MUTED}; border:none; padding-bottom:4px;")
        bl.addWidget(_hold_hint)

        self._zero_rules_banner = QFrame()
        _s.themed_ss(self._zero_rules_banner, "QFrame {{ background:{AMBER_BG}; border:1px solid {AMBER}; border-radius:4px; }}")
        banner_lay = QHBoxLayout(self._zero_rules_banner)
        banner_lay.setContentsMargins(10, 6, 10, 6)
        banner_lay.setSpacing(10)
        banner_txt = QLabel(
            "No alert rules are active — you won't receive any alerts."
        )
        _s.themed_ss(banner_txt, "color:{AMBER}; font-size:11px; border:none; background:transparent;")
        banner_lay.addWidget(banner_txt, 1)
        rec_btn = QPushButton("Enable recommended rules →")
        rec_btn.setFlat(True)
        rec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(rec_btn, "QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            " border:none; padding:0; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; text-decoration:underline; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
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
            chk.setFixedWidth(175)
            _s.themed_ss(chk, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
            chk.stateChanged.connect(self._save)
            desc_lbl = QLabel(description)
            _s.themed_ss(desc_lbl, "font-size:10px; color:{TEXT_SECONDARY}; border:none;")
            grid.addWidget(chk, row_idx, 0)
            grid.addWidget(desc_lbl, row_idx, 1)
            self._rule_checkboxes[name] = chk
        bl.addLayout(grid)

        # ── Service Down sub-toggle — background root-cause diagnosis ──────────
        esc_row = QHBoxLayout()
        esc_row.setContentsMargins(20, 0, 0, 0)
        esc_row.setSpacing(8)
        self._chk_service_escalation = QCheckBox("Diagnose why (recommended)")
        _s.themed_ss(self._chk_service_escalation, "QCheckBox{{color:{TEXT_SECONDARY};font-size:10px;}}")
        self._chk_service_escalation.stateChanged.connect(self._save)
        esc_row.addWidget(self._chk_service_escalation)
        esc_desc = QLabel(
            "Runs a background diagnostic and explains why (filtered by a firewall, "
            "local network issue, or a real outage)"
        )
        _s.themed_ss(esc_desc, "font-size:10px; color:{TEXT_SECONDARY}; border:none;")
        esc_row.addWidget(esc_desc, 1)
        bl.addLayout(esc_row)

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
            _s.themed_ss(lbl, "font-size:11px; color:{AMBER}; font-weight:bold; border:none;")
            if banner:
                banner.setVisible(True)
        else:
            _s.themed_ss(lbl, "font-size:11px; color:{GREEN}; font-weight:bold; border:none;")
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
        _s.themed_ss(self._chk_toast, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
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
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        return card

    def _build_webhook_card(self) -> QWidget:
        card, bl = _card("Webhook (Slack / Teams / Generic HTTP POST)")
        self._chk_webhook = QCheckBox("Enable webhook")
        _s.themed_ss(self._chk_webhook, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
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
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Alert")
        btn_test.setFixedHeight(26)
        _s.themed_ss(btn_test, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            "border-radius:2px;padding:0 14px;font-size:11px;}}"
            "QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
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
        _s.themed_ss(self._chk_email, "QCheckBox{{color:{TEXT_PRIMARY};font-size:11px;}}")
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
        _s.themed_ss(note, "color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        btn_test = QPushButton("Send Test Email")
        btn_test.setFixedHeight(26)
        _s.themed_ss(btn_test, "QPushButton{{background:{BG_CARD};color:{ACCENT};border:1px solid {ACCENT};"
            "border-radius:2px;padding:0 14px;font-size:11px;}}"
            "QPushButton:hover{{background:{ACCENT};color:{WHITE};}}"
            "QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}")
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
            _s.themed_ss(lbl, "font-size:10px; color:{TEXT_SECONDARY}; border:none; background:transparent;")
            lbl.setText("Testing…")
            lbl.setVisible(True)
        if btn:
            btn.setEnabled(False)

        def _worker() -> None:
            try:
                deliver_fn(ch, alert)
                html = (
                    f'<span style="color:{_s.GREEN};">'
                    f"✓ Sent — check your channel for a test alert.</span>"
                )
                self._test_done.emit(key, html)
                t = threading.Timer(5.0, lambda: self._test_done.emit(key, ""))
                t.daemon = True
                t.start()
            except Exception as exc:
                err = f"{type(exc).__name__}: {str(exc)[:120]}"
                html = f'<span style="color:{_s.RED};">✗ {err}</span>'
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
                if "✓" in html:
                    try:
                        from ui.widgets.toast import ToastManager
                        label = key.replace("_", " ").title()
                        ToastManager.show(f"{label} channel test passed", "success")
                    except Exception:
                        pass  # non-fatal — toast is cosmetic
            else:
                lbl.setVisible(False)

    def _test_webhook(self) -> None:
        from modules.notification_router import WebhookChannel
        from modules.notification_channels import _deliver_webhook
        from modules.alert_types import AlertFired
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
        from modules.notification_router import EmailChannel
        from modules.notification_channels import _deliver_email
        from modules.alert_types import AlertFired
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
        from modules.notification_router import PushoverChannel
        from modules.notification_channels import _deliver_pushover
        from modules.alert_types import AlertFired
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
        from modules.notification_router import NtfyChannel
        from modules.notification_channels import _deliver_ntfy
        from modules.alert_types import AlertFired
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
        from modules.notification_router import TelegramChannel
        from modules.notification_channels import _deliver_telegram
        from modules.alert_types import AlertFired
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

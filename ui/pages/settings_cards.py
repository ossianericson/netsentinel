"""
settings_cards.py — SettingsPage card builder mixin and helpers.

Extracted from settings_page.py (S14-3c) to reduce that file's size.

Provides:
  • Worker threads: _NotifTestWorker, _FetchRegistryWorker, _InstallWorker,
                    _UninstallWorker
  • UI helpers:     _page_header, _card, _integr_cert_count, _integr_svc_count
  • _SettingsCardsMixin — all _build_*_card methods and their handlers,
    inherited by SettingsPage

Usage:
    from ui.pages.settings_cards import _SettingsCardsMixin, _card, ...
    class SettingsPage(_SettingsCardsMixin, QWidget): ...
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import ui.styles as _styles
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_PURPLE, AMBER,
    BADGE_OFF_BG, BADGE_OFF_BORDER, BADGE_OFF_FG, BADGE_OK_BG,
    BADGE_OK_BORDER, BADGE_OK_FG, BG_ALT_ROW, BG_CARD,
    BG_HOVER, BORDER, BTN_HOVER_BG,
    CARD_HDR_BORDER, CARD_RADIUS, DEEP_ORANGE, GREEN,
    INLINE_WARN_BG, INLINE_WARN_FG, NAV_BAR, PRO_WARN_BG,
    RED, RED_BG, TEAL, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WHITE,
)


# ── Worker threads ────────────────────────────────────────────────────────────

class _NotifTestWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, channel_type: str, parent=None):
        super().__init__(parent)
        self._channel_type = channel_type

    def run(self) -> None:
        import socket, time as _t
        host = socket.gethostname()
        ts   = _t.strftime("%Y-%m-%d %H:%M:%S")
        subj = "NetSentinel test message"
        body = f"This is a test from NetSentinel on {host} at {ts}."
        try:
            qs = QSettings("NetSentinel", "NetSentinel")
            ct = self._channel_type
            if ct == "email":
                self._test_email(qs, subj, body)
            elif ct == "webhook":
                self._test_webhook(qs, subj, body)
            elif ct == "pushover":
                self._test_pushover(qs, subj, body)
            elif ct == "telegram":
                self._test_telegram(qs, body)
            elif ct == "ntfy":
                self._test_ntfy(qs, body)
            else:
                raise ValueError(f"Unknown channel: {ct}")
            self.done.emit("Test sent ✓")
        except Exception as exc:
            self.error.emit(f"Failed: {exc}")

    def _test_email(self, qs, subj: str, body: str) -> None:
        import smtplib, ssl
        smtp_host = qs.value("notifications/smtp_host", "")
        smtp_port = qs.value("notifications/smtp_port", 587, int)
        username  = qs.value("notifications/smtp_user", "")
        to_addr   = qs.value("notifications/email_address", "")
        if not smtp_host or not to_addr:
            raise ValueError("SMTP host or recipient not configured — open Notifications settings")
        try:
            import keyring
            password = keyring.get_password("NetSentinel", "notifications/smtp_password") or ""
        except Exception:
            password = ""
        from email.mime.text import MIMEText
        msg = MIMEText(body)
        msg["Subject"] = subj
        msg["From"] = username or to_addr
        msg["To"]   = to_addr
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.ehlo(); s.starttls(context=ctx)
            if username:
                s.login(username, password)
            s.sendmail(msg["From"], [to_addr], msg.as_string())

    def _test_webhook(self, qs, subj: str, body: str) -> None:
        import urllib.request, json
        url = qs.value("notifications/webhook_url", "")
        if not url:
            raise ValueError("Webhook URL not configured — open Notifications settings")
        payload = json.dumps({"subject": subj, "body": body, "source": "NetSentinel"}).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=8)

    def _test_pushover(self, qs, subj: str, body: str) -> None:
        import urllib.request, urllib.parse
        try:
            import keyring
            api_token = keyring.get_password("NetSentinel", "notifications/pushover_token") or ""
        except Exception:
            api_token = ""
        user_key = qs.value("notifications/pushover_user_key", "")
        if not api_token or not user_key:
            raise ValueError("Pushover API token or user key not configured — open Notifications settings")
        data = urllib.parse.urlencode({
            "token": api_token, "user": user_key, "title": subj, "message": body,
        }).encode()
        urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=data, timeout=8)

    def _test_telegram(self, qs, body: str) -> None:
        import urllib.request, urllib.parse
        try:
            import keyring
            bot_token = keyring.get_password("NetSentinel", "notifications/telegram_token") or ""
        except Exception:
            bot_token = ""
        chat_id = qs.value("notifications/telegram_chat_id", "")
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot token or chat ID not configured — open Notifications settings")
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": body}).encode()
        urllib.request.urlopen(url, data=data, timeout=8)

    def _test_ntfy(self, qs, body: str) -> None:
        import urllib.request
        topic_url = qs.value("notifications/ntfy_topic_url", "")
        if not topic_url:
            raise ValueError("ntfy topic URL not configured — open Notifications settings")
        urllib.request.urlopen(
            urllib.request.Request(topic_url, data=body.encode(),
                                   headers={"Title": "NetSentinel Test"}, method="POST"),
            timeout=8,
        )


class _FetchRegistryWorker(QThread):
    ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self) -> None:
        try:
            from modules.plugin_registry import fetch_registry
            entries = fetch_registry(self._url)
            self.ready.emit(entries)
        except Exception as exc:
            self.error.emit(str(exc))


class _InstallWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str, str)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import install_plugin
            install_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


class _UninstallWorker(QThread):
    done  = pyqtSignal(str)
    error = pyqtSignal(str, str)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self._entry = entry

    def run(self) -> None:
        try:
            from modules.plugin_registry import uninstall_plugin
            uninstall_plugin(self._entry)
            self.done.emit(self._entry.name)
        except Exception as exc:
            self.error.emit(self._entry.name, str(exc))


# ── Shared UI helpers ─────────────────────────────────────────────────────────

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
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:{CARD_RADIUS};}}"
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
    bl.setSpacing(10)
    cl.addWidget(body)
    return card, bl


def _integr_cert_count(qs: QSettings) -> "tuple[bool, str]":
    try:
        import json as _json
        targets = _json.loads(qs.value("cert/targets", "[]"))
        n = len(targets) if isinstance(targets, list) else 0
    except Exception:
        n = 0
    return (n > 0, f"{n} target{'s' if n != 1 else ''} configured")


def _integr_svc_count(qs: QSettings) -> "tuple[bool, str]":
    try:
        import json as _json
        targets = _json.loads(qs.value("service_monitor/targets", "[]"))
        n = len(targets) if isinstance(targets, list) else 0
    except Exception:
        n = 0
    return (n > 0, f"{n} target{'s' if n != 1 else ''} configured")


# ── Theme swatch widget ───────────────────────────────────────────────────────

class _ThemeSwatch(QFrame):
    """Clickable mini colour-palette preview card for one theme."""

    clicked = pyqtSignal(str)

    def __init__(self, name: str, colors: dict, parent=None):
        super().__init__(parent)
        self._name = name
        self._colors = colors
        self.setFixedSize(128, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Apply {name} theme")
        self._build(colors)

    def _build(self, c: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        nav = QLabel()
        nav.setFixedHeight(12)
        nav.setStyleSheet(f"background:{c['NAV_BAR']};border:none;")
        outer.addWidget(nav)

        body_w = QWidget()
        body_w.setStyleSheet(f"background:{c['BG_DARK']};border:none;")
        body_lay = QHBoxLayout(body_w)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        sb = QLabel()
        sb.setFixedWidth(8)
        sb.setStyleSheet(f"background:{c.get('SIDEBAR_BG', c['NAV_BAR'])};border:none;")
        body_lay.addWidget(sb)

        content_w = QWidget()
        content_w.setStyleSheet(f"background:{c['BG_DARK']};border:none;")
        content_lay = QHBoxLayout(content_w)
        content_lay.setContentsMargins(6, 6, 6, 6)
        content_lay.setSpacing(5)

        card_lbl = QLabel()
        card_lbl.setFixedSize(36, 26)
        card_lbl.setStyleSheet(
            f"background:{c['BG_CARD']};border:1px solid {c['BORDER']};border-radius:2px;"
        )
        content_lay.addWidget(card_lbl)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{c['ACCENT']};border-radius:2px;border:none;")
        content_lay.addWidget(dot)
        content_lay.addStretch()

        body_lay.addWidget(content_w, 1)
        outer.addWidget(body_w, 1)

        name_lbl = QLabel(self._name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setFixedHeight(18)
        name_lbl.setStyleSheet(
            f"font-size:10px;font-weight:500;color:{c['TEXT_PRIMARY']};"
            f"background:{c['BG_CARD']};border:none;"
        )
        outer.addWidget(name_lbl)

    def set_active(self, active: bool) -> None:
        own_accent = self._colors["ACCENT"]
        if active:
            self.setStyleSheet(
                f"QFrame{{border:2px solid {own_accent};border-radius:4px;}}"
            )
        else:
            self.setStyleSheet(
                f"QFrame{{border:1px solid {_styles.BORDER};border-radius:4px;}}"
            )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._name)


# ── Mixin ─────────────────────────────────────────────────────────────────────

class _SettingsCardsMixin:
    """Pure-Python mixin.  SettingsPage inherits this alongside QWidget."""

    # ── Configuration completeness ────────────────────────────────────────────

    def _build_config_completeness_card(self) -> QFrame:
        card, bl = _card("Configuration Status")
        intro = QLabel(
            "Features that need attention are highlighted. "
            "Click a chip to jump to the relevant settings."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        bl.addWidget(intro)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        self._cfg_chips: dict = {}
        for key, label in [
            ("notifications",   "Notifications"),
            ("sched_scan",      "Scheduled Scan"),
            ("monitor_resume",  "Monitor Resume"),
            ("digest",          "Weekly Digest"),
            ("cve_tracking",    "CVE Tracking"),
            ("automation",      "Automation"),
        ]:
            chip = QLabel(label)
            chip.setFixedHeight(24)
            chip.setStyleSheet(self._chip_style("grey"))
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setContentsMargins(10, 0, 10, 0)
            chips_row.addWidget(chip)
            self._cfg_chips[key] = chip
        chips_row.addStretch()
        bl.addLayout(chips_row)
        self.refresh_config_completeness()
        return card

    def _chip_style(self, state: str) -> str:
        if state == "green":
            return (
                f"font-size:10px; font-weight:bold; color:{BADGE_OK_FG};"
                f" background:{BADGE_OK_BG}; border:1px solid {BADGE_OK_BORDER}; border-radius:10px;"
                " padding:0 10px;"
            )
        if state == "amber":
            return (
                f"font-size:10px; font-weight:bold; color:{INLINE_WARN_FG};"
                f" background:{INLINE_WARN_BG}; border:1px solid {AMBER}; border-radius:10px;"
                " padding:0 10px;"
            )
        return (
            f"font-size:10px; font-weight:bold; color:{BADGE_OFF_FG};"
            f" background:{BADGE_OFF_BG}; border:1px solid {BADGE_OFF_BORDER}; border-radius:10px;"
            " padding:0 10px;"
        )

    def refresh_config_completeness(self, cve_count: int = 0, rule_count: int = 0) -> None:
        if not hasattr(self, "_cfg_chips"):
            return
        s = QSettings("NetSentinel", "NetSentinel")

        def _set(key: str, state: str) -> None:
            self._cfg_chips[key].setStyleSheet(self._chip_style(state))

        _set("notifications", "green" if s.value("tray/alerts_enabled", True, bool) else "grey")
        _set("sched_scan",    "green" if s.value("sched_scan/enabled", False, bool) else "grey")
        any_monitor = (
            s.value("monitor_persist/arp_running", False, bool)
            or s.value("monitor_persist/bandwidth_running", False, bool)
        )
        _set("monitor_resume", "green" if any_monitor else "grey")
        email = s.value("digest/email", "", str)
        digest_on = s.value("digest/enabled", False, bool)
        if digest_on and email:
            _set("digest", "green")
        elif digest_on or email:
            _set("digest", "amber")
        else:
            _set("digest", "grey")
        _set("cve_tracking", "green" if cve_count > 0 else "grey")
        _set("automation",   "green" if rule_count > 0 else "grey")

    # ── Active Integrations ───────────────────────────────────────────────────

    def _build_integrations_card(self) -> QFrame:
        card, bl = _card("Active Integrations")
        qs = QSettings("NetSentinel", "NetSentinel")

        def _row(label: str, status_fn, nav_target: str) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(190)
            lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;")
            status_val = status_fn()
            ok = status_val[0]
            status_txt = status_val[1]
            s_lbl = QLabel(status_txt)
            s_lbl.setStyleSheet(
                f"font-size:11px;color:{GREEN if ok else TEXT_MUTED};background:transparent;"
            )
            cfg_btn = QPushButton("Configure →")
            cfg_btn.setFlat(True)
            cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cfg_btn.setStyleSheet(
                f"QPushButton{{color:{ACCENT};font-size:11px;background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{ACCENT_DARK};}}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
            )
            cfg_btn.clicked.connect(lambda _=False, t=nav_target: self.navigate_to.emit(t))
            row.addWidget(lbl)
            row.addWidget(s_lbl, 1)
            row.addWidget(cfg_btn)
            bl.addLayout(row)

        def _notif_row(label: str, status_fn, nav_target: str, channel_type: str) -> None:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setFixedWidth(190)
            lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;")
            status_val = status_fn()
            ok = status_val[0]
            status_txt = status_val[1]
            s_lbl = QLabel(status_txt)
            s_lbl.setStyleSheet(
                f"font-size:11px;color:{GREEN if ok else TEXT_MUTED};background:transparent;"
            )
            test_btn = QPushButton("Send test")
            test_btn.setFlat(True)
            test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            test_btn.setStyleSheet(
                f"QPushButton{{color:{TEXT_SECONDARY};font-size:11px;background:transparent;"
                f"border:1px solid {BORDER};border-radius:3px;padding:1px 8px;}}"
                f"QPushButton:hover{{color:{TEXT_PRIMARY};border-color:{ACCENT};}}"
                f"QPushButton:disabled{{color:{TEXT_MUTED};}}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
            )
            cfg_btn = QPushButton("Configure →")
            cfg_btn.setFlat(True)
            cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cfg_btn.setStyleSheet(
                f"QPushButton{{color:{ACCENT};font-size:11px;background:transparent;border:none;padding:0;}}"
                f"QPushButton:hover{{color:{ACCENT_DARK};}}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
            )
            cfg_btn.clicked.connect(lambda _=False, t=nav_target: self.navigate_to.emit(t))

            def _run_test(ct=channel_type, btn=test_btn):
                btn.setEnabled(False)
                btn.setText("Sending…")
                w = _NotifTestWorker(ct, parent=self)
                self._notif_test_workers.append(w)
                def _on_done(msg, b=btn, worker=w):
                    b.setEnabled(True)
                    b.setText("Send test")
                    from ui.widgets.toast import ToastManager
                    ToastManager.show(msg, kind="info")
                    if worker in self._notif_test_workers:
                        self._notif_test_workers.remove(worker)
                def _on_err(msg, b=btn, worker=w):
                    b.setEnabled(True)
                    b.setText("Send test")
                    from ui.widgets.toast import ToastManager
                    ToastManager.show(msg, kind="warning")
                    if worker in self._notif_test_workers:
                        self._notif_test_workers.remove(worker)
                w.done.connect(_on_done)
                w.error.connect(_on_err)
                w.start()

            test_btn.clicked.connect(_run_test)
            row.addWidget(lbl)
            row.addWidget(s_lbl, 1)
            row.addWidget(test_btn)
            row.addWidget(cfg_btn)
            bl.addLayout(row)

        _notif_row("Email notifications",
             lambda: (bool(qs.value("notifications/email_address", "")),
                      ("✓ " + str(qs.value("notifications/email_address", ""))[:30])
                      if qs.value("notifications/email_address", "") else "✗ Not configured"),
             "Notifications", "email")
        _notif_row("Webhook",
             lambda: (bool(qs.value("notifications/webhook_url", "")),
                      ("✓ Configured" if qs.value("notifications/webhook_url", "") else "✗ Not set")),
             "Notifications", "webhook")
        _notif_row("Pushover",
             lambda: (bool(qs.value("notifications/pushover_user_key", "")),
                      ("✓ Configured" if qs.value("notifications/pushover_user_key", "") else "✗ Not set")),
             "Notifications", "pushover")
        _row("5G Modem logging",
             lambda: (qs.value("logging/modem_enabled", False, type=bool),
                      (f"● Logging · every {qs.value('logging/modem_interval_min', 5, type=int)} min"
                       if qs.value("logging/modem_enabled", False, type=bool) else "● Not enabled")),
             "Logs")
        _row("Mesh Router logging",
             lambda: (qs.value("logging/mesh_enabled", False, type=bool),
                      (f"● Logging · every {qs.value('logging/mesh_interval_min', 5, type=int)} min"
                       if qs.value("logging/mesh_enabled", False, type=bool) else "● Not enabled")),
             "Logs")
        _row("Syslog receiver",
             lambda: (qs.value("logging/syslog_enabled", True, type=bool),
                      ("● Listening" if qs.value("logging/syslog_enabled", True, type=bool) else "● Disabled")),
             "Logs")
        _row("SNMP traps",
             lambda: (qs.value("logging/snmp_enabled", True, type=bool),
                      ("● Listening" if qs.value("logging/snmp_enabled", True, type=bool) else "● Disabled")),
             "Logs")
        _row("TLS cert targets",   lambda: _integr_cert_count(qs), "TLS & Exposure")
        _row("Service monitor targets", lambda: _integr_svc_count(qs), "Service Monitor")
        return card

    # ── Appearance ────────────────────────────────────────────────────────────

    def _build_appearance_card(self) -> QFrame:
        card, bl = _card("Appearance — Colour Theme")
        desc = QLabel(
            "Choose a colour theme — switches instantly, no restart needed."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)
        self._theme_status_lbl = QLabel("")
        self._theme_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        self._theme_swatches: dict[str, _ThemeSwatch] = {}
        for name, colors in _styles.THEMES.items():
            sw = _ThemeSwatch(name, colors)
            sw.clicked.connect(self._on_theme)
            self._theme_swatches[name] = sw
            swatch_row.addWidget(sw)
        swatch_row.addStretch()
        bl.addLayout(swatch_row)
        bl.addWidget(self._theme_status_lbl)
        self._refresh_theme_swatches()
        bl.addSpacing(10)
        accent_hdr = QLabel("Accent Colour")
        accent_hdr.setStyleSheet(
            f"font-size:11px;font-weight:bold;color:{TEXT_PRIMARY};background:transparent;"
        )
        bl.addWidget(accent_hdr)
        accent_desc = QLabel(
            "Override the active theme's accent colour. Takes effect on next launch."
        )
        accent_desc.setWordWrap(True)
        accent_desc.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(accent_desc)
        _ACCENT_PRESETS = [
            (ACCENT, "Blue"), (ACCENT_PURPLE, "Purple"), (GREEN, "Green"),
            (TEAL, "Teal"), (RED, "Red"),    (DEEP_ORANGE, "Orange"),
        ]
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(6)
        self._accent_status_lbl = QLabel("")
        self._accent_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )
        current_override = _styles.get_accent_override()
        for hex_val, name in _ACCENT_PRESETS:
            sw = QPushButton()
            sw.setFixedSize(28, 28)
            sw.setToolTip(f"{name} ({hex_val})")
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            active = (current_override == hex_val)
            border = ACCENT if active else BORDER
            sw.setStyleSheet(
                f"QPushButton{{background:{hex_val};border:2px solid {border};border-radius:4px;}}"
                f"QPushButton:hover{{border-color:{hex_val};}}"
            )
            sw.clicked.connect(
                lambda _=False, hx=hex_val, nm=name: self._on_accent_swatch(hx, nm)
            )
            swatch_row.addWidget(sw)
        custom_btn = QPushButton("Custom…")
        custom_btn.setFlat(True)
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.setStyleSheet(
            f"QPushButton{{color:{ACCENT};font-size:11px;background:transparent;"
            f"border:1px solid {BORDER};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        custom_btn.clicked.connect(self._on_accent_custom)
        swatch_row.addWidget(custom_btn)
        reset_btn = QPushButton("Reset")
        reset_btn.setFlat(True)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(
            f"QPushButton{{color:{TEXT_SECONDARY};font-size:11px;background:transparent;"
            f"border:1px solid {BORDER};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        reset_btn.clicked.connect(self._on_accent_reset)
        swatch_row.addWidget(reset_btn)
        swatch_row.addStretch()
        bl.addLayout(swatch_row)
        bl.addWidget(self._accent_status_lbl)
        return card

    def _on_accent_swatch(self, hex_val: str, name: str) -> None:
        from ui.styles import apply_accent_override
        apply_accent_override(hex_val)
        self._accent_status_lbl.setText(f"Accent set to {name} ({hex_val}).")

    def _on_accent_custom(self) -> None:
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        from ui.styles import apply_accent_override
        current = _styles.get_accent_override() or _styles.ACCENT
        chosen = QColorDialog.getColor(QColor(current), self, "Choose Accent Colour")
        if chosen.isValid():
            hex_val = chosen.name().upper()
            apply_accent_override(hex_val)
            self._accent_status_lbl.setText(f"Custom accent ({hex_val}) applied.")

    def _on_accent_reset(self) -> None:
        from ui.styles import apply_accent_override
        apply_accent_override(None)
        self._accent_status_lbl.setText("Accent reset to theme default.")

    def _refresh_theme_swatches(self) -> None:
        active = _styles.get_active_theme_name()
        for name, sw in self._theme_swatches.items():
            sw.set_active(name == active)

    def _on_theme(self, name: str) -> None:
        from ui.styles import apply_theme
        apply_theme(name)
        self._refresh_theme_swatches()
        self._theme_status_lbl.setText(f"Theme '{name}' applied.")

    # ── Display preferences ───────────────────────────────────────────────────

    def _build_display_card(self) -> QFrame:
        card, bl = _card("Display Preferences")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_compact = QCheckBox("Compact table rows (24 px — more devices visible)")
        self._chk_compact.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_compact.setChecked(qs.value("display/compact_rows", True, type=bool))
        self._chk_compact.toggled.connect(self._on_compact_toggled)
        bl.addWidget(self._chk_compact)
        self._chk_tooltips = QCheckBox("Show extended tooltips on hover (400 ms delay)")
        self._chk_tooltips.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tooltips.setChecked(qs.value("display/tooltips_enabled", True, type=bool))
        self._chk_tooltips.toggled.connect(self._on_tooltip_toggled)
        bl.addWidget(self._chk_tooltips)
        note = QLabel(
            "Row height and tooltip settings take effect the next time a table is populated."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(note)
        return card

    def _on_compact_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/compact_rows", checked)
        self._mark_dirty()

    def _on_tooltip_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/tooltips_enabled", checked)
        self._mark_dirty()

    # ── Network Scanning ──────────────────────────────────────────────────────

    def _build_scanning_card(self) -> QFrame:
        card, bl = _card("Network Scanning")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_auto_snap = QCheckBox(
            "Auto-snapshot after every scan (keeps last 10) — Config Snapshots"
        )
        self._chk_auto_snap.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_auto_snap.setChecked(qs.value("baseline/auto_snapshot", False, type=bool))
        self._chk_auto_snap.toggled.connect(self._on_auto_snap_toggled)
        bl.addWidget(self._chk_auto_snap)
        note = QLabel(
            "When enabled, a Config Snapshot is silently saved after each device scan. "
            "If any change is detected versus the previous snapshot, a toast and a rail "
            "badge appear on Config Snapshots."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(note)
        return card

    def _on_auto_snap_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("baseline/auto_snapshot", checked)
        self._mark_dirty()

    # ── Scheduled scan ────────────────────────────────────────────────────────

    def _build_sched_scan_card(self) -> QFrame:
        card, bl = _card("Scheduled Full Scan")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_sched_scan = QCheckBox("Enable scheduled full network scan")
        self._chk_sched_scan.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_sched_scan.setChecked(qs.value("sched_scan/enabled", False, bool))
        bl.addWidget(self._chk_sched_scan)

        rec_row = QHBoxLayout()
        rec_row.setSpacing(8)
        rec_lbl = QLabel("Run every")
        rec_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_scan_combo = QComboBox()
        self._sched_scan_combo.addItems(["24 hours (daily)", "12 hours", "6 hours", "1 hour"])
        _interval_map = {"24 hours (daily)": 24, "12 hours": 12, "6 hours": 6, "1 hour": 1}
        _saved_hours = qs.value("sched_scan/interval_hours", 24, int)
        _rev = {v: k for k, v in _interval_map.items()}
        self._sched_scan_combo.setCurrentText(_rev.get(_saved_hours, "24 hours (daily)"))
        self._sched_scan_combo.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        rec_row.addWidget(rec_lbl)
        rec_row.addWidget(self._sched_scan_combo)
        rec_row.addStretch()
        bl.addLayout(rec_row)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        time_lbl = QLabel("Start time (today)")
        time_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_hour_spin = QSpinBox()
        self._sched_hour_spin.setRange(0, 23)
        self._sched_hour_spin.setValue(qs.value("sched_scan/hour", 2, int))
        self._sched_hour_spin.setFixedWidth(55)
        self._sched_hour_spin.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        colon = QLabel(":")
        colon.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;")
        self._sched_min_spin = QSpinBox()
        self._sched_min_spin.setRange(0, 59)
        self._sched_min_spin.setValue(qs.value("sched_scan/minute", 0, int))
        self._sched_min_spin.setFixedWidth(55)
        self._sched_min_spin.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        time_row.addWidget(time_lbl)
        time_row.addWidget(self._sched_hour_spin)
        time_row.addWidget(colon)
        time_row.addWidget(self._sched_min_spin)
        time_row.addStretch()
        bl.addLayout(time_row)

        save_btn = QPushButton("Save Schedule")
        save_btn.setFixedHeight(28)
        save_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" font-size:11px; border-radius:4px; padding:0 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        save_btn.clicked.connect(self._save_sched_scan)
        bl.addWidget(save_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._sched_scan_next_lbl = QLabel("")
        self._sched_scan_next_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent;"
        )
        bl.addWidget(self._sched_scan_next_lbl)
        self._refresh_sched_scan_label()
        return card

    def _save_sched_scan(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("sched_scan/enabled", self._chk_sched_scan.isChecked())
        _interval_map = {"24 hours (daily)": 24, "12 hours": 12, "6 hours": 6, "1 hour": 1}
        hours = _interval_map.get(self._sched_scan_combo.currentText(), 24)
        qs.setValue("sched_scan/interval_hours", hours)
        qs.setValue("sched_scan/hour",   self._sched_hour_spin.value())
        qs.setValue("sched_scan/minute", self._sched_min_spin.value())
        import datetime as _dt
        now = _dt.datetime.now()
        next_run = now.replace(
            hour=self._sched_hour_spin.value(),
            minute=self._sched_min_spin.value(),
            second=0, microsecond=0
        )
        if next_run <= now:
            next_run += _dt.timedelta(hours=hours)
        qs.setValue("sched_scan/next_ts", next_run.timestamp())
        self._refresh_sched_scan_label()
        self._mark_dirty()

    def _refresh_sched_scan_label(self) -> None:
        if not hasattr(self, "_sched_scan_next_lbl"):
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("sched_scan/enabled", False, bool):
            self._sched_scan_next_lbl.setText("Scheduled scan is disabled.")
            return
        import time as _t
        next_ts = float(qs.value("sched_scan/next_ts", 0))
        if next_ts > _t.time():
            import datetime as _dt
            nxt = _dt.datetime.fromtimestamp(next_ts)
            self._sched_scan_next_lbl.setText(
                f"Next scan: {nxt.strftime('%a %d %b at %H:%M')}"
            )
        else:
            self._sched_scan_next_lbl.setText("Next scan: not yet scheduled — click Save.")

    # ── System Tray ───────────────────────────────────────────────────────────

    def _build_tray_card(self) -> QFrame:
        from ui.system_tray import get_run_on_startup
        card, bl = _card("System Tray & Startup")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_tray = QCheckBox(
            "Minimize to system tray on close  (app keeps running in the background)"
        )
        self._chk_tray.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tray.setChecked(qs.value("tray/minimize_to_tray", True, type=bool))
        self._chk_tray.toggled.connect(self._on_tray_toggled)
        bl.addWidget(self._chk_tray)
        self._chk_minimize_tray = QCheckBox(
            "Minimize button also hides to tray  (default is minimize to taskbar)"
        )
        self._chk_minimize_tray.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_minimize_tray.setChecked(
            qs.value("tray/minimize_window_to_tray", False, type=bool)
        )
        self._chk_minimize_tray.toggled.connect(self._on_minimize_tray_toggled)
        bl.addWidget(self._chk_minimize_tray)
        self._chk_startup = QCheckBox(
            "Start NetSentinel automatically when Windows starts  (runs in tray, starts background logger)"
        )
        self._chk_startup.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        if sys.platform != "win32":
            self._chk_startup.setEnabled(False)
            self._chk_startup.setToolTip("Startup registration is only available on Windows")
        else:
            self._chk_startup.setChecked(get_run_on_startup())
        self._chk_startup.toggled.connect(self._on_startup_toggled)
        bl.addWidget(self._chk_startup)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-height:1px; border:none;")
        bl.addWidget(sep)
        notif_lbl = QLabel("Notifications  (all off by default)")
        notif_lbl.setStyleSheet(
            f"font-size:11px; font-weight:600; color:{TEXT_PRIMARY}; background:transparent;"
        )
        bl.addWidget(notif_lbl)
        self._chk_notify_new_device = QCheckBox(
            "Notify when a new device joins the network"
        )
        self._chk_notify_new_device.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_new_device.setChecked(
            qs.value("tray/notify_new_device", False, type=bool)
        )
        self._chk_notify_new_device.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_new_device", v),
                self._mark_dirty(),
            )
        )
        bl.addWidget(self._chk_notify_new_device)
        self._chk_notify_gone = QCheckBox(
            "Notify when a known device leaves the network"
        )
        self._chk_notify_gone.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent;"
        )
        self._chk_notify_gone.setChecked(
            qs.value("tray/notify_device_gone", False, type=bool)
        )
        self._chk_notify_gone.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("tray/notify_device_gone", v),
                self._mark_dirty(),
            )
        )
        bl.addWidget(self._chk_notify_gone)
        note = QLabel(
            "Alert-rule notifications (ARP attacks, HIGH-risk devices, custom rules) "
            "are configured per-rule in the Alerts tab."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent;")
        bl.addWidget(note)
        return card

    def _on_tray_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        QSettings("NetSentinel", "NetSentinel").setValue("tray/minimize_to_tray", checked)
        try:
            from PyQt6.QtWidgets import QApplication
            win = QApplication.instance().activeWindow()
            if win is None:
                for w in QApplication.instance().topLevelWidgets():
                    if hasattr(w, "_tray_manager"):
                        win = w
                        break
            if win and hasattr(win, "_tray_manager"):
                win._tray_manager.set_minimize_to_tray(checked)
        except Exception:
            pass  # non-fatal

    def _on_minimize_tray_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        QSettings("NetSentinel", "NetSentinel").setValue("tray/minimize_window_to_tray", checked)

    def _on_startup_toggled(self, checked: bool) -> None:
        self._mark_dirty()
        from ui.system_tray import set_run_on_startup
        set_run_on_startup(checked)

    # ── Plugin Marketplace ────────────────────────────────────────────────────

    def _build_plugin_marketplace_card(self) -> QFrame:
        from modules.plugin_registry import REGISTRY_URL
        card, bl = _card("Community Plugins — Browse & Install")
        desc = QLabel(
            "Browse community plugins hosted on GitHub. "
            "Click Install to download a plugin to your local plugins folder."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_lbl = QLabel("Registry URL:")
        url_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};")
        url_lbl.setFixedWidth(90)
        self._pm_url = QLineEdit(REGISTRY_URL)
        self._pm_url.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};border:1px solid {BORDER};padding:2px 6px;"
        )
        url_row.addWidget(url_lbl)
        url_row.addWidget(self._pm_url, 1)
        bl.addLayout(url_row)
        _btn_qss = (
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
            f"border:1px solid {ACCENT};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
        )
        tb_row = QHBoxLayout()
        tb_row.setSpacing(6)
        self._pm_btn_refresh = QPushButton("↻  Refresh")
        self._pm_btn_refresh.setStyleSheet(_btn_qss)
        self._pm_btn_refresh.clicked.connect(self._pm_refresh)
        self._pm_btn_install = QPushButton("▼  Install")
        self._pm_btn_install.setStyleSheet(_btn_qss)
        self._pm_btn_install.setEnabled(False)
        self._pm_btn_install.clicked.connect(self._pm_install_selected)
        self._pm_btn_uninstall = QPushButton("✕  Uninstall")
        self._pm_btn_uninstall.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{RED};"
            f"border:1px solid {RED};border-radius:2px;"
            f"padding:0 12px;font-size:11px;height:26px;}}"
            f"QPushButton:hover{{background:{PRO_WARN_BG};}}"
            f"QPushButton:disabled{{color:{TEXT_MUTED};border-color:{BORDER};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_btn_uninstall.clicked.connect(self._pm_uninstall_selected)
        self._pm_btn_folder = QPushButton("📁  Open Plugins Folder")
        self._pm_btn_folder.setStyleSheet(_btn_qss)
        self._pm_btn_folder.clicked.connect(self._pm_open_folder)
        tb_row.addWidget(self._pm_btn_refresh)
        tb_row.addWidget(self._pm_btn_install)
        tb_row.addWidget(self._pm_btn_uninstall)
        tb_row.addStretch()
        tb_row.addWidget(self._pm_btn_folder)
        bl.addLayout(tb_row)
        self._pm_table = QTableWidget(0, 5)
        self._pm_table.setHorizontalHeaderLabels(["Name", "Author", "Tags", "Version", "Status"])
        self._pm_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._pm_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._pm_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._pm_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self._pm_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self._pm_table.verticalHeader().setDefaultSectionSize(24)
        self._pm_table.verticalHeader().setVisible(False)
        self._pm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._pm_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._pm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._pm_table.setAlternatingRowColors(True)
        self._pm_table.setMinimumHeight(160)
        self._pm_table.setStyleSheet(
            f"QTableWidget{{font-size:11px;background:{BG_CARD};border:1px solid {BORDER};}}"
            f"QHeaderView::section{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"font-size:11px;font-weight:bold;border:none;"
            f"border-bottom:1px solid {BORDER};padding:3px 6px;}}"
            f"QTableWidget::item:selected{{background:{ACCENT};color:{WHITE};}}"
        )
        self._pm_table.itemSelectionChanged.connect(self._pm_on_selection)
        bl.addWidget(self._pm_table)
        self._pm_status = QLabel("Click ↻ Refresh to load the community plugin registry.")
        self._pm_status.setStyleSheet(
            f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(self._pm_status)
        self._pm_entries: list = []
        self._pm_workers: list = []
        return card

    def _pm_refresh(self) -> None:
        self._pm_btn_refresh.setEnabled(False)
        self._pm_status.setText("Fetching registry…")
        url = self._pm_url.text().strip()
        worker = _FetchRegistryWorker(url, parent=self)
        worker.ready.connect(self._pm_on_registry_ready)
        worker.error.connect(self._pm_on_registry_error)
        worker.finished.connect(lambda: self._pm_btn_refresh.setEnabled(True))
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_registry_ready(self, entries: list) -> None:
        from modules.plugin_registry import is_installed
        self._pm_entries = entries
        self._pm_table.setRowCount(0)
        for e in entries:
            row = self._pm_table.rowCount()
            self._pm_table.insertRow(row)
            installed = is_installed(e)
            dot_color = GREEN if installed else TEXT_MUTED
            dot_text  = "● Installed" if installed else "○ Available"
            for col, text in enumerate([e.name, e.author, e.tag_str, e.version]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._pm_table.setItem(row, col, item)
            status_item = QTableWidgetItem(dot_text)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            from PyQt6.QtGui import QColor
            status_item.setForeground(QColor(dot_color))
            self._pm_table.setItem(row, 4, status_item)
        self._pm_status.setText(
            f"Loaded {len(entries)} plugin{'s' if len(entries) != 1 else ''} from registry."
        )

    def _pm_on_registry_error(self, msg: str) -> None:
        self._pm_status.setText(
            f"Plugin registry load failed — {msg}. "
            "Check the plugins folder is accessible and not corrupted."
        )

    def _pm_on_selection(self) -> None:
        has_sel = bool(self._pm_table.selectedItems())
        self._pm_btn_install.setEnabled(has_sel)
        self._pm_btn_uninstall.setEnabled(has_sel)

    def _pm_install_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_install.setEnabled(False)
        self._pm_status.setText(f"Installing {entry.name}…")
        worker = _InstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_install_done)
        worker.error.connect(self._pm_on_install_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_install_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} installed successfully.")
        self._pm_on_registry_ready(self._pm_entries)

    def _pm_on_install_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(
            f"Could not install {name} — {msg}. "
            "Check your internet connection and that pip is available."
        )
        self._pm_btn_install.setEnabled(True)

    def _pm_uninstall_selected(self) -> None:
        row = self._pm_table.currentRow()
        if row < 0 or row >= len(self._pm_entries):
            return
        entry = self._pm_entries[row]
        self._pm_btn_uninstall.setEnabled(False)
        self._pm_status.setText(f"Removing {entry.name}…")
        worker = _UninstallWorker(entry, parent=self)
        worker.done.connect(self._pm_on_uninstall_done)
        worker.error.connect(self._pm_on_uninstall_error)
        self._pm_workers.append(worker)
        worker.start()

    def _pm_on_uninstall_done(self, name: str) -> None:
        self._pm_status.setText(f"✓ {name} uninstalled.")
        self._pm_on_registry_ready(self._pm_entries)

    def _pm_on_uninstall_error(self, name: str, msg: str) -> None:
        self._pm_status.setText(
            f"Could not remove {name} — {msg}. "
            "The plugin may be in use; try restarting the application."
        )
        self._pm_btn_uninstall.setEnabled(True)

    def _pm_open_folder(self) -> None:
        import subprocess
        from modules.plugin_system import plugins_dir
        path = plugins_dir()
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # ── Keyboard shortcuts ────────────────────────────────────────────────────

    def _build_shortcuts_card(self) -> QFrame:
        card, bl = _card("Keyboard Shortcuts")
        shortcuts = [
            # Navigation
            ("Ctrl + K",           "Open command palette — fuzzy-search any page or action"),
            ("Ctrl + F",           "Focus sidebar search"),
            ("Escape",             "Close flyout panel / dismiss command palette"),
            # Scanning & data
            ("Ctrl + R",           "Run full scan"),
            ("Ctrl + E",           "Export last scan results"),
            # Application
            ("Ctrl + Q",           "Quit application"),
            ("F5",                 "Refresh current page"),
            ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix mode)"),
            # Tables
            ("Right-click row",    "Context menu: Copy IP / Copy MAC / How to Fix / Port Scan / WoL"),
            ("Click column header","Sort table by that column"),
        ]
        for i, (key, desc) in enumerate(shortcuts):
            row_w = QWidget()
            row_w.setStyleSheet(f"background:{BG_ALT_ROW if i % 2 else BG_CARD};")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 3, 0, 3)
            row_l.setSpacing(12)
            k = QLabel(key)
            k.setFixedWidth(150)
            k.setStyleSheet(
                f"font-family:Consolas;font-size:10px;color:{ACCENT_DARK};background:transparent;"
            )
            d = QLabel(desc)
            d.setStyleSheet(
                f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
            )
            row_l.addWidget(k)
            row_l.addWidget(d, 1)
            bl.addWidget(row_w)
        return card

    # ── Maintenance ───────────────────────────────────────────────────────────

    def _build_maintenance_card(self) -> QFrame:
        card, bl = _card("Maintenance")
        desc = QLabel(
            "Reload the OUI vendor database without restarting the application. "
            "Use this after updating offenders.json or installing a new vendor list."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;")
        bl.addWidget(desc)

        for label, signal_name, color in [
            ("Reload OUI Database",      "reload_oui_requested",      ACCENT),
            ("Reset all dismissed notices", "reset_dismissed_requested", None),
            ("Export All Data (ZIP)",     "export_all_requested",       None),
        ]:
            btn = QPushButton(label)
            btn.setFixedWidth(220)
            c = color or TEXT_SECONDARY
            bc = color or BORDER
            btn.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{c};"
                f" border:1px solid {bc}; padding:4px 14px;"
                f" font-size:11px; border-radius:4px; }}"
                f"QPushButton:hover {{ background:{BTN_HOVER_BG}; }}"
                f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
            )
            btn.clicked.connect(getattr(self, signal_name).emit)
            bl.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)

        skip_hints_btn = QPushButton("Skip all guided hints")
        skip_hints_btn.setFixedWidth(220)
        skip_hints_btn.setToolTip(
            "Mark every first-run coach mark as seen so they never appear again."
        )
        skip_hints_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        skip_hints_btn.clicked.connect(self._on_skip_all_hints)
        bl.addWidget(skip_hints_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        bl.addSpacing(6)
        settings_hdr = QLabel("Settings Export / Import")
        settings_hdr.setStyleSheet(
            f"font-size:11px;font-weight:bold;color:{TEXT_PRIMARY};background:transparent;"
        )
        bl.addWidget(settings_hdr)
        settings_desc = QLabel(
            "Export all settings to a JSON file for backup or migration. "
            "Secrets (passwords, API keys) are stored in the OS keychain and are "
            "NOT included in the export."
        )
        settings_desc.setWordWrap(True)
        settings_desc.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(settings_desc)

        self._settings_io_status = QLabel("")
        self._settings_io_status.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )

        io_row = QHBoxLayout()
        io_row.setSpacing(8)
        exp_btn = QPushButton("Export settings (JSON)")
        exp_btn.setFixedWidth(190)
        exp_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; padding:4px 14px; font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{BTN_HOVER_BG}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        exp_btn.clicked.connect(self._on_export_settings)
        imp_btn = QPushButton("Import settings")
        imp_btn.setFixedWidth(140)
        imp_btn.setStyleSheet(exp_btn.styleSheet())
        imp_btn.clicked.connect(self._on_import_settings)
        io_row.addWidget(exp_btn)
        io_row.addWidget(imp_btn)
        io_row.addStretch()
        bl.addLayout(io_row)
        bl.addWidget(self._settings_io_status)
        bl.addSpacing(6)

        setup_btn = QPushButton("Run first-time setup")
        setup_btn.setFixedWidth(220)
        setup_btn.setStyleSheet(exp_btn.styleSheet())
        setup_btn.clicked.connect(self.run_setup_requested.emit)
        bl.addWidget(setup_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-height:1px; border:none;")
        bl.addWidget(sep2)

        reset_hdr = QLabel("Danger Zone")
        reset_hdr.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{RED}; background:transparent;"
        )
        bl.addWidget(reset_hdr)
        reset_desc = QLabel(
            "Clear all application settings and restore factory defaults. "
            "Secrets stored in the OS keychain are not affected."
        )
        reset_desc.setWordWrap(True)
        reset_desc.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent;"
        )
        bl.addWidget(reset_desc)

        reset_all_btn = QPushButton("Reset all settings to defaults")
        reset_all_btn.setFixedWidth(240)
        reset_all_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{RED};"
            f" border:1px solid {RED}; padding:4px 14px;"
            f" font-size:11px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:{PRO_WARN_BG}; color:{RED}; }}"
            f"QPushButton:pressed {{ background:{RED_BG}; color:{RED}; }}"
        )
        reset_all_btn.clicked.connect(self._on_reset_settings)
        bl.addWidget(reset_all_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._reset_settings_status = QLabel("")
        self._reset_settings_status.setStyleSheet(
            f"font-size:11px; color:{RED}; background:transparent;"
        )
        bl.addWidget(self._reset_settings_status)
        return card

    def _on_export_settings(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from modules.utils import get_app_data_dir
        default_path = str(get_app_data_dir() / "netsentinel_settings.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", default_path, "JSON files (*.json)"
        )
        if not path:
            return
        try:
            from modules.settings_io import export_settings
            export_settings(Path(path))
            self._settings_io_status.setText(f"Settings exported to {Path(path).name}")
        except Exception as exc:
            self._settings_io_status.setText(f"Export failed: {exc}")

    def _on_import_settings(self) -> None:
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON files (*.json)"
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self, "Import Settings",
            "This will overwrite your current settings.\n"
            "Secrets (passwords, API keys) will not be affected.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            from modules.settings_io import import_settings
            count = import_settings(Path(path))
            self._settings_io_status.setText(
                f"Imported {count} settings from {Path(path).name} — restart to apply."
            )
        except Exception as exc:
            self._settings_io_status.setText(f"Import failed: {exc}")

    def _on_reset_settings(self) -> None:
        result = QMessageBox.warning(
            self,
            "Reset all settings to defaults",
            "This will clear ALL application settings, including:\n"
            "  • Display and theme preferences\n"
            "  • Scanning and schedule configuration\n"
            "  • Notification and tray options\n"
            "  • All other stored preferences\n\n"
            "Secrets (passwords, API keys) stored in the OS keychain are NOT affected.\n\n"
            "This cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.clear()
        qs.sync()
        # Restore visible checkboxes to their factory defaults without marking dirty
        for attr, default in [
            ("_chk_compact",           True),
            ("_chk_tooltips",          True),
            ("_chk_auto_snap",         False),
            ("_chk_sched_scan",        False),
            ("_chk_tray",              True),
            ("_chk_minimize_tray",     False),
            ("_chk_notify_new_device", False),
            ("_chk_notify_gone",       False),
        ]:
            if hasattr(self, attr):
                cb = getattr(self, attr)
                cb.blockSignals(True)
                cb.setChecked(default)
                cb.blockSignals(False)
        if hasattr(self, "_reset_settings_status"):
            self._reset_settings_status.setText(
                "All settings reset to defaults — restart NetSentinel to apply."
            )
        self.clear_dirty()

    def _on_skip_all_hints(self) -> None:
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        for key in [
            "onboarding_v6_done",
            "tour/post_scan_done",
            "coach/home_pills_shown",
            "coach/grade_shown",
            "coach/devices_rightclick_shown",
            "coach/log_hub_sources_shown",
            "coach/diagnosis_shown",
        ]:
            qs.setValue(key, True)
        qs.sync()
        if hasattr(self, "_reset_settings_status"):
            self._reset_settings_status.setText(
                "All guided hints marked as seen — they will not appear again."
            )

    # ── App Health ────────────────────────────────────────────────────────────

    def _build_health_card(self) -> QFrame:
        card, bl = _card("App Health")
        tbl = QTableWidget(6, 2)
        tbl.setHorizontalHeaderLabels(["Component", "Status"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{NAV_BAR}; color:{WHITE};"
            f" font-size:10px; font-weight:bold; padding:4px 8px; border:none; }}"
        )
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            f"QTableWidget {{ font-size:11px; color:{TEXT_PRIMARY}; border:none;"
            f" background:{BG_CARD}; alternate-background-color:{BG_ALT_ROW};"
            f" gridline-color:{BORDER}; }}"
            f"QTableWidget::item {{ padding:4px 8px; }}"
        )
        tbl.setFixedHeight(168)
        for row, name in enumerate([
            "Scheduler", "ARP Monitor", "Bandwidth Monitor",
            "Report Scheduler", "Database", "Logger",
        ]):
            tbl.setItem(row, 0, QTableWidgetItem(name))
            tbl.setItem(row, 1, QTableWidgetItem("—"))
            tbl.setRowHeight(row, 24)
        bl.addWidget(tbl)
        self._health_table = tbl
        return card

    def refresh_health_status(self, statuses: dict) -> None:
        if not hasattr(self, "_health_table"):
            return
        tbl = self._health_table
        for row in range(tbl.rowCount()):
            name_item = tbl.item(row, 0)
            if name_item is None:
                continue
            name = name_item.text()
            if name in statuses:
                status_str, ok = statuses[name]
                item = QTableWidgetItem(status_str)
                from PyQt6.QtGui import QColor
                item.setForeground(QColor(GREEN if ok else RED))
                tbl.setItem(row, 1, item)

"""
NotificationRouter — routes AlertFired events to one or more delivery channels.

Each channel is registered with a severity filter and optional rule_type filter.
When an alert fires, the router dispatches it to every matching enabled channel.

Supported channel types
-----------------------
  TOAST       — desktop system-tray notification (callback injected by UI layer)
  WEBHOOK     — HTTP POST JSON payload to a configurable URL
  EMAIL_SMTP  — SMTP email via smtplib (TLS/STARTTLS)

Architecture rules observed
---------------------------
  • Pure Python — no PyQt6, no ui/ imports (ARCH RULE 3).
  • AlertEngine injected; router registers itself as the on_alert callback.
  • Delivery is asynchronous (threading.Thread) — the evaluate_* call returns
    immediately and channels fire in background threads.
  • Channel config is persisted externally (QSettings in the UI layer); this
    module only holds runtime state.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Callable, Dict, List, Optional

from modules.alert_engine import AlertEngine, AlertFired

# ── Severity ordering ─────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}

SEVERITY_LEVELS = ["INFO", "WARNING", "CRITICAL"]


def _severity_gte(severity: str, minimum: str) -> bool:
    """Return True if severity >= minimum in INFO < WARNING < CRITICAL order."""
    return _SEVERITY_ORDER.get(severity, 0) >= _SEVERITY_ORDER.get(minimum, 0)


# ── Channel config dataclasses ────────────────────────────────────────────────

@dataclass
class ToastChannel:
    """Desktop system-tray notification. Callback injected by the UI layer."""
    name:             str  = "Desktop Notification"
    enabled:          bool = True
    min_severity:     str  = "WARNING"     # INFO | WARNING | CRITICAL
    rule_types:       List[str] = field(default_factory=list)  # empty = all


@dataclass
class WebhookChannel:
    """HTTP POST JSON to a URL (e.g. Slack, Teams, generic webhook)."""
    name:         str  = "Webhook"
    enabled:      bool = False
    url:          str  = ""
    min_severity: str  = "CRITICAL"
    rule_types:   List[str] = field(default_factory=list)
    # Optional: static headers dict (e.g. {"Authorization": "Bearer TOKEN"})
    headers:      Dict[str, str] = field(default_factory=dict)
    timeout_s:    int  = 8


@dataclass
class EmailChannel:
    """SMTP email notification."""
    name:         str  = "Email Alert"
    enabled:      bool = False
    smtp_host:    str  = ""
    smtp_port:    int  = 587
    use_tls:      bool = True            # STARTTLS on port 587; set False for SSL port 465
    username:     str  = ""
    password:     str  = ""             # loaded from OS keychain by the UI layer (RULE 22-A)
    from_addr:    str  = ""
    to_addrs:     List[str] = field(default_factory=list)
    min_severity: str  = "CRITICAL"
    rule_types:   List[str] = field(default_factory=list)
    timeout_s:    int  = 10


@dataclass
class PushoverChannel:
    """Pushover mobile push notification (https://pushover.net)."""
    name:         str  = "Pushover"
    enabled:      bool = False
    api_token:    str  = ""   # loaded from OS keychain by the UI layer (RULE 22-A)
    user_key:     str  = ""   # loaded from OS keychain by the UI layer (RULE 22-A)
    min_severity: str  = "WARNING"
    rule_types:   List[str] = field(default_factory=list)
    timeout_s:    int  = 8


@dataclass
class NtfyChannel:
    """ntfy.sh (or self-hosted) push notification (https://ntfy.sh)."""
    name:         str  = "ntfy"
    enabled:      bool = False
    topic_url:    str  = ""    # e.g. https://ntfy.sh/my-topic — stored in QSettings
    access_token: str  = ""    # optional; loaded from OS keychain (RULE 22-A)
    min_severity: str  = "WARNING"
    rule_types:   List[str] = field(default_factory=list)
    timeout_s:    int  = 8


@dataclass
class TelegramChannel:
    """Telegram bot push notification."""
    name:         str  = "Telegram"
    enabled:      bool = False
    bot_token:    str  = ""   # loaded from OS keychain by the UI layer (RULE 22-A)
    chat_id:      str  = ""   # Telegram chat/channel/group ID — stored in QSettings
    min_severity: str  = "WARNING"
    rule_types:   List[str] = field(default_factory=list)
    timeout_s:    int  = 8


# Union type alias
Channel = ToastChannel | WebhookChannel | EmailChannel | PushoverChannel | NtfyChannel | TelegramChannel


# ── Payload builder ───────────────────────────────────────────────────────────

def _build_payload(alert: AlertFired) -> dict:
    """Canonical JSON-serialisable dict for webhook / email bodies."""
    return {
        "ts":        alert.ts,
        "rule_name": alert.rule_name,
        "rule_type": alert.rule_type,
        "host":      alert.host,
        "severity":  alert.severity,
        "message":   alert.message,
        "value":     alert.value,
    }


def _matches_channel(alert: AlertFired, min_severity: str, rule_types: List[str]) -> bool:
    """Return True if the alert should be dispatched to a channel with these filters."""
    if not _severity_gte(alert.severity, min_severity):
        return False
    if rule_types and alert.rule_type not in rule_types:
        return False
    return True


# ── Delivery helpers (run in background threads) ──────────────────────────────

def _deliver_webhook(channel: WebhookChannel, alert: AlertFired) -> None:
    payload = json.dumps(_build_payload(alert)).encode()
    headers = {"Content-Type": "application/json", **channel.headers}
    req = urllib.request.Request(channel.url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            pass
    except (urllib.error.URLError, OSError):
        pass  # Background delivery — failures are silent (logged externally if needed)


def _deliver_email(channel: EmailChannel, alert: AlertFired) -> None:
    if not channel.smtp_host or not channel.to_addrs:
        return
    subject = f"[NetSentinel {alert.severity}] {alert.rule_name} — {alert.host}"
    body = (
        f"Alert: {alert.rule_name}\n"
        f"Severity: {alert.severity}\n"
        f"Host: {alert.host}\n"
        f"Rule type: {alert.rule_type}\n"
        f"Message: {alert.message}\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(alert.ts))}\n"
    )
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"]    = channel.from_addr or channel.username
    msg["To"]      = ", ".join(channel.to_addrs)
    try:
        ctx = ssl.create_default_context()
        if channel.use_tls:
            with smtplib.SMTP(channel.smtp_host, channel.smtp_port,
                              timeout=channel.timeout_s) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                if channel.username:
                    smtp.login(channel.username, channel.password)
                smtp.sendmail(msg["From"], channel.to_addrs, msg.as_string())
        else:
            with smtplib.SMTP_SSL(channel.smtp_host, channel.smtp_port,
                                   context=ctx, timeout=channel.timeout_s) as smtp:
                if channel.username:
                    smtp.login(channel.username, channel.password)
                smtp.sendmail(msg["From"], channel.to_addrs, msg.as_string())
    except (smtplib.SMTPException, OSError):
        pass


def _deliver_pushover(channel: PushoverChannel, alert: AlertFired) -> None:
    """POST to the Pushover API. Requires api_token + user_key."""
    if not channel.api_token or not channel.user_key:
        return
    # Map severity to Pushover priority: -1=low, 0=normal, 1=high
    priority = {"INFO": -1, "WARNING": 0, "CRITICAL": 1}.get(alert.severity, 0)
    payload = json.dumps({
        "token":    channel.api_token,
        "user":     channel.user_key,
        "title":    f"NetSentinel — {alert.rule_name}",
        "message":  f"{alert.host}: {alert.message}",
        "priority": priority,
    }).encode()
    req = urllib.request.Request(
        "https://api.pushover.net/1/messages.json",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            pass
    except (urllib.error.URLError, OSError):
        pass


def _deliver_ntfy(channel: NtfyChannel, alert: AlertFired) -> None:
    """POST to ntfy.sh (or self-hosted). topic_url is the full topic endpoint."""
    if not channel.topic_url:
        return
    # Map severity to ntfy priority (1=min … 5=max)
    priority = {"INFO": "2", "WARNING": "3", "CRITICAL": "5"}.get(alert.severity, "3")
    headers = {
        "Title":    f"NetSentinel — {alert.rule_name}",
        "Priority": priority,
        "Tags":     f"netsentinel,{alert.severity.lower()}",
    }
    if channel.access_token:
        headers["Authorization"] = f"Bearer {channel.access_token}"
    body = f"{alert.host}: {alert.message}".encode()
    req = urllib.request.Request(
        channel.topic_url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            pass
    except (urllib.error.URLError, OSError):
        pass


def _deliver_telegram(channel: TelegramChannel, alert: AlertFired) -> None:
    """POST to the Telegram Bot API sendMessage endpoint."""
    if not channel.bot_token or not channel.chat_id:
        return
    text = (
        f"*NetSentinel — {alert.rule_name}*\n"
        f"Severity: `{alert.severity}`\n"
        f"Host: `{alert.host}`\n"
        f"{alert.message}"
    )
    payload = json.dumps({
        "chat_id":    channel.chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode()
    url = f"https://api.telegram.org/bot{channel.bot_token}/sendMessage"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            pass
    except (urllib.error.URLError, OSError):
        pass


# ── Status-tracked delivery wrappers ─────────────────────────────────────────

def _deliver_webhook_tracked(
    channel: WebhookChannel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    payload = json.dumps(_build_payload(alert)).encode()
    headers = {"Content-Type": "application/json", **channel.headers}
    req = urllib.request.Request(channel.url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))


def _deliver_email_tracked(
    channel: EmailChannel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    if not channel.smtp_host or not channel.to_addrs:
        on_err(entry, "SMTP not configured")
        return
    import smtplib, ssl as _ssl
    from email.mime.text import MIMEText as _MIMEText
    subject = f"[NetSentinel {alert.severity}] {alert.rule_name} — {alert.host}"
    body = (
        f"Alert: {alert.rule_name}\nSeverity: {alert.severity}\n"
        f"Host: {alert.host}\nMessage: {alert.message}\n"
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(alert.ts))}\n"
    )
    msg = _MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = channel.from_addr or channel.username
    msg["To"] = ", ".join(channel.to_addrs)
    try:
        ctx = _ssl.create_default_context()
        if channel.use_tls:
            with smtplib.SMTP(channel.smtp_host, channel.smtp_port, timeout=channel.timeout_s) as s:
                s.ehlo(); s.starttls(context=ctx)
                if channel.username:
                    s.login(channel.username, channel.password)
                s.sendmail(msg["From"], channel.to_addrs, msg.as_string())
        else:
            with smtplib.SMTP_SSL(channel.smtp_host, channel.smtp_port, context=ctx, timeout=channel.timeout_s) as s:
                if channel.username:
                    s.login(channel.username, channel.password)
                s.sendmail(msg["From"], channel.to_addrs, msg.as_string())
        on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))


# ── Router ────────────────────────────────────────────────────────────────────

class NotificationRouter:
    """
    Routes AlertFired events to registered delivery channels.

    Usage::
        router = NotificationRouter()
        router.set_toast_callback(lambda a: show_toast(a.severity, a.message))
        router.set_channels([
            ToastChannel(min_severity="WARNING"),
            WebhookChannel(enabled=True, url="https://hooks.slack.com/..."),
        ])
        # Attach to AlertEngine:
        alert_engine.set_on_alert(router.dispatch)
    """

    def __init__(self) -> None:
        self._channels: List[Channel] = [
            ToastChannel(),   # desktop toast on by default
        ]
        self._toast_cb: Optional[Callable[[AlertFired], None]] = None
        self._lock = threading.Lock()

        # In-memory delivery log — last N dispatches for the UI
        self._log: List[dict] = []
        self._log_max = 500

    # ── Configuration ─────────────────────────────────────────────────────────

    def set_channels(self, channels: List[Channel]) -> None:
        with self._lock:
            self._channels = list(channels)

    def get_channels(self) -> List[Channel]:
        with self._lock:
            return list(self._channels)

    def set_toast_callback(self, cb: Callable[[AlertFired], None]) -> None:
        """Inject the UI toast function (called on the UI's thread via signal)."""
        self._toast_cb = cb

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def dispatch(self, alert: AlertFired) -> None:
        """
        Called by AlertEngine.on_alert. Routes the alert to each matching
        channel. Toast is called synchronously; Webhook and Email fire in
        daemon threads so they never block the monitoring cycle.
        """
        with self._lock:
            channels = list(self._channels)

        for ch in channels:
            if not ch.enabled:
                continue

            if not _matches_channel(alert, ch.min_severity, ch.rule_types):
                continue

            if isinstance(ch, ToastChannel):
                if self._toast_cb:
                    try:
                        self._toast_cb(alert)
                    except Exception:
                        pass
                entry = self._log_delivery(ch.name, "TOAST", alert)
                self._mark_delivered(entry)

            elif isinstance(ch, WebhookChannel):
                if ch.url:
                    entry = self._log_delivery(ch.name, "WEBHOOK", alert)
                    t = threading.Thread(
                        target=_deliver_webhook_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()

            elif isinstance(ch, EmailChannel):
                if ch.smtp_host and ch.to_addrs:
                    entry = self._log_delivery(ch.name, "EMAIL", alert)
                    t = threading.Thread(
                        target=_deliver_email_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()

            elif isinstance(ch, PushoverChannel):
                if ch.api_token and ch.user_key:
                    entry = self._log_delivery(ch.name, "PUSHOVER", alert)
                    t = threading.Thread(
                        target=_deliver_pushover, args=(ch, alert), daemon=True
                    )
                    t.start()
                    # Pushover has no error feedback path — mark delivered optimistically
                    self._mark_delivered(entry)

            elif isinstance(ch, NtfyChannel):
                if ch.topic_url:
                    entry = self._log_delivery(ch.name, "NTFY", alert)
                    t = threading.Thread(
                        target=_deliver_ntfy, args=(ch, alert), daemon=True
                    )
                    t.start()
                    self._mark_delivered(entry)

            elif isinstance(ch, TelegramChannel):
                if ch.bot_token and ch.chat_id:
                    entry = self._log_delivery(ch.name, "TELEGRAM", alert)
                    t = threading.Thread(
                        target=_deliver_telegram, args=(ch, alert), daemon=True
                    )
                    t.start()
                    self._mark_delivered(entry)

    # ── Delivery log ──────────────────────────────────────────────────────────

    def _log_delivery(
        self, channel_name: str, channel_type: str, alert: AlertFired
    ) -> dict:
        entry = {
            "ts":           alert.ts,
            "channel_name": channel_name,
            "channel_type": channel_type,
            "severity":     alert.severity,
            "rule_name":    alert.rule_name,
            "host":         alert.host,
            "message":      alert.message,
            "status":       "PENDING",
            "error":        "",
        }
        with self._lock:
            self._log.append(entry)
            if len(self._log) > self._log_max:
                self._log = self._log[-self._log_max:]
        return entry

    def _mark_delivered(self, entry: dict) -> None:
        with self._lock:
            entry["status"] = "DELIVERED"

    def _mark_failed(self, entry: dict, error: str) -> None:
        with self._lock:
            entry["status"] = "FAILED"
            entry["error"]  = error

    def retry_delivery(self, entry: dict) -> None:
        """Re-attempt delivery for a failed log entry."""
        ch_name = entry.get("channel_name", "")
        ch_type = entry.get("channel_type", "")
        alert = AlertFired(
            ts=entry.get("ts", 0.0),
            severity=entry.get("severity", "WARNING"),
            rule_name=entry.get("rule_name", ""),
            host=entry.get("host", ""),
            message=entry.get("message", ""),
            rule_type="",
        )
        for ch in self._channels:
            if ch.name == ch_name:
                entry["status"] = "PENDING"
                entry["error"]  = ""
                if isinstance(ch, WebhookChannel) and ch.url:
                    t = threading.Thread(
                        target=_deliver_webhook_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()
                elif isinstance(ch, EmailChannel) and ch.smtp_host and ch.to_addrs:
                    t = threading.Thread(
                        target=_deliver_email_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()
                break

    def get_delivery_log(self) -> List[dict]:
        """Return a copy of the recent delivery log (newest last)."""
        with self._lock:
            return list(self._log)

    def clear_delivery_log(self) -> None:
        with self._lock:
            self._log.clear()


# ── Serialisation helpers (for QSettings persistence) ────────────────────────

def channels_to_dict(channels: List[Channel]) -> List[dict]:
    """Serialise channel list to a JSON-safe list of dicts."""
    out = []
    for ch in channels:
        if isinstance(ch, ToastChannel):
            out.append({"type": "TOAST",    **ch.__dict__})
        elif isinstance(ch, WebhookChannel):
            d = ch.__dict__.copy()
            d.pop("password", None)
            out.append({"type": "WEBHOOK",  **d})
        elif isinstance(ch, EmailChannel):
            d = ch.__dict__.copy()
            d.pop("password", None)
            out.append({"type": "EMAIL",    **d})
        elif isinstance(ch, PushoverChannel):
            d = ch.__dict__.copy()
            d.pop("api_token", None)   # RULE 22-A — never serialise secrets
            d.pop("user_key",  None)
            out.append({"type": "PUSHOVER", **d})
        elif isinstance(ch, NtfyChannel):
            d = ch.__dict__.copy()
            d.pop("access_token", None)
            out.append({"type": "NTFY",     **d})
        elif isinstance(ch, TelegramChannel):
            d = ch.__dict__.copy()
            d.pop("bot_token", None)
            out.append({"type": "TELEGRAM", **d})
    return out


def channels_from_dict(data: List[dict]) -> List[Channel]:
    """Deserialise channel list from QSettings-stored JSON."""
    result: List[Channel] = []
    for d in data:
        t = d.get("type", "").upper()
        d2 = {k: v for k, v in d.items() if k != "type"}
        try:
            if t == "TOAST":
                result.append(ToastChannel(**d2))
            elif t == "WEBHOOK":
                result.append(WebhookChannel(**d2))
            elif t == "EMAIL":
                result.append(EmailChannel(**d2))
            elif t == "PUSHOVER":
                result.append(PushoverChannel(**d2))
            elif t == "NTFY":
                result.append(NtfyChannel(**d2))
            elif t == "TELEGRAM":
                result.append(TelegramChannel(**d2))
        except TypeError:
            pass  # schema mismatch — skip stale entry
    return result

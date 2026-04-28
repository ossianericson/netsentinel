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
    password:     str  = ""             # stored in QSettings by the UI layer
    from_addr:    str  = ""
    to_addrs:     List[str] = field(default_factory=list)
    min_severity: str  = "CRITICAL"
    rule_types:   List[str] = field(default_factory=list)
    timeout_s:    int  = 10


# Union type alias
Channel = ToastChannel | WebhookChannel | EmailChannel


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
                self._log_delivery(ch.name, "TOAST", alert)

            elif isinstance(ch, WebhookChannel):
                if ch.url:
                    t = threading.Thread(
                        target=_deliver_webhook, args=(ch, alert), daemon=True
                    )
                    t.start()
                    self._log_delivery(ch.name, "WEBHOOK", alert)

            elif isinstance(ch, EmailChannel):
                if ch.smtp_host and ch.to_addrs:
                    t = threading.Thread(
                        target=_deliver_email, args=(ch, alert), daemon=True
                    )
                    t.start()
                    self._log_delivery(ch.name, "EMAIL", alert)

    # ── Delivery log ──────────────────────────────────────────────────────────

    def _log_delivery(self, channel_name: str, channel_type: str, alert: AlertFired) -> None:
        entry = {
            "ts":           alert.ts,
            "channel_name": channel_name,
            "channel_type": channel_type,
            "severity":     alert.severity,
            "rule_name":    alert.rule_name,
            "host":         alert.host,
            "message":      alert.message,
        }
        self._log.append(entry)
        if len(self._log) > self._log_max:
            self._log = self._log[-self._log_max:]

    def get_delivery_log(self) -> List[dict]:
        """Return a copy of the recent delivery log (newest last)."""
        return list(self._log)

    def clear_delivery_log(self) -> None:
        self._log.clear()


# ── Serialisation helpers (for QSettings persistence) ────────────────────────

def channels_to_dict(channels: List[Channel]) -> List[dict]:
    """Serialise channel list to a JSON-safe list of dicts."""
    out = []
    for ch in channels:
        if isinstance(ch, ToastChannel):
            out.append({"type": "TOAST",   **ch.__dict__})
        elif isinstance(ch, WebhookChannel):
            d = ch.__dict__.copy()
            d.pop("password", None)  # never serialise passwords here
            out.append({"type": "WEBHOOK", **d})
        elif isinstance(ch, EmailChannel):
            d = ch.__dict__.copy()
            d.pop("password", None)
            out.append({"type": "EMAIL",   **d})
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
        except TypeError:
            pass  # schema mismatch — skip stale entry
    return result

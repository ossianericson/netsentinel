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
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from modules.alert_engine import AlertFired
from modules.utils import get_app_data_dir
from modules.notification_channels import (
    _deliver_webhook_tracked, _deliver_email_tracked,
    _deliver_pushover_tracked, _deliver_ntfy_tracked, _deliver_telegram_tracked,
)

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


def _matches_channel(alert: AlertFired, min_severity: str, rule_types: List[str]) -> bool:
    """Return True if the alert should be dispatched to a channel with these filters."""
    if not _severity_gte(alert.severity, min_severity):
        return False
    if rule_types and alert.rule_type not in rule_types:
        return False
    return True


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

        # Snooze registry: rule_name → expiry Unix timestamp (float); 0 = forever
        self._snooze: Dict[str, float] = {}
        self._restore_snoozes()

    # ── Snooze management ─────────────────────────────────────────────────────

    @staticmethod
    def _snooze_path() -> Path:
        return get_app_data_dir() / "notification_snoozes.json"

    def _restore_snoozes(self) -> None:
        """Restore persisted snooze state from JSON file on startup."""
        try:
            data: dict = json.loads(self._snooze_path().read_text("utf-8"))
            now = time.time()
            for rule_name, expiry in data.items():
                try:
                    expiry = float(expiry)
                except (TypeError, ValueError):
                    continue
                if expiry == 0 or expiry > now:
                    self._snooze[rule_name] = expiry
        except Exception:
            pass

    def _persist_snoozes(self) -> None:
        """Write current snooze registry to disk."""
        try:
            path = self._snooze_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._snooze), encoding="utf-8")
        except Exception:
            pass

    def set_snooze(self, rule_name: str, until_ts: float) -> None:
        """Snooze rule_name until until_ts (Unix seconds). Pass 0 for 'forever'."""
        with self._lock:
            self._snooze[rule_name] = until_ts
            snapshot = dict(self._snooze)
        try:
            path = self._snooze_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot), encoding="utf-8")
        except Exception:
            pass

    def clear_snooze(self, rule_name: str) -> None:
        with self._lock:
            self._snooze.pop(rule_name, None)
            snapshot = dict(self._snooze)
        try:
            path = self._snooze_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(snapshot), encoding="utf-8")
        except Exception:
            pass

    def get_snooze_expiry(self, rule_name: str) -> Optional[float]:
        """Return expiry ts for snoozed rule, 0 if forever, None if not snoozed."""
        with self._lock:
            return self._snooze.get(rule_name)

    def get_all_snoozes(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._snooze)

    def _is_snoozed(self, rule_name: str) -> bool:
        expiry = self._snooze.get(rule_name)
        if expiry is None:
            return False
        return expiry == 0 or time.time() < expiry

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
            snoozed = self._is_snoozed(alert.rule_name)

        if snoozed:
            return

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
                entry = self._log_delivery(ch.name, "PUSHOVER", alert)
                t = threading.Thread(
                    target=_deliver_pushover_tracked,
                    args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                    daemon=True,
                )
                t.start()

            elif isinstance(ch, NtfyChannel):
                entry = self._log_delivery(ch.name, "NTFY", alert)
                t = threading.Thread(
                    target=_deliver_ntfy_tracked,
                    args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                    daemon=True,
                )
                t.start()

            elif isinstance(ch, TelegramChannel):
                entry = self._log_delivery(ch.name, "TELEGRAM", alert)
                t = threading.Thread(
                    target=_deliver_telegram_tracked,
                    args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                    daemon=True,
                )
                t.start()

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
                elif isinstance(ch, PushoverChannel):
                    t = threading.Thread(
                        target=_deliver_pushover_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()
                elif isinstance(ch, NtfyChannel):
                    t = threading.Thread(
                        target=_deliver_ntfy_tracked,
                        args=(ch, alert, entry, self._mark_delivered, self._mark_failed),
                        daemon=True,
                    )
                    t.start()
                elif isinstance(ch, TelegramChannel):
                    t = threading.Thread(
                        target=_deliver_telegram_tracked,
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

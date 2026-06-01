"""
Notification delivery helpers — per-channel send functions.

Extracted from modules/notification_router.py (S20-3 sprint split).
All public names remain importable from modules.notification_router for
backwards compatibility via re-exports in that module.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable

from modules.alert_engine import AlertFired


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


# ── Delivery helpers (run in background threads) ──────────────────────────────

def _deliver_webhook(channel, alert: AlertFired) -> None:
    payload = json.dumps(_build_payload(alert)).encode()
    headers = {"Content-Type": "application/json", **channel.headers}
    req = urllib.request.Request(channel.url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=channel.timeout_s):
            pass
    except (urllib.error.URLError, OSError):
        pass


def _deliver_email(channel, alert: AlertFired) -> None:
    from email.mime.text import MIMEText
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


def _deliver_pushover(channel, alert: AlertFired) -> None:
    """POST to the Pushover API. Requires api_token + user_key."""
    if not channel.api_token or not channel.user_key:
        return
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


def _deliver_ntfy(channel, alert: AlertFired) -> None:
    """POST to ntfy.sh (or self-hosted). topic_url is the full topic endpoint."""
    if not channel.topic_url:
        return
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


def _deliver_telegram(channel, alert: AlertFired) -> None:
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

def _deliver_pushover_tracked(
    channel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    """POST to Pushover API with success/failure callbacks."""
    if not channel.api_token or not channel.user_key:
        on_err(entry, "Pushover not configured (missing api_token or user_key)")
        return
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
            on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))


def _deliver_ntfy_tracked(
    channel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    """POST to ntfy.sh (or self-hosted) with success/failure callbacks."""
    if not channel.topic_url:
        on_err(entry, "ntfy not configured (missing topic_url)")
        return
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
            on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))


def _deliver_telegram_tracked(
    channel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    """POST to Telegram Bot API with success/failure callbacks."""
    if not channel.bot_token or not channel.chat_id:
        on_err(entry, "Telegram not configured (missing bot_token or chat_id)")
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
            on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))


def _deliver_webhook_tracked(
    channel,
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
    channel,
    alert: AlertFired,
    entry: dict,
    on_ok: Callable,
    on_err: Callable,
) -> None:
    if not channel.smtp_host or not channel.to_addrs:
        on_err(entry, "SMTP not configured")
        return
    import smtplib as _smtplib
    import ssl as _ssl
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
            with _smtplib.SMTP(channel.smtp_host, channel.smtp_port, timeout=channel.timeout_s) as s:
                s.ehlo(); s.starttls(context=ctx)
                if channel.username:
                    s.login(channel.username, channel.password)
                s.sendmail(msg["From"], channel.to_addrs, msg.as_string())
        else:
            with _smtplib.SMTP_SSL(channel.smtp_host, channel.smtp_port, context=ctx, timeout=channel.timeout_s) as s:
                if channel.username:
                    s.login(channel.username, channel.password)
                s.sendmail(msg["From"], channel.to_addrs, msg.as_string())
        on_ok(entry)
    except Exception as exc:
        on_err(entry, str(exc))

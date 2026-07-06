"""Tests for modules/notification_channels.py — see also test_sprint20_splits.py."""
from unittest.mock import MagicMock, patch


def test_import():
    from modules import notification_channels as m
    assert hasattr(m, "_build_payload")
    assert hasattr(m, "_deliver_webhook")
    assert hasattr(m, "_deliver_email")
    assert hasattr(m, "_deliver_pushover")
    assert hasattr(m, "_deliver_ntfy")
    assert hasattr(m, "_deliver_telegram")
    assert hasattr(m, "_deliver_webhook_tracked")
    assert hasattr(m, "_deliver_email_tracked")
    assert hasattr(m, "_deliver_pushover_tracked")
    assert hasattr(m, "_deliver_ntfy_tracked")
    assert hasattr(m, "_deliver_telegram_tracked")


def test_build_payload_all_fields():
    from modules.alert_engine import AlertFired
    from modules.notification_channels import _build_payload
    a = AlertFired(
        rule_name="Host Down", rule_type="HOST_DOWN",
        host="192.168.1.1", message="Host is down",
        severity="CRITICAL", ts=1700000000, value=None,
    )
    p = _build_payload(a)
    assert set(p.keys()) >= {"ts", "rule_name", "rule_type", "host", "severity", "message", "value"}
    assert p["ts"] == 1700000000
    assert p["severity"] == "CRITICAL"


def test_deliver_functions_callable():
    from modules import notification_channels as nc
    for fn_name in ["_deliver_webhook", "_deliver_email", "_deliver_pushover",
                    "_deliver_ntfy", "_deliver_telegram",
                    "_deliver_pushover_tracked", "_deliver_ntfy_tracked",
                    "_deliver_telegram_tracked"]:
        assert callable(getattr(nc, fn_name))


# ── send_plain_email (S8-3) ────────────────────────────────────────────────

def test_send_plain_email_false_when_no_smtp_host():
    from modules.notification_channels import send_plain_email
    channel = MagicMock(smtp_host="", to_addrs=["a@b.com"])
    assert send_plain_email(channel, "Subject", "Body") is False


def test_send_plain_email_false_when_no_recipients():
    from modules.notification_channels import send_plain_email
    channel = MagicMock(smtp_host="smtp.example.com", to_addrs=[])
    assert send_plain_email(channel, "Subject", "Body") is False


def test_send_plain_email_success_via_starttls():
    from modules.notification_channels import send_plain_email
    channel = MagicMock(
        smtp_host="smtp.example.com", smtp_port=587, use_tls=True,
        username="user", password="pass", from_addr="from@example.com",
        to_addrs=["to@example.com"], timeout_s=10,
    )
    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__.return_value = MagicMock()
        assert send_plain_email(channel, "Weekly Report", "body text") is True
        mock_smtp.assert_called_once()


def test_send_plain_email_failure_returns_false():
    import smtplib
    from modules.notification_channels import send_plain_email
    channel = MagicMock(
        smtp_host="smtp.example.com", smtp_port=587, use_tls=True,
        username="user", password="pass", from_addr="from@example.com",
        to_addrs=["to@example.com"], timeout_s=10,
    )
    with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("boom")):
        assert send_plain_email(channel, "Weekly Report", "body text") is False


def _make_alert():
    from modules.alert_engine import AlertFired
    return AlertFired(
        rule_name="Test", rule_type="RTT_THRESHOLD",
        host="10.0.0.1", message="latency high",
        severity="WARNING", ts=1700000000, value=None,
    )


# ── Tracked Pushover ──────────────────────────────────────────────────────────

def test_pushover_tracked_calls_on_ok_on_success():
    from modules.notification_channels import _deliver_pushover_tracked
    channel = MagicMock(api_token="tok", user_key="key", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        _deliver_pushover_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_called_once_with(entry)
    on_err.assert_not_called()


def test_pushover_tracked_calls_on_err_on_network_failure():
    from modules.notification_channels import _deliver_pushover_tracked
    import urllib.error
    channel = MagicMock(api_token="tok", user_key="key", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        _deliver_pushover_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()
    assert "timeout" in on_err.call_args[0][1]


def test_pushover_tracked_calls_on_err_when_not_configured():
    from modules.notification_channels import _deliver_pushover_tracked
    channel = MagicMock(api_token="", user_key="", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    _deliver_pushover_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()


# ── Tracked ntfy ──────────────────────────────────────────────────────────────

def test_ntfy_tracked_calls_on_ok_on_success():
    from modules.notification_channels import _deliver_ntfy_tracked
    channel = MagicMock(topic_url="https://ntfy.sh/test", access_token="", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        _deliver_ntfy_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_called_once_with(entry)
    on_err.assert_not_called()


def test_ntfy_tracked_calls_on_err_on_failure():
    from modules.notification_channels import _deliver_ntfy_tracked
    import urllib.error
    channel = MagicMock(topic_url="https://ntfy.sh/test", access_token="", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        _deliver_ntfy_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()


def test_ntfy_tracked_on_err_when_no_topic_url():
    from modules.notification_channels import _deliver_ntfy_tracked
    channel = MagicMock(topic_url="", access_token="", timeout_s=5)
    on_ok = MagicMock()
    on_err = MagicMock()
    _deliver_ntfy_tracked(channel, _make_alert(), {}, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()


# ── Tracked Telegram ──────────────────────────────────────────────────────────

def test_telegram_tracked_calls_on_ok_on_success():
    from modules.notification_channels import _deliver_telegram_tracked
    channel = MagicMock(bot_token="tok:abc", chat_id="12345", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        _deliver_telegram_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_called_once_with(entry)
    on_err.assert_not_called()


def test_telegram_tracked_calls_on_err_on_failure():
    from modules.notification_channels import _deliver_telegram_tracked
    import urllib.error
    channel = MagicMock(bot_token="tok:abc", chat_id="12345", timeout_s=5)
    entry = {}
    on_ok = MagicMock()
    on_err = MagicMock()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("forbidden")):
        _deliver_telegram_tracked(channel, _make_alert(), entry, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()
    assert "forbidden" in on_err.call_args[0][1]


def test_telegram_tracked_on_err_when_not_configured():
    from modules.notification_channels import _deliver_telegram_tracked
    channel = MagicMock(bot_token="", chat_id="", timeout_s=5)
    on_ok = MagicMock()
    on_err = MagicMock()
    _deliver_telegram_tracked(channel, _make_alert(), {}, on_ok, on_err)
    on_ok.assert_not_called()
    on_err.assert_called_once()

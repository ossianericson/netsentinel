"""
Tests for modules/notification_router.py

Covers:
  - Severity ordering (_severity_gte)
  - Channel matching (_matches_channel)
  - Router dispatch to matching channels only
  - Toast callback invoked / not invoked based on severity
  - Delivery log: entries recorded, cleared, get_delivery_log
  - set_channels / get_channels
  - channels_to_dict / channels_from_dict serialisation
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from modules.alert_engine import AlertFired
from modules.notification_router import (
    EmailChannel,
    NotificationRouter,
    ToastChannel,
    WebhookChannel,
    _matches_channel,
    _severity_gte,
    channels_from_dict,
    channels_to_dict,
)


def _alert(severity: str = "WARNING", rule_type: str = "RTT_THRESHOLD", host: str = "10.0.0.1") -> AlertFired:
    return AlertFired(
        rule_name="Test Rule",
        rule_type=rule_type,
        host=host,
        message="test message",
        severity=severity,
        ts=int(time.time()),
    )


class TestSeverityOrdering(unittest.TestCase):
    def test_info_lt_warning(self):
        assert _severity_gte("WARNING", "INFO")
        assert not _severity_gte("INFO", "WARNING")

    def test_warning_lt_critical(self):
        assert _severity_gte("CRITICAL", "WARNING")
        assert not _severity_gte("WARNING", "CRITICAL")

    def test_same_level(self):
        for lvl in ("INFO", "WARNING", "CRITICAL"):
            assert _severity_gte(lvl, lvl)

    def test_unknown_defaults_to_zero(self):
        assert _severity_gte("INFO", "UNKNOWN")


class TestMatchesChannel(unittest.TestCase):
    def test_severity_filter_pass(self):
        assert _matches_channel(_alert("CRITICAL"), "WARNING", [])

    def test_severity_filter_block(self):
        assert not _matches_channel(_alert("INFO"), "CRITICAL", [])

    def test_rule_type_filter_match(self):
        assert _matches_channel(_alert("CRITICAL", "HOST_DOWN"), "WARNING", ["HOST_DOWN"])

    def test_rule_type_filter_no_match(self):
        assert not _matches_channel(_alert("CRITICAL", "HOST_DOWN"), "WARNING", ["CERT_EXPIRY"])

    def test_empty_rule_types_passes_all(self):
        assert _matches_channel(_alert("CRITICAL", "ANY_TYPE"), "INFO", [])


class TestRouterDispatch(unittest.TestCase):
    def _make_router(self):
        r = NotificationRouter()
        r.set_channels([ToastChannel(enabled=True, min_severity="WARNING")])
        return r

    def test_toast_callback_called_on_match(self):
        r = self._make_router()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.dispatch(_alert("CRITICAL"))
        cb.assert_called_once()

    def test_toast_callback_not_called_below_threshold(self):
        r = self._make_router()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.dispatch(_alert("INFO"))
        cb.assert_not_called()

    def test_toast_disabled_not_called(self):
        r = NotificationRouter()
        r.set_channels([ToastChannel(enabled=False)])
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.dispatch(_alert("CRITICAL"))
        cb.assert_not_called()

    def test_delivery_log_recorded(self):
        r = self._make_router()
        r.set_toast_callback(MagicMock())
        r.dispatch(_alert("CRITICAL"))
        log = r.get_delivery_log()
        assert len(log) == 1
        assert log[0]["channel_type"] == "TOAST"
        assert log[0]["severity"] == "CRITICAL"

    def test_delivery_log_cleared(self):
        r = self._make_router()
        r.set_toast_callback(MagicMock())
        r.dispatch(_alert("WARNING"))
        r.clear_delivery_log()
        assert r.get_delivery_log() == []

    def test_webhook_channel_disabled_skipped(self):
        r = NotificationRouter()
        r.set_channels([WebhookChannel(enabled=False, url="http://example.com")])
        r.dispatch(_alert("CRITICAL"))
        assert r.get_delivery_log() == []

    def test_webhook_no_url_skipped(self):
        r = NotificationRouter()
        r.set_channels([WebhookChannel(enabled=True, url="")])
        r.dispatch(_alert("CRITICAL"))
        assert r.get_delivery_log() == []

    def test_email_no_host_skipped(self):
        r = NotificationRouter()
        r.set_channels([EmailChannel(enabled=True, smtp_host="", to_addrs=["a@b.com"])])
        r.dispatch(_alert("CRITICAL"))
        assert r.get_delivery_log() == []

    def test_multiple_channels_all_fire(self):
        r = NotificationRouter()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.set_channels([
            ToastChannel(enabled=True, min_severity="INFO"),
            WebhookChannel(enabled=True, url="http://example.com", min_severity="INFO"),
        ])
        # Override thread delivery to run synchronously for testing
        class SyncThread:
            def __init__(self, target, args=(), daemon=True, **kw):
                self._target = target
                self._args = args

            def start(self):
                self._target(*self._args)

        with patch("modules.notification_router.threading") as mock_th:
            mock_th.Thread.side_effect = SyncThread
            with patch("modules.notification_channels._deliver_webhook_tracked"):
                r.dispatch(_alert("WARNING"))

        log = r.get_delivery_log()
        assert len(log) == 2

    def test_log_capped_at_max(self):
        r = NotificationRouter()
        r._log_max = 5
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.set_channels([ToastChannel(enabled=True, min_severity="INFO")])
        for _ in range(10):
            r.dispatch(_alert("INFO"))
        assert len(r.get_delivery_log()) == 5


class TestSetGetChannels(unittest.TestCase):
    def test_set_and_get_channels(self):
        r = NotificationRouter()
        channels = [ToastChannel(), WebhookChannel(url="http://x.com")]
        r.set_channels(channels)
        assert len(r.get_channels()) == 2
        assert isinstance(r.get_channels()[1], WebhookChannel)


class TestSerialization(unittest.TestCase):
    def test_roundtrip_toast(self):
        ch = ToastChannel(enabled=True, min_severity="CRITICAL", rule_types=["HOST_DOWN"])
        d = channels_to_dict([ch])
        restored = channels_from_dict(d)
        assert len(restored) == 1
        assert isinstance(restored[0], ToastChannel)
        assert restored[0].min_severity == "CRITICAL"
        assert restored[0].rule_types == ["HOST_DOWN"]

    def test_roundtrip_webhook(self):
        ch = WebhookChannel(enabled=True, url="https://hooks.example.com", min_severity="WARNING")
        d = channels_to_dict([ch])
        restored = channels_from_dict(d)
        assert isinstance(restored[0], WebhookChannel)
        assert restored[0].url == "https://hooks.example.com"

    def test_roundtrip_email(self):
        ch = EmailChannel(
            enabled=False, smtp_host="smtp.gmail.com", smtp_port=587,
            username="user@gmail.com", from_addr="user@gmail.com",
            to_addrs=["admin@example.com"], min_severity="CRITICAL",
        )
        d = channels_to_dict([ch])
        restored = channels_from_dict(d)
        assert isinstance(restored[0], EmailChannel)
        assert restored[0].smtp_host == "smtp.gmail.com"
        assert restored[0].to_addrs == ["admin@example.com"]

    def test_password_not_serialised(self):
        """Passwords must NOT appear in the serialised dict."""
        ch = EmailChannel(enabled=True, smtp_host="smtp.x.com", password="s3cr3t")
        d = channels_to_dict([ch])
        serialised = str(d)
        assert "s3cr3t" not in serialised


if __name__ == "__main__":
    unittest.main()

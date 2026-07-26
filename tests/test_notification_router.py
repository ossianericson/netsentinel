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
    PushoverChannel,
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

    def test_default_toast_channel_is_disabled(self):
        """Strict opt-in by construction -- a freshly constructed router must
        never deliver a balloon before NotificationsPage._apply_to_router()
        has run, even for a CRITICAL alert."""
        r = NotificationRouter()
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.dispatch(_alert("CRITICAL"))
        cb.assert_not_called()

    def test_toast_disabled_not_called(self):
        r = NotificationRouter()
        r.set_channels([ToastChannel(enabled=False)])
        cb = MagicMock()
        r.set_toast_callback(cb)
        r.dispatch(_alert("CRITICAL"))
        cb.assert_not_called()

    def test_toast_callback_exception_marks_delivery_failed(self):
        """A raised toast callback exception must record status=FAILED, not
        DELIVERED — the previous code swallowed the exception and then
        unconditionally called _mark_delivered regardless of outcome, so a
        toast that never reached the user still showed as delivered with no
        error trail."""
        r = self._make_router()
        r.set_toast_callback(MagicMock(side_effect=RuntimeError("toast api unavailable")))
        r.dispatch(_alert("CRITICAL"))
        log = r.get_delivery_log()
        assert len(log) == 1
        assert log[0]["status"] == "FAILED", (
            f"Expected status='FAILED' when the toast callback raises; "
            f"got '{log[0]['status']}' — dispatch() is swallowing the "
            f"exception and marking it DELIVERED anyway"
        )
        assert "toast api unavailable" in log[0].get("error", "")

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


class TestDispatchEscalation(unittest.TestCase):
    """F-21: check_escalations() re-delivery via dispatch_escalation()."""

    def test_unknown_channel_name_returns_false(self):
        r = NotificationRouter()
        assert r.dispatch_escalation(_alert("INFO"), "Carrier Pigeon") is False

    def test_no_configured_channel_of_that_type_returns_false(self):
        r = NotificationRouter()
        r.set_channels([ToastChannel(enabled=True)])
        assert r.dispatch_escalation(_alert("INFO"), "Email") is False

    def test_disabled_channel_of_matching_type_returns_false(self):
        r = NotificationRouter()
        r.set_channels([EmailChannel(enabled=False, smtp_host="smtp.x.com", to_addrs=["a@b.com"])])
        assert r.dispatch_escalation(_alert("INFO"), "Email") is False

    def test_bypasses_severity_gate(self):
        """Escalation must fire even for an INFO alert against a channel whose
        min_severity is CRITICAL — that's the whole point of escalating."""
        r = NotificationRouter()
        r.set_channels([PushoverChannel(
            enabled=True, api_token="t", user_key="u", min_severity="CRITICAL",
        )])
        with patch("modules.notification_router._deliver_pushover_tracked"):
            delivered = r.dispatch_escalation(_alert("INFO"), "Pushover")
        assert delivered is True
        log = r.get_delivery_log()
        assert len(log) == 1
        assert log[0]["channel_type"] == "PUSHOVER"

    def test_delivers_via_configured_email_channel(self):
        r = NotificationRouter()
        r.set_channels([EmailChannel(enabled=True, smtp_host="smtp.x.com", to_addrs=["a@b.com"])])
        with patch("modules.notification_router._deliver_email_tracked"):
            delivered = r.dispatch_escalation(_alert("INFO"), "Email")
        assert delivered is True


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


class TestSnoozeJsonPersistence(unittest.TestCase):
    """Snooze state must round-trip through a JSON file — no QSettings."""

    def _make_router_with_tmp(self, tmp_path):
        r = NotificationRouter.__new__(NotificationRouter)
        r._channels = []
        r._toast_cb = None
        r._lock = __import__("threading").Lock()
        r._log = []
        r._log_max = 500
        r._snooze = {}
        with patch.object(NotificationRouter, "_snooze_path", return_value=tmp_path):
            r._restore_snoozes()
        return r

    def test_set_snooze_writes_json(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "snoozes.json"
            r = NotificationRouter()
            with patch.object(type(r), "_snooze_path", staticmethod(lambda: path)):
                r.set_snooze("rule_a", 9999999999.0)
            data = json.loads(path.read_text())
            assert "rule_a" in data
            assert data["rule_a"] == 9999999999.0

    def test_clear_snooze_removes_key(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "snoozes.json"
            r = NotificationRouter()
            with patch.object(type(r), "_snooze_path", staticmethod(lambda: path)):
                r.set_snooze("rule_b", 9999999999.0)
                r.clear_snooze("rule_b")
            data = json.loads(path.read_text())
            assert "rule_b" not in data

    def test_restore_snoozes_reads_json(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "snoozes.json"
            path.write_text(json.dumps({"rule_c": 9999999999.0}), encoding="utf-8")
            r = NotificationRouter()
            r._snooze = {}
            with patch.object(type(r), "_snooze_path", staticmethod(lambda: path)):
                r._restore_snoozes()
            assert "rule_c" in r._snooze

    def test_expired_snooze_not_restored(self):
        import tempfile, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "snoozes.json"
            path.write_text(json.dumps({"old_rule": 1.0}), encoding="utf-8")
            r = NotificationRouter()
            r._snooze = {}
            with patch.object(type(r), "_snooze_path", staticmethod(lambda: path)):
                r._restore_snoozes()
            assert "old_rule" not in r._snooze

    def test_no_pyqt_import_in_snooze_methods(self):
        """Snooze methods must not lazily import PyQt6.QtCore.QSettings."""
        import inspect
        for method_name in ("_restore_snoozes", "set_snooze", "clear_snooze"):
            src = inspect.getsource(getattr(NotificationRouter, method_name))
            assert "import QSettings" not in src and "QSettings(" not in src, (
                f"{method_name} still uses QSettings"
            )


class TestRoutingMatrixSerialization(unittest.TestCase):
    """Phase 6 -- per-rule x per-channel routing matrix. Additive, self-gating:
    absent notif/rule_routing -> {} -> every rule_types=[] -> today's
    behaviour byte-for-byte."""

    def test_roundtrip_subset(self):
        from modules.notification_router import routing_matrix_to_json, routing_matrix_from_json
        matrix = {"email": ["NEW_CVE", "HOST_DOWN"]}
        restored = routing_matrix_from_json(routing_matrix_to_json(matrix))
        assert restored == {"email": ["NEW_CVE", "HOST_DOWN"]}

    def test_all_rule_types_selected_collapses_to_empty_list(self):
        from modules.notification_router import routing_matrix_to_json
        from modules.alert_types import RULE_TYPES
        import json as _json
        raw = routing_matrix_to_json({"toast": sorted(RULE_TYPES)})
        assert _json.loads(raw) == {"toast": []}

    def test_unknown_rule_type_dropped_on_load(self):
        from modules.notification_router import routing_matrix_from_json
        import json as _json
        raw = _json.dumps({"email": ["HOST_DOWN", "NOT_A_REAL_RULE_TYPE"]})
        assert routing_matrix_from_json(raw) == {"email": ["HOST_DOWN"]}

    def test_unknown_channel_key_dropped_on_load(self):
        from modules.notification_router import routing_matrix_from_json
        import json as _json
        raw = _json.dumps({"carrier_pigeon": ["HOST_DOWN"], "email": []})
        assert routing_matrix_from_json(raw) == {"email": []}

    def test_garbage_json_returns_empty_dict(self):
        from modules.notification_router import routing_matrix_from_json
        assert routing_matrix_from_json("{not valid json") == {}

    def test_missing_input_returns_empty_dict(self):
        from modules.notification_router import routing_matrix_from_json
        assert routing_matrix_from_json("") == {}
        assert routing_matrix_from_json(None) == {}

    def test_empty_list_channel_round_trips_as_empty(self):
        """An empty selection stored for a channel round-trips as [] --
        _matches_channel() reads that as 'no filter', matching the pre-Phase-6
        default for every channel that never touches this card."""
        from modules.notification_router import routing_matrix_to_json, routing_matrix_from_json
        restored = routing_matrix_from_json(routing_matrix_to_json({"webhook": []}))
        assert restored == {"webhook": []}


if __name__ == "__main__":
    unittest.main()

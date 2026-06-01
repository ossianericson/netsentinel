"""Tests for modules/notification_channels.py — see also test_sprint20_splits.py."""


def test_import():
    import modules.notification_channels as m
    assert hasattr(m, "_build_payload")
    assert hasattr(m, "_deliver_webhook")
    assert hasattr(m, "_deliver_email")
    assert hasattr(m, "_deliver_pushover")
    assert hasattr(m, "_deliver_ntfy")
    assert hasattr(m, "_deliver_telegram")
    assert hasattr(m, "_deliver_webhook_tracked")
    assert hasattr(m, "_deliver_email_tracked")


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
    import modules.notification_channels as nc
    for fn_name in ["_deliver_webhook", "_deliver_email", "_deliver_pushover",
                    "_deliver_ntfy", "_deliver_telegram"]:
        assert callable(getattr(nc, fn_name))

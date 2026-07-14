"""
Tests for modules/automation_hooks.py
"""
import sys
import threading
from unittest.mock import patch

import pytest

from modules.automation_hooks import (
    AutomationEngine, AutomationRule, Trigger,
    _expand_vars, _build_argv,
    template_wol, template_log_to_file, get_engine,
    automation_event_from_alert,
)


# ── AutomationRule dataclass ──────────────────────────────────────────────────

def test_rule_defaults():
    r = AutomationRule()
    assert r.trigger == Trigger.DEVICE_JOINED.value
    assert r.enabled is True
    assert r.match_value == "*"
    assert r.id  # non-empty UUID fragment


def test_rule_fields():
    r = AutomationRule(
        name="Test",
        trigger=Trigger.DEVICE_LEFT.value,
        match_field="mac",
        match_value="AA:BB:CC:DD:EE:FF",
        script_path="/usr/bin/python3",
        args="-c 'print(1)'",
    )
    assert r.trigger == "device_left"
    assert r.match_value == "AA:BB:CC:DD:EE:FF"


# ── Trigger enum ──────────────────────────────────────────────────────────────

def test_trigger_values():
    assert Trigger.DEVICE_JOINED.value == "device_joined"
    assert Trigger.DEVICE_LEFT.value   == "device_left"
    assert Trigger.ALERT_FIRED.value   == "alert_fired"


# ── Helper functions ──────────────────────────────────────────────────────────

def test_expand_vars_basic():
    result = _expand_vars("-Target $MAC -IP $IP", {"mac": "AA:BB", "ip": "10.0.0.1"})
    assert result == "-Target AA:BB -IP 10.0.0.1"


def test_expand_vars_no_match():
    result = _expand_vars("static-arg", {"mac": "AA:BB"})
    assert result == "static-arg"


def test_expand_vars_empty():
    assert _expand_vars("", {"mac": "AA:BB"}) == ""


def test_build_argv_simple():
    argv = _build_argv("/usr/bin/python3", "-c 'print(1)'")
    assert argv[0] == "/usr/bin/python3"
    assert len(argv) > 1


def test_build_argv_no_args():
    argv = _build_argv("/bin/bash", "")
    assert argv == ["/bin/bash"]


# ── AutomationEngine persistence ─────────────────────────────────────────────

@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "modules.automation_hooks.get_app_data_dir",
        lambda: tmp_path,
    )
    return AutomationEngine()


def test_engine_starts_empty(engine):
    assert engine.get_rules() == []


def test_engine_add_and_get(engine):
    r = AutomationRule(name="MyRule")
    engine.add_rule(r)
    rules = engine.get_rules()
    assert len(rules) == 1
    assert rules[0].name == "MyRule"


def test_engine_update(engine):
    r = AutomationRule(name="Original")
    engine.add_rule(r)
    r.name = "Updated"
    engine.update_rule(r)
    assert engine.get_rules()[0].name == "Updated"


def test_engine_delete(engine):
    r = AutomationRule(name="ToDelete")
    engine.add_rule(r)
    engine.delete_rule(r.id)
    assert engine.get_rules() == []


def test_engine_set_enabled(engine):
    r = AutomationRule(name="X", enabled=True)
    engine.add_rule(r)
    engine.set_enabled(r.id, False)
    assert engine.get_rules()[0].enabled is False


def test_engine_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.automation_hooks.get_app_data_dir", lambda: tmp_path)
    e1 = AutomationEngine()
    r = AutomationRule(name="Persist", trigger=Trigger.ALERT_FIRED.value)
    e1.add_rule(r)
    # Load fresh instance
    e2 = AutomationEngine()
    rules = e2.get_rules()
    assert len(rules) == 1
    assert rules[0].name == "Persist"
    assert rules[0].trigger == "alert_fired"


# ── AutomationEngine.evaluate — matching logic ────────────────────────────────

def test_evaluate_matches_wildcard(engine):
    called = threading.Event()
    def fake_run(rule, event_data, on_log):
        called.set()
    engine.add_rule(AutomationRule(
        name="Wild", trigger="device_joined", match_field="any", match_value="*",
        script_path=sys.executable, args="-c pass",
    ))
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate("device_joined", {"mac": "AA:BB"})
    assert called.is_set()


def test_evaluate_matches_mac(engine):
    called = threading.Event()
    def fake_run(rule, event_data, on_log):
        called.set()
    engine.add_rule(AutomationRule(
        name="MAC", trigger="device_joined", match_field="mac",
        match_value="aa:bb:cc:dd:ee:ff",
        script_path=sys.executable,
    ))
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate("device_joined", {"mac": "aa:bb:cc:dd:ee:ff"})
    assert called.is_set()


def test_evaluate_no_match(engine):
    called = threading.Event()
    def fake_run(rule, event_data, on_log):
        called.set()
    engine.add_rule(AutomationRule(
        name="MAC", trigger="device_joined", match_field="mac",
        match_value="11:22:33:44:55:66",
        script_path=sys.executable,
    ))
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate("device_joined", {"mac": "aa:bb:cc:dd:ee:ff"})
    assert not called.is_set()


def test_evaluate_wrong_trigger(engine):
    called = threading.Event()
    def fake_run(*a): called.set()
    engine.add_rule(AutomationRule(
        name="T", trigger="device_left", match_field="any",
        script_path=sys.executable,
    ))
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate("device_joined", {"mac": "aa:bb"})
    assert not called.is_set()


def test_evaluate_disabled_rule_skipped(engine):
    called = threading.Event()
    def fake_run(*a): called.set()
    engine.add_rule(AutomationRule(
        name="Dis", trigger="device_joined", match_field="any",
        script_path=sys.executable, enabled=False,
    ))
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate("device_joined", {"mac": "aa:bb"})
    assert not called.is_set()


# ── Script execution ──────────────────────────────────────────────────────────

def test_run_rule_no_script(engine):
    """Rule with empty script_path logs and returns without raising."""
    logs = []
    rule = AutomationRule(name="NoScript", trigger="device_joined", script_path="")
    engine._run_rule(rule, {}, lambda rid, s, t: logs.append(t))
    assert any("No script" in l for l in logs)


def test_run_rule_missing_binary(engine):
    """Rule with nonexistent script logs 'not found' error."""
    logs = []
    rule = AutomationRule(
        name="Missing", trigger="device_joined",
        script_path="/nonexistent/binary_that_does_not_exist_xyz",
    )
    engine._run_rule(rule, {}, lambda rid, s, t: logs.append(t))
    assert any("not found" in l.lower() or "error" in l.lower() for l in logs)


def test_run_rule_executes_python(engine):
    """Rule that runs a Python one-liner; stdout should arrive via on_log."""
    logs = []
    rule = AutomationRule(
        name="Echo", trigger="device_joined",
        script_path=sys.executable,
        args="-c \"print('automation_ok')\"",
    )
    engine._run_rule(rule, {}, lambda rid, s, t: logs.append(t))
    assert any("automation_ok" in l for l in logs)


# ── Webhook dispatch (F-37) ───────────────────────────────────────────────────
# Automation Hooks previously had no webhook capability at all -- AutomationRule
# had no URL field, only script_path. This covers the new webhook_url field and
# its POST dispatch in _run_rule()/_send_webhook().

def test_rule_webhook_url_defaults_empty():
    assert AutomationRule().webhook_url == ""


def test_run_rule_no_script_no_webhook_skips(engine):
    logs = []
    rule = AutomationRule(name="Empty", trigger="device_joined", script_path="", webhook_url="")
    engine._run_rule(rule, {}, lambda rid, s, t: logs.append(t))
    assert any("No script or webhook" in l for l in logs)


def test_run_rule_webhook_only_posts_and_skips_script(engine):
    """A rule with only a webhook configured must not hit the 'no script
    configured' path -- it should POST and stop, without touching subprocess."""
    logs = []
    rule = AutomationRule(
        name="Hook", trigger="device_joined",
        script_path="", webhook_url="https://hooks.example.com/services/T1/B1/xyz",
    )
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.status = 200
        engine._run_rule(rule, {"mac": "AA:BB:CC:DD:EE:FF"}, lambda rid, s, t: logs.append(t))

    mock_urlopen.assert_called_once()
    req = mock_urlopen.call_args[0][0]
    assert req.full_url == "https://hooks.example.com/services/T1/B1/xyz"
    assert req.get_method() == "POST"
    assert any("Webhook → 200" in l for l in logs)


def test_webhook_payload_is_slack_and_discord_compatible():
    """Payload must carry both 'text' (Slack) and 'content' (Discord) keys,
    plus the raw event data, so a bare incoming-webhook URL from either
    service accepts it as-is."""
    import json
    engine_local = AutomationEngine.__new__(AutomationEngine)  # no __init__ needed
    logs = []
    rule = AutomationRule(name="Payload Test", webhook_url="https://example.com/hook")
    captured = {}

    def _fake_urlopen(req, timeout=5):
        captured["body"] = json.loads(req.data.decode("utf-8"))
        class _Resp:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        engine_local._send_webhook(
            rule, {"mac": "AA:BB", "alert_level": "HIGH"},
            rule.webhook_url, lambda s, t: logs.append(t),
        )

    assert "text" in captured["body"]
    assert "content" in captured["body"]
    assert captured["body"]["text"] == captured["body"]["content"]
    assert captured["body"]["mac"] == "AA:BB"


def test_webhook_error_is_logged_not_raised(engine):
    logs = []
    rule = AutomationRule(name="Fail", webhook_url="https://unreachable.example.invalid/hook")
    import urllib.error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
        engine._run_rule(rule, {}, lambda rid, s, t: logs.append(t))
    assert any("Webhook error" in l for l in logs)


# ── Template factories ────────────────────────────────────────────────────────

def test_template_wol_returns_rule():
    r = template_wol("AA:BB:CC:DD:EE:FF")
    assert isinstance(r, AutomationRule)
    assert r.trigger == Trigger.DEVICE_JOINED.value
    assert "AA:BB:CC:DD:EE:FF" in r.args or r.match_value == "AA:BB:CC:DD:EE:FF"


def test_template_log_to_file_returns_rule():
    r = template_log_to_file("/tmp/test.jsonl")
    assert isinstance(r, AutomationRule)
    assert r.trigger == Trigger.DEVICE_JOINED.value
    assert "/tmp/test.jsonl" in r.args


# ── Singleton ─────────────────────────────────────────────────────────────────

def test_get_engine_returns_same_instance():
    e1 = get_engine()
    e2 = get_engine()
    assert e1 is e2


# ── automation_event_from_alert (F-13) ─────────────────────────────────────────
# AutomationEngine.evaluate() previously had exactly one caller repo-wide: the
# manual "Test" button. Real device-down/high-RTT/new-device events fired by
# AlertEngine never reached it. automation_event_from_alert() maps a real
# AlertFired object onto the (trigger, event_data) shape evaluate() expects.

def _make_alert(rule_type: str, host: str = "", severity: str = "WARNING", message: str = ""):
    from modules.alert_engine import AlertFired
    import time
    return AlertFired(
        rule_name="r", rule_type=rule_type, host=host,
        message=message, severity=severity, ts=int(time.time()),
    )


def test_new_device_alert_maps_to_device_joined_trigger():
    alert = _make_alert("NEW_DEVICE", host="aa:bb:cc:dd:ee:ff")
    trigger, event_data = automation_event_from_alert(alert)
    assert trigger == Trigger.DEVICE_JOINED.value
    assert event_data["mac"] == "aa:bb:cc:dd:ee:ff"
    assert event_data["ip"] == ""


def test_device_gone_alert_maps_to_device_left_trigger():
    alert = _make_alert("DEVICE_GONE", host="192.168.1.42")
    trigger, event_data = automation_event_from_alert(alert)
    assert trigger == Trigger.DEVICE_LEFT.value
    assert event_data["ip"] == "192.168.1.42"
    assert event_data["mac"] == ""


def test_other_rule_types_map_to_generic_alert_fired_trigger():
    """Covers device-down / high-RTT and every other AlertEngine rule_type
    that isn't NEW_DEVICE/DEVICE_GONE -- these are the 'device-down' and
    'high RTT' events the README claims fire automation hooks."""
    alert = _make_alert("HIGH_RTT", host="192.168.1.10", severity="HIGH")
    trigger, event_data = automation_event_from_alert(alert)
    assert trigger == Trigger.ALERT_FIRED.value
    assert event_data["alert_level"] == "HIGH"


def test_evaluate_fires_rule_from_mapped_new_device_alert(engine):
    """End-to-end: a real AlertFired NEW_DEVICE event, run through the
    mapper, actually triggers a matching AutomationRule."""
    called = threading.Event()
    def fake_run(rule, event_data, on_log):
        called.set()
    engine.add_rule(AutomationRule(
        name="OnJoin", trigger=Trigger.DEVICE_JOINED.value,
        match_field="mac", match_value="aa:bb:cc:dd:ee:ff",
        script_path=sys.executable,
    ))
    alert = _make_alert("NEW_DEVICE", host="aa:bb:cc:dd:ee:ff")
    with patch.object(engine, "_run_rule", side_effect=fake_run):
        engine.evaluate(*automation_event_from_alert(alert))
    assert called.is_set()


def test_app_wires_alert_engine_into_automation_engine():
    """Static guard: app.py's on_alert callback must call both the
    notification router and automation_event_from_alert()/get_engine().
    A regression here silently disconnects Automation Hooks from real
    events again (the original F-13 defect)."""
    from pathlib import Path
    src = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    assert "alerts.set_on_alert(_dispatch_alert)" in src
    assert "automation_event_from_alert" in src
    assert "get_engine().evaluate(" in src

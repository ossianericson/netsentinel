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

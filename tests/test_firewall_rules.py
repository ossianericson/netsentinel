"""
Tests for modules/firewall_rules.py.

All tests are non-destructive — no actual netsh calls are made.
Platform checks and subprocess calls are monkeypatched throughout.
"""

from __future__ import annotations

import importlib
from pathlib import Path


# ── Import / attribute checks ─────────────────────────────────────────────────

def test_module_importable():
    mod = importlib.import_module("modules.firewall_rules")
    assert mod is not None


def test_public_api_present():
    from modules import firewall_rules
    assert callable(firewall_rules.ensure_app_rules)
    assert callable(firewall_rules.ensure_ookla_rules)


# ── Non-Windows no-op ─────────────────────────────────────────────────────────

def test_ensure_app_rules_noop_on_linux(monkeypatch):
    from modules import firewall_rules
    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Linux")
    firewall_rules._app_rules_done = False
    result = firewall_rules.ensure_app_rules()
    assert result is True


def test_ensure_ookla_rules_noop_on_linux(monkeypatch):
    from modules import firewall_rules
    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Linux")
    firewall_rules._ookla_rules_done = set()
    result = firewall_rules.ensure_ookla_rules(Path("speedtest.exe"))
    assert result is True


# ── Caching ───────────────────────────────────────────────────────────────────

def test_ensure_app_rules_cached(monkeypatch):
    """ensure_app_rules must invoke netsh at most once per process lifetime."""
    from modules import firewall_rules
    firewall_rules._app_rules_done = False
    call_count = [0]

    def _fake_netsh(*args, **kwargs):
        call_count[0] += 1
        return 0, "Rule Name: NetSentinel Speedtest\n"

    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Windows")
    monkeypatch.setattr(firewall_rules, "_netsh", _fake_netsh)

    firewall_rules.ensure_app_rules()
    first = call_count[0]
    firewall_rules.ensure_app_rules()   # second call — must be cached
    assert call_count[0] == first, "ensure_app_rules re-invoked netsh after caching"


def test_ensure_ookla_rules_cached(monkeypatch):
    """ensure_ookla_rules must skip netsh for a path already processed."""
    from modules import firewall_rules
    firewall_rules._ookla_rules_done = set()
    call_count = [0]

    def _fake_netsh(*args, **kwargs):
        call_count[0] += 1
        return 0, "Rule Name: NetSentinel Ookla Speedtest\n"

    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Windows")
    monkeypatch.setattr(firewall_rules, "_netsh", _fake_netsh)

    p = Path("C:/fake/speedtest.exe")
    firewall_rules.ensure_ookla_rules(p)
    first = call_count[0]
    firewall_rules.ensure_ookla_rules(p)   # second call — must be cached
    assert call_count[0] == first, "ensure_ookla_rules re-invoked netsh after caching"


# ── Rule-already-exists fast path ──────────────────────────────────────────────

def test_ensure_app_rules_skips_add_when_rule_exists(monkeypatch):
    from modules import firewall_rules
    firewall_rules._app_rules_done = False

    add_calls = []

    def _fake_netsh(*args, **kwargs):
        if "show" in args:
            return 0, "Rule Name: NetSentinel Speedtest\nEnabled: Yes\n"
        add_calls.append(args)
        return 0, "Ok."

    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Windows")
    monkeypatch.setattr(firewall_rules, "_netsh", _fake_netsh)

    result = firewall_rules.ensure_app_rules()
    assert result is True
    assert add_calls == [], "add rule called even though rule already existed"


# ── Not-elevated graceful failure ─────────────────────────────────────────────

def test_ensure_app_rules_returns_false_when_netsh_fails(monkeypatch):
    from modules import firewall_rules
    firewall_rules._app_rules_done = False

    def _fake_netsh(*args, **kwargs):
        if "show" in args:
            return 1, "No rules match the specified criteria."
        return 1, "Access is denied."   # simulate non-elevated

    monkeypatch.setattr(firewall_rules.platform, "system", lambda: "Windows")
    monkeypatch.setattr(firewall_rules, "_netsh", _fake_netsh)

    result = firewall_rules.ensure_app_rules()
    assert result is False


# ── _add_outbound_rules calls correct netsh arguments ────────────────────────

def test_add_outbound_rules_uses_remoteport(monkeypatch):
    from modules import firewall_rules
    recorded = []

    def _fake_netsh(*args, **kwargs):
        recorded.append(args)
        return 0, "Ok."

    monkeypatch.setattr(firewall_rules, "_netsh", _fake_netsh)
    firewall_rules._add_outbound_rules("Rule TCP", "Rule UDP", "C:/app.exe")

    # At least one add call must specify remoteport=
    add_calls = [c for c in recorded if "add" in c]
    assert any("remoteport=443,8080,5060" in " ".join(c) for c in add_calls), \
        "TCP add call missing expected remoteport argument"
    assert any("remoteport=8080,5060" in " ".join(c) for c in add_calls), \
        "UDP add call missing expected remoteport argument"

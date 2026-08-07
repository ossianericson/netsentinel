"""Phase 4 C4 — the plugin poll outcome must reach the alert engine.

`PluginPollingWorker.error` lands in `HardwareIntegrationPage._on_plugin_error`,
which updates the card's health counter and stops there. INFRA_UNREACHABLE needs
that same observation, plus the matching healthy observation from
`_on_plugin_result` — without the healthy one the EvidenceGate episode never
ends and the device can never be reported as recovered.

The page emits; the Dashboard evaluates. Two halves, tested separately: the page
against a real widget, the handler against a Dashboard double (RULE-TP4-DASH).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    from ui.dashboard import Dashboard
    from modules.alert_engine import AlertEngine, AlertRule
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ── The page emits a reachability observation ────────────────────────────────

@pytest.fixture
def page(monkeypatch):
    import ui.pages.hardware_integration_page as mod

    monkeypatch.setattr(mod, "_load_instances", lambda: [])
    monkeypatch.setattr(mod, "_load_paths", lambda: [])
    monkeypatch.setattr(mod, "_load_last_result", lambda _i: None)
    monkeypatch.setattr(mod, "_record_error", lambda i, m: {"consecutive": 1, "disabled": False})
    monkeypatch.setattr(mod, "_record_success", lambda i: {"consecutive": 0})

    p = mod.HardwareIntegrationPage(parent=None)
    seen: list = []
    p.plugin_reachability.connect(lambda *a: seen.append(a))
    p._seen = seen
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # non-fatal — already gone
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_plugin_error_emits_an_unreachable_observation(page):
    page._on_plugin_error("modem-1", "TIMEOUT: no response after 5s")

    assert len(page._seen) == 1, "a failed poll must be reported to the alert engine"
    instance_id, unreachable, _label, reason = page._seen[0]
    assert instance_id == "modem-1"
    assert unreachable is True
    assert "TIMEOUT" in reason


def test_auth_failure_is_not_an_unreachable_observation(page):
    """Wrong credentials mean the device answered — it is not unreachable.

    Mirrors _record_error()'s existing AUTH carve-out; counting it here would
    raise "your modem is not responding" for a mistyped password.
    """
    page._on_plugin_error("modem-1", "AUTH: bad password")

    assert len(page._seen) == 1
    assert page._seen[0][1] is False


def test_successful_poll_emits_a_healthy_observation(page):
    page._on_plugin_result("modem-1", {"status": {}})

    assert len(page._seen) == 1
    assert page._seen[0][1] is False, (
        "the healthy observation is what ends the EvidenceGate episode — without "
        "it a recovered device stays 'down' forever"
    )


def test_error_reported_inside_a_result_payload_counts_as_unreachable(page):
    page._on_plugin_result("modem-1", {"status": {"extra": {"error": "TIMEOUT: gone"}}})

    assert len(page._seen) == 1
    assert page._seen[0][1] is True


# ── The Dashboard handler evaluates it ───────────────────────────────────────

def _fake_dashboard(engine):
    fake = MagicMock()
    fake._alert_engine = engine
    fake._alerts_seen = []
    fake._surface_alert_in_app = fake._alerts_seen.append
    fake._store = MagicMock()
    return fake


def test_handler_fires_after_two_consecutive_failures():
    engine = AlertEngine(rules=[
        AlertRule(name="Infra", rule_type="INFRA_UNREACHABLE", cooldown_s=0, enabled=True)
    ])
    fake = _fake_dashboard(engine)

    Dashboard._on_plugin_reachability(fake, "modem-1", True, "ZTE MC889", "timeout")
    assert fake._alerts_seen == [], "one failed poll is a blip"
    Dashboard._on_plugin_reachability(fake, "modem-1", True, "ZTE MC889", "timeout")

    assert len(fake._alerts_seen) == 1
    assert fake._alerts_seen[0].rule_type == "INFRA_UNREACHABLE"


def test_handler_is_a_no_op_without_an_engine():
    fake = _fake_dashboard(None)
    Dashboard._on_plugin_reachability(fake, "modem-1", True, "ZTE MC889", "timeout")
    assert fake._alerts_seen == []


def test_page_signal_is_connected_to_the_handler():
    """RULE-DW1: the emit is useless unless something is listening."""
    tree = ast.parse((_REPO_ROOT / "ui" / "tabs.py").read_text(encoding="utf-8"))

    wired = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "plugin_reachability"
    ]
    assert len(wired) == 1, (
        "ui/tabs.py must connect HardwareIntegrationPage.plugin_reachability "
        f"exactly once; found {len(wired)}"
    )

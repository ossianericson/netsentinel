"""
Dogfooding harness for the in-app "Write a Plugin" AI prompts (Plan Phase 1/2).

tests/fixtures/ai_prompt_plugins/*.py are NOT hand-written test doubles — each
one is what a literal-minded AI produces when given ONLY the corresponding
prompt text from ui/pages/plugin_guide.py, with no insider knowledge of the
hardware-plugin contract beyond what that prompt states. See each fixture's
module docstring for the exact prompt it followed.

Phase 1 wrote these fixtures against the ORIGINAL (unfixed) prompts and
found five confirmed defects (D11-D15 in the plan): Prompt A never asked for
the plugin contract at all; Prompt B hard-coded a captured credential,
ignored the multi-instance IP injection, and set no request timeout; both
Prompt B and the template-completion prompt produced plugins whose runtime
errors were unclassified and silently defeated the circuit breaker's AUTH
exemption.

Phase 2 fixed ui/pages/plugin_guide.py (all three prompts) and the wizard's
_TEMPLATE / plugins/template_plugin.py (added _fmt_err + the AUTH:/NET:/
DEPS:/ERR: contract), then these fixtures were regenerated to reflect what
an AI produces under the FIXED prompts. This file now asserts the fix holds:
every fixture is a conforming, correctly-classified plugin. Compare with git
history for this file's Phase-1 version, which asserted the defects.

No real hardware is touched — tests.fake_device_http.FakeRouterServer stands
in for "the user's actual router".
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

from modules.plugin_tools import validate_plugin
from workers.plugin_polling_worker import PluginPollingWorker
from ui.widgets import hub_helpers as hh
from tests.fake_device_http import FakeRouterServer

FIXTURES = ROOT / "tests" / "fixtures" / "ai_prompt_plugins"
PROMPT_A = str(FIXTURES / "prompt_a_plugin.py")
PROMPT_B = str(FIXTURES / "prompt_b_plugin.py")
TEMPLATE_COMPLETED = str(FIXTURES / "template_completed_plugin.py")

_CLASSIFIED_PREFIXES = ("DEPS:", "NET:", "AUTH:", "ERR:", "FILE:")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _redirect_requests(monkeypatch, fake_base_url: str) -> None:
    """Rewrite scheme+host of every requests.get/post call to *fake_base_url*.

    Lets the fixtures' hardcoded/instance-IP-derived URLs transparently hit the
    in-process FakeRouterServer without editing the "AI-generated" fixture
    files (that would contaminate what the dogfood is actually measuring).
    """
    import requests as _requests_mod

    real_post, real_get = _requests_mod.post, _requests_mod.get
    fparts = urlsplit(fake_base_url)

    def _rewrite(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((fparts.scheme, fparts.netloc, parts.path, parts.query, parts.fragment))

    monkeypatch.setattr(_requests_mod, "post", lambda url, *a, **kw: real_post(_rewrite(url), *a, **kw))
    monkeypatch.setattr(_requests_mod, "get", lambda url, *a, **kw: real_get(_rewrite(url), *a, **kw))


def _run_worker_once(path: str, hw_type: str = "router", instance_ip: str = ""):
    """Instantiate PluginPollingWorker and run one poll synchronously (RULE-WIN4 pattern)."""
    captured = {"result": None, "error": None}
    w = PluginPollingWorker(path, hw_type, instance_id="iid-dogfood", instance_ip=instance_ip)
    w.result.connect(lambda d: captured.__setitem__("result", d))
    w.error.connect(lambda m: captured.__setitem__("error", m))
    try:
        w._run_once()
    finally:
        w.deleteLater()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
    return captured


def _route_into_health(path: str, captured: dict) -> dict:
    """Mirror HardwareIntegrationPage's error routing (test_plugin_worker_integration.py)."""
    if captured["error"] is not None:
        return hh._record_error(path, captured["error"])
    data = captured["result"] or {}
    err = (data.get("status") or {}).get("extra", {}).get("error", "")
    if err:
        return hh._record_error(path, err)
    return hh._record_success(path)


def _copy_fixture(tmp_path: Path, src: str) -> str:
    """Copy a fixture to a fresh tmp_path location.

    hub_helpers health tracking keys off the literal file path via
    QSettings("NetSentinel", "NetSentinel") -- an explicit org/app name that
    bypasses the isolated_settings fixture's QCoreApplication patching and
    persists to the real per-user QSettings backing store (Windows registry).
    Running straight against the checked-in fixture path would leak circuit-
    breaker counters across separate test runs. A fresh tmp_path copy per test
    gives each run its own path hash, exactly like test_plugin_worker_integration.py.
    """
    dst = tmp_path / Path(src).name
    dst.write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
    return str(dst)


def _install_fake_keyring(monkeypatch, store: dict) -> None:
    import types
    fake = types.ModuleType("keyring")
    fake.get_password = lambda service, key: store.get((service, key))
    fake.set_password = lambda service, key, value: store.__setitem__((service, key), value)
    monkeypatch.setitem(sys.modules, "keyring", fake)


# ── Prompt A — now a fully conforming plugin ───────────────────────────────────

def test_prompt_a_output_is_a_valid_plugin():
    """Fixed Prompt A explicitly asks for HARDWARE_NAME/HARDWARE_TYPE and the
    get_info()/get_status() functions -- unlike the Phase-1 finding where
    Prompt A produced a plain, non-conforming script.
    """
    result = validate_plugin(PROMPT_A)
    assert result.ok, result.pretty()


def test_prompt_a_uses_keyring_and_sets_timeout():
    source = Path(PROMPT_A).read_text(encoding="utf-8")
    assert "import keyring" in source
    assert "timeout=10" in source


def test_prompt_a_happy_path_and_classified_auth_failure(monkeypatch, qt_app, isolated_settings, tmp_path):
    path = _copy_fixture(tmp_path, PROMPT_A)
    with FakeRouterServer(password="correct-horse") as srv:
        host, port = srv.server_address
        _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", f"{host}:{port}"): "correct-horse"})

        captured = _run_worker_once(path, instance_ip=f"{host}:{port}")
        assert captured["error"] is None
        assert not captured["result"]["status"]["extra"].get("error")
        assert captured["result"]["status"]["connected_clients"] == 2

        srv.password = "changed-on-router"
        captured = _run_worker_once(path, instance_ip=f"{host}:{port}")
        err = (captured["result"] or {}).get("status", {}).get("extra", {}).get("error", "")
        assert err.startswith("AUTH:"), f"expected a classified AUTH: error, got {err!r}"

        h = _route_into_health(path, captured)
        assert h["consecutive"] == 0, "AUTH: errors must not count toward the circuit breaker"


# ── Prompt B — hard-coded secret and multi-instance defects are gone ──────────

def test_prompt_b_output_is_a_valid_plugin():
    result = validate_plugin(PROMPT_B)
    assert result.ok, result.pretty()


def test_prompt_b_no_longer_hardcodes_a_password():
    """Fixed Prompt B tells the AI to move a captured credential to keyring.

    Checks for a live PASSWORD/PW constant assignment specifically (not a bare
    substring search) since the fixture's own docstring quotes the captured
    cURL command -- including the secret -- as documentation of what prompt
    it was generated from.
    """
    import ast
    source = Path(PROMPT_B).read_text(encoding="utf-8")
    assert "import keyring" in source
    tree = ast.parse(source)
    hardcoded = [
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str) and node.value.value == "correct-horse"
        for target in node.targets if isinstance(target, ast.Name)
    ]
    assert not hardcoded, f"captured secret must not be hard-coded as {hardcoded}"


def test_prompt_b_now_supports_multi_instance_ip_injection():
    """Fixed Prompt B tells the AI to read _NETSENTINEL_INSTANCE_IP."""
    source = Path(PROMPT_B).read_text(encoding="utf-8")
    assert "_NETSENTINEL_INSTANCE_IP" in source


def test_prompt_b_and_template_completed_now_set_a_request_timeout():
    for path in (PROMPT_B, TEMPLATE_COMPLETED):
        source = Path(path).read_text(encoding="utf-8")
        assert "timeout=" in source, f"{path} still has no request timeout"


def test_prompt_b_wrong_password_now_produces_classified_auth_error(monkeypatch, qt_app, isolated_settings, tmp_path):
    """The unclassified-error defect (D15) is fixed: a wrong password now
    produces a proper AUTH: error that does not trip the circuit breaker.
    """
    path = _copy_fixture(tmp_path, PROMPT_B)
    with FakeRouterServer(password="correct-horse") as srv:
        host, port = srv.server_address
        _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", f"{host}:{port}"): "correct-horse"})
        _redirect_requests(monkeypatch, srv.url)
        srv.password = "changed-on-router"

        captured = _run_worker_once(path, instance_ip=f"{host}:{port}")
        assert captured["error"] is None, "error must be reported via extra.error, not an uncaught exception"
        err = captured["result"]["status"]["extra"].get("error", "")
        assert err.startswith("AUTH:"), f"expected a classified AUTH: error, got {err!r}"

        h = _route_into_health(path, captured)
        assert h["consecutive"] == 0, "AUTH: errors must not count toward the circuit breaker"


def test_prompt_b_offline_now_produces_classified_net_error(monkeypatch, qt_app, isolated_settings, tmp_path):
    path = _copy_fixture(tmp_path, PROMPT_B)
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", "127.0.0.1:1"): "correct-horse"})
    captured = _run_worker_once(path, instance_ip="127.0.0.1:1")  # nothing listens here
    assert captured["error"] is None
    err = captured["result"]["status"]["extra"].get("error", "")
    assert err.startswith("NET:"), f"expected a classified NET: error, got {err!r}"


# ── Template-completion prompt — best-case path, now correctly classified ─────

def test_template_completed_output_is_a_valid_plugin():
    result = validate_plugin(TEMPLATE_COMPLETED)
    assert result.ok, result.pretty()


def test_template_completed_keeps_keyring_instance_ip_and_error_contract():
    source = Path(TEMPLATE_COMPLETED).read_text(encoding="utf-8")
    assert "import keyring" in source
    assert "_NETSENTINEL_INSTANCE_IP" in source
    assert "_fmt_err" in source


def test_template_completed_wrong_password_now_produces_classified_auth_error(monkeypatch, qt_app, isolated_settings, tmp_path):
    path = _copy_fixture(tmp_path, TEMPLATE_COMPLETED)
    with FakeRouterServer(password="correct-horse") as srv:
        host, port = srv.server_address
        _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", f"{host}:{port}"): "correct-horse"})

        # Happy path sanity check first.
        captured = _run_worker_once(path, instance_ip=f"{host}:{port}")
        assert captured["error"] is None
        assert not captured["result"]["status"]["extra"].get("error")

        # Now break auth and confirm the fix holds.
        srv.password = "changed-on-router"
        captured = _run_worker_once(path, instance_ip=f"{host}:{port}")
        err = (captured["result"] or {}).get("status", {}).get("extra", {}).get("error", "")
        assert err.startswith("AUTH:"), f"expected a classified AUTH: error, got {err!r}"

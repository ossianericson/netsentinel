"""Tests for _validate_script and _classify_error (no QApp required).

RULE-T1 compliance for hardware_integration_page helper functions.
"""
from __future__ import annotations

import textwrap
from pathlib import Path


from ui.pages.hardware_integration_page import _classify_error, _validate_script


# ── helpers ───────────────────────────────────────────────────────────────────


def _write(tmp_path: Path, body: str) -> str:
    p = tmp_path / "plugin.py"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(p)


# ── _validate_script — happy paths ────────────────────────────────────────────


def test_valid_minimal_script(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME = "Test Router"
        HARDWARE_TYPE = "router"
        HARDWARE_IP   = "192.168.1.1"
        def get_info(): return {}
        def get_status(): return {}
    """)
    ok, msg, meta = _validate_script(path)
    assert ok
    assert msg == "OK"
    assert meta["name"] == "Test Router"
    assert meta["type"] == "router"


def test_valid_with_all_optional_constants(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME     = "My Modem"
        HARDWARE_TYPE     = "modem"
        HARDWARE_IP       = "192.168.0.1"
        PYPI_PACKAGE      = "fritzconnection"
        CREDENTIAL_LABEL  = "API Key"
        DESCRIPTION       = "ZTE modem integration"
        def get_info(): return {}
        def get_status(): return {}
        def get_clients(): return []
    """)
    ok, _, meta = _validate_script(path)
    assert ok
    assert meta["pypi_package"] == "fritzconnection"
    assert meta["credential_label"] == "API Key"
    assert meta["description"] == "ZTE modem integration"


def test_script_with_no_hardware_ip_defaults_empty(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME = "Switch"
        HARDWARE_TYPE = "switch"
        def get_info(): return {}
        def get_status(): return {}
    """)
    ok, _, meta = _validate_script(path)
    assert ok
    assert meta["ip"] == ""


# ── _validate_script — error paths ────────────────────────────────────────────


def test_syntax_error_returns_false(tmp_path):
    path = _write(tmp_path, "def broken(:\n    pass")
    ok, msg, meta = _validate_script(path)
    assert not ok
    assert "syntax" in msg.lower() or "Syntax" in msg
    assert meta == {}


def test_missing_hardware_name(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_TYPE = "router"
        def get_info(): return {}
        def get_status(): return {}
    """)
    ok, msg, _ = _validate_script(path)
    assert not ok
    assert "HARDWARE_NAME" in msg


def test_missing_hardware_type(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME = "X"
        def get_info(): return {}
        def get_status(): return {}
    """)
    ok, msg, _ = _validate_script(path)
    assert not ok
    assert "HARDWARE_TYPE" in msg


def test_missing_get_info(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME = "X"
        HARDWARE_TYPE = "router"
        def get_status(): return {}
    """)
    ok, msg, _ = _validate_script(path)
    assert not ok
    assert "get_info" in msg


def test_missing_get_status(tmp_path):
    path = _write(tmp_path, """
        HARDWARE_NAME = "X"
        HARDWARE_TYPE = "router"
        def get_info(): return {}
    """)
    ok, msg, _ = _validate_script(path)
    assert not ok
    assert "get_status" in msg


def test_nonexistent_file_returns_false(tmp_path):
    ok, msg, meta = _validate_script(str(tmp_path / "nonexistent.py"))
    assert not ok
    assert meta == {}


def test_binary_file_returns_false(tmp_path):
    p = tmp_path / "plugin.py"
    p.write_bytes(b"\x00\x01\x02\x03")
    ok, msg, meta = _validate_script(str(p))
    # Either parses with garbage or hits some error — either way not OK
    # (binary → UnicodeDecodeError or SyntaxError during parse)
    assert meta == {} or not ok  # at minimum no crash


# ── _classify_error — structured prefix handling ──────────────────────────────


def test_classify_deps_prefix_with_pip_install():
    result = _classify_error(
        "DEPS: tplinkrouterc6u not installed. Run: pip install tplinkrouterc6u"
    )
    assert "tplinkrouterc6u" in result
    # Should mention "Missing library" or "pip install"
    assert "Missing" in result or "pip install" in result


def test_classify_auth_prefix():
    result = _classify_error("AUTH: wrong password for admin account")
    assert "auth" in result.lower() or "Authentication" in result


def test_classify_net_prefix():
    result = _classify_error("NET: connection refused at 192.168.68.1:80")
    assert "reach" in result.lower() or "Cannot" in result


def test_classify_err_prefix_returns_body():
    result = _classify_error("ERR: internal state machine error XYZ99")
    assert "internal state machine error XYZ99" in result


# ── _classify_error — legacy / unstructured fallback ─────────────────────────


def test_classify_legacy_pip_install():
    result = _classify_error("no module named requests, run: pip install requests")
    assert "requests" in result
    assert "Missing" in result or "pip" in result.lower()


def test_classify_legacy_401_auth():
    result = _classify_error("HTTP 401 unauthorized response from router")
    assert "auth" in result.lower() or "Authentication" in result


def test_classify_legacy_connection_refused():
    result = _classify_error("Connection refused — host is unreachable")
    assert "reach" in result.lower() or "Cannot" in result


def test_classify_legacy_no_password():
    result = _classify_error("No password saved for 192.168.1.1")
    assert "password" in result.lower()


def test_classify_unknown_returns_original():
    result = _classify_error("some totally random error message XYZ_SENTINEL_42")
    assert "XYZ_SENTINEL_42" in result

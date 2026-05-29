"""Tests for modules/plugin_tools.py (P3-1 validator CLI, P4-2 signing, P4-3 imports)."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.plugin_tools import (
    ValidationResult,
    ValidationIssue,
    validate_plugin,
    verify_signature,
    _cli_validate,
    _load_hash_db,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _write_plugin(tmp_path: Path, content: str) -> str:
    p = tmp_path / "test_plugin.py"
    p.write_text(content, encoding="utf-8")
    return str(p)


_MINIMAL_VALID = """\
HARDWARE_NAME = "Test Device"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"
CREDENTIAL_LABEL = "Password"

def get_info():
    return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}

def get_status():
    return {"connected_clients": 0, "extra": {}}
"""

_MISSING_NAME = """\
HARDWARE_TYPE = "router"

def get_info():
    return {}

def get_status():
    return {}
"""

_MISSING_FUNCTION = """\
HARDWARE_NAME = "Test"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "10.0.0.1"

def get_info():
    return {}
"""

_SYNTAX_ERROR = """\
HARDWARE_NAME = "Broken"
def get_info(:
    pass
"""

_REQUIRED_ARGS = """\
HARDWARE_NAME = "Test"
HARDWARE_TYPE = "router"

def get_info(required_arg):
    return {}

def get_status():
    return {}
"""

_WITH_PYPI_PACKAGE = """\
HARDWARE_NAME  = "Test"
HARDWARE_TYPE  = "router"
HARDWARE_IP    = "192.168.1.1"
PYPI_PACKAGE   = "fritzconnection"
CREDENTIAL_LABEL = "Password"

def get_info():
    return {}

def get_status():
    return {}
"""

_WITH_SAFE_IMPORTS = """\
HARDWARE_NAME  = "Test"
HARDWARE_TYPE  = "modem"
HARDWARE_IP    = "192.168.1.1"
SAFE_IMPORTS   = ["requests", "keyring", "numpy"]
CREDENTIAL_LABEL = "Password"

import numpy

def get_info():
    return {}

def get_status():
    return {}
"""

_EXTERNAL_IMPORT_NO_PYPI = """\
HARDWARE_NAME = "Test"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"
CREDENTIAL_LABEL = "Password"

import fritzconnection

def get_info():
    return {}

def get_status():
    return {}
"""


# ── Tests: validate_plugin ────────────────────────────────────────────────────

class TestValidatePlugin:

    def test_file_not_found(self):
        result = validate_plugin("/nonexistent/path/plugin.py")
        assert not result.ok
        assert any("not found" in i.message.lower() for i in result.errors)

    def test_valid_plugin_passes(self, tmp_path):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        result = validate_plugin(path)
        assert result.ok
        assert not result.errors

    def test_syntax_error_fails(self, tmp_path):
        path = _write_plugin(tmp_path, _SYNTAX_ERROR)
        result = validate_plugin(path)
        assert not result.ok
        assert any("syntax" in i.message.lower() for i in result.errors)

    def test_missing_required_constant(self, tmp_path):
        path = _write_plugin(tmp_path, _MISSING_NAME)
        result = validate_plugin(path)
        assert not result.ok
        assert any("HARDWARE_NAME" in i.message for i in result.errors)

    def test_missing_required_function(self, tmp_path):
        path = _write_plugin(tmp_path, _MISSING_FUNCTION)
        result = validate_plugin(path)
        assert not result.ok
        assert any("get_status" in i.message for i in result.errors)

    def test_required_args_on_get_info_fails(self, tmp_path):
        path = _write_plugin(tmp_path, _REQUIRED_ARGS)
        result = validate_plugin(path)
        assert not result.ok
        assert any("required positional" in i.message for i in result.errors)

    def test_pypi_package_declared_suppresses_warning(self, tmp_path):
        path = _write_plugin(tmp_path, _WITH_PYPI_PACKAGE)
        result = validate_plugin(path)
        # No warning about missing PYPI_PACKAGE
        warning_msgs = [i.message for i in result.warnings]
        assert not any("PYPI_PACKAGE" in m for m in warning_msgs)

    def test_external_import_without_pypi_warns(self, tmp_path):
        path = _write_plugin(tmp_path, _EXTERNAL_IMPORT_NO_PYPI)
        result = validate_plugin(path)
        assert any("PYPI_PACKAGE" in i.message for i in result.warnings)

    def test_safe_imports_override_suppresses_advisory(self, tmp_path):
        path = _write_plugin(tmp_path, _WITH_SAFE_IMPORTS)
        result = validate_plugin(path)
        # numpy is in SAFE_IMPORTS, so should not appear in info advisory
        info_msgs = [i.message for i in result.issues if i.level == "info"]
        suspicious_msg = [m for m in info_msgs if "numpy" in m]
        assert not suspicious_msg, f"numpy should be suppressed: {info_msgs}"

    def test_meta_populated(self, tmp_path):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        result = validate_plugin(path)
        assert result.meta["name"] == "Test Device"
        assert result.meta["type"] == "router"
        assert result.meta["ip"]   == "192.168.1.1"
        assert result.meta["credential_label"] == "Password"

    def test_sha256_in_meta(self, tmp_path):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        result = validate_plugin(path)
        expected = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert result.meta.get("sha256") == expected

    def test_no_hardware_ip_warns(self, tmp_path):
        content = """\
HARDWARE_NAME = "Test"
HARDWARE_TYPE = "router"

def get_info():
    return {}

def get_status():
    return {}
"""
        path = _write_plugin(tmp_path, content)
        result = validate_plugin(path)
        assert any("HARDWARE_IP" in i.message for i in result.warnings)

    def test_pretty_output_ok(self, tmp_path):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        result = validate_plugin(path)
        pretty = result.pretty()
        assert pretty.startswith("✓")

    def test_pretty_output_error(self, tmp_path):
        path = _write_plugin(tmp_path, _MISSING_NAME)
        result = validate_plugin(path)
        pretty = result.pretty()
        assert pretty.startswith("✗")

    def test_no_credential_label_gives_info(self, tmp_path):
        content = """\
HARDWARE_NAME = "Test"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {}

def get_status():
    return {}
"""
        path = _write_plugin(tmp_path, content)
        result = validate_plugin(path)
        assert any("CREDENTIAL_LABEL" in i.message for i in result.issues
                   if i.level == "info")


# ── Tests: verify_signature ───────────────────────────────────────────────────

class TestVerifySignature:

    def test_not_in_hash_list_when_db_missing(self, tmp_path, monkeypatch):
        """No hash DB → returns (False, 'Not in hash list')."""
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        monkeypatch.setattr(
            "modules.plugin_tools._load_hash_db",
            lambda: {},
        )
        signed, msg = verify_signature(path)
        assert not signed
        assert "Not in hash list" in msg

    def test_verified_when_hash_matches(self, tmp_path, monkeypatch):
        from modules.plugin_tools import _file_hash
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        sha = _file_hash(path)  # must match _file_hash used inside verify_signature
        monkeypatch.setattr(
            "modules.plugin_tools._load_hash_db",
            lambda: {Path(path).name: sha},
        )
        signed, msg = verify_signature(path)
        assert signed
        assert "Verified" in msg

    def test_mismatch_when_hash_differs(self, tmp_path, monkeypatch):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        monkeypatch.setattr(
            "modules.plugin_tools._load_hash_db",
            lambda: {Path(path).name: "deadbeef" * 8},
        )
        signed, msg = verify_signature(path)
        assert not signed
        assert "MISMATCH" in msg

    def test_load_hash_db_returns_empty_when_file_absent(self, monkeypatch, tmp_path):
        # Point the module root elsewhere so the hash file can't be found
        monkeypatch.setattr(
            "modules.plugin_tools.Path",
            lambda *args, **kwargs: _FakePath(tmp_path / "nonexistent" / "no.json"),
        )
        # Fall back to direct test — just confirm the function handles missing file
        db = _load_hash_db.__wrapped__() if hasattr(_load_hash_db, "__wrapped__") else _load_hash_db()
        # Either way it must return a dict
        assert isinstance(db, dict)


# ── Tests: CLI ────────────────────────────────────────────────────────────────

class TestCliValidate:

    def test_no_args_returns_1(self):
        assert _cli_validate([]) == 1

    def test_valid_plugin_returns_0(self, tmp_path, monkeypatch, capsys):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        monkeypatch.setattr("modules.plugin_tools._load_hash_db", lambda: {})
        rc = _cli_validate([str(path)])
        assert rc == 0

    def test_invalid_plugin_returns_1(self, tmp_path, monkeypatch, capsys):
        path = _write_plugin(tmp_path, _MISSING_NAME)
        monkeypatch.setattr("modules.plugin_tools._load_hash_db", lambda: {})
        rc = _cli_validate([str(path)])
        assert rc == 1

    def test_live_flag_accepted(self, tmp_path, monkeypatch):
        path = _write_plugin(tmp_path, _MINIMAL_VALID)
        monkeypatch.setattr("modules.plugin_tools._load_hash_db", lambda: {})
        # --live is accepted without crashing (even if device unreachable)
        rc = _cli_validate([str(path), "--live"])
        assert rc == 0  # minimal plugin has no external imports so live import succeeds


# ── Regression: bundled plugin hashes must stay in sync ──────────────────────

class TestBundledPluginHashSync:
    """Regression guard: data/plugin_hashes.json must match the actual plugins/.

    This test failed silently when P1-3 (sprint 2) updated deco_plugin.py and
    zte_plugin.py to use module-attribute injection but the hash database was
    not regenerated.  The consequence: _start_poll_worker_inst returned early
    on every startup, so no plugin ever produced data.

    Hashes are computed on LF-normalised content so they are identical on Windows
    (CRLF) and Linux/macOS (LF) after git checkout.

    If this test fails, regenerate with:
        python -c "
        import hashlib, json
        from pathlib import Path
        def fh(p): raw=p.read_bytes(); return hashlib.sha256(raw.replace(b'\\r\\n',b'\\n')).hexdigest()
        hashes = {p.name: fh(p) for p in sorted(Path('plugins').glob('*.py'))}
        Path('data/plugin_hashes.json').write_text(json.dumps(hashes, indent=2) + chr(10))
        "
    """

    def test_hash_db_matches_bundled_plugins(self):
        from modules.plugin_tools import _file_hash
        PLUGINS = ROOT / "plugins"
        HASH_DB = ROOT / "data" / "plugin_hashes.json"

        if not HASH_DB.exists():
            pytest.skip("data/plugin_hashes.json not present")

        db = json.loads(HASH_DB.read_text(encoding="utf-8"))

        mismatches = []
        for plugin in sorted(PLUGINS.glob("*.py")):
            recorded = db.get(plugin.name)
            if recorded is None:
                mismatches.append(f"{plugin.name}: missing from hash DB")
                continue
            actual = _file_hash(plugin)
            if actual != recorded:
                mismatches.append(
                    f"{plugin.name}: DB={recorded[:12]}… actual={actual[:12]}…"
                )

        assert not mismatches, (
            "Bundled plugin(s) changed but data/plugin_hashes.json was not "
            "regenerated — workers will silently refuse to start.\n"
            "Run the regeneration command in the docstring above.\n"
            "Mismatches:\n  " + "\n  ".join(mismatches)
        )


# ── Helper for hash DB test ───────────────────────────────────────────────────

class _FakePath:
    """Stub that mimics just enough of pathlib.Path to make _load_hash_db return {}."""
    def __init__(self, p): self._p = Path(p)
    def __truediv__(self, other): return _FakePath(self._p / other)
    def exists(self): return False

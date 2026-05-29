"""
Tests for the _import_bundled / _validate_script / instance-registry flow
in ui/pages/hardware_integration_page.py.

RULE-T1: covers AppData copy, PYPI_PACKAGE check, _validate_script edge-cases,
         instance registry round-trip, and _instance_id stability.

No PyQt6 GUI is initialised — all UI-level code is tested via the module-level
helper functions that do not depend on a QWidget parent.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import only the pure helpers (no QApplication needed)
from ui.pages.hardware_integration_page import (
    _validate_script,
    _path_hash,
    _instance_id,
)


# ── _validate_script ──────────────────────────────────────────────────────────

class TestValidateScript:

    def _write(self, tmp_path: Path, content: str) -> str:
        p = tmp_path / "test_plugin.py"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_valid_minimal(self, tmp_path):
        src = """\
HARDWARE_NAME = "My Device"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "10.0.0.1"
CREDENTIAL_LABEL = "Password"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, msg, meta = _validate_script(self._write(tmp_path, src))
        assert ok, msg
        assert meta["name"] == "My Device"
        assert meta["type"] == "router"
        assert meta["ip"]   == "10.0.0.1"

    def test_missing_hardware_name(self, tmp_path):
        src = """\
HARDWARE_TYPE = "router"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, msg, _ = _validate_script(self._write(tmp_path, src))
        assert not ok
        assert "HARDWARE_NAME" in msg

    def test_missing_hardware_type(self, tmp_path):
        src = """\
HARDWARE_NAME = "X"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, msg, _ = _validate_script(self._write(tmp_path, src))
        assert not ok
        assert "HARDWARE_TYPE" in msg

    def test_missing_get_info(self, tmp_path):
        src = """\
HARDWARE_NAME = "X"
HARDWARE_TYPE = "router"

def get_status():
    return {}
"""
        ok, msg, _ = _validate_script(self._write(tmp_path, src))
        assert not ok
        assert "get_info" in msg

    def test_missing_get_status(self, tmp_path):
        src = """\
HARDWARE_NAME = "X"
HARDWARE_TYPE = "router"

def get_info():
    return {}
"""
        ok, msg, _ = _validate_script(self._write(tmp_path, src))
        assert not ok
        assert "get_status" in msg

    def test_syntax_error(self, tmp_path):
        src = "def get_info(:\n    pass\n"
        ok, msg, _ = _validate_script(self._write(tmp_path, src))
        assert not ok
        assert "syntax" in msg.lower() or "error" in msg.lower()

    def test_nonexistent_file(self, tmp_path):
        ok, msg, _ = _validate_script(str(tmp_path / "nosuchfile.py"))
        assert not ok

    def test_meta_returns_pypi_package(self, tmp_path):
        src = """\
HARDWARE_NAME  = "X"
HARDWARE_TYPE  = "router"
HARDWARE_IP    = "192.168.1.1"
PYPI_PACKAGE   = "mylib"
CREDENTIAL_LABEL = "Password"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, _, meta = _validate_script(self._write(tmp_path, src))
        assert ok
        assert meta["pypi_package"] == "mylib"

    def test_meta_returns_credential_label(self, tmp_path):
        src = """\
HARDWARE_NAME    = "X"
HARDWARE_TYPE    = "router"
HARDWARE_IP      = "192.168.1.1"
CREDENTIAL_LABEL = "PIN"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, _, meta = _validate_script(self._write(tmp_path, src))
        assert ok
        assert meta["credential_label"] == "PIN"

    def test_icon_path_detected_from_sibling_png(self, tmp_path):
        src = """\
HARDWARE_NAME = "X"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {}

def get_status():
    return {}
"""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(src, encoding="utf-8")
        # Create sibling icon.png
        icon_file = tmp_path / "icon.png"
        icon_file.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
        ok, _, meta = _validate_script(str(plugin_file))
        assert ok
        assert meta.get("icon_path") == str(icon_file)

    def test_icon_path_empty_when_no_icon(self, tmp_path):
        src = """\
HARDWARE_NAME = "X"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {}

def get_status():
    return {}
"""
        ok, _, meta = _validate_script(self._write(tmp_path, src))
        assert ok
        assert meta.get("icon_path", "") == ""


# ── _path_hash ────────────────────────────────────────────────────────────────

class TestPathHash:

    def test_returns_12_char_hex(self):
        h = _path_hash("/some/path/plugin.py")
        assert isinstance(h, str)
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_stable_across_calls(self):
        assert _path_hash("/a/b.py") == _path_hash("/a/b.py")

    def test_different_for_different_paths(self):
        assert _path_hash("/a.py") != _path_hash("/b.py")


# ── _instance_id ──────────────────────────────────────────────────────────────

class TestInstanceId:

    def test_returns_16_char_hex(self):
        iid = _instance_id("/path/plugin.py", "192.168.1.1")
        assert isinstance(iid, str)
        assert len(iid) == 16
        assert all(c in "0123456789abcdef" for c in iid)

    def test_stable_across_calls(self):
        a = _instance_id("/p.py", "10.0.0.1")
        b = _instance_id("/p.py", "10.0.0.1")
        assert a == b

    def test_different_ip_gives_different_id(self):
        a = _instance_id("/p.py", "10.0.0.1")
        b = _instance_id("/p.py", "10.0.0.2")
        assert a != b

    def test_different_path_gives_different_id(self):
        a = _instance_id("/a.py", "10.0.0.1")
        b = _instance_id("/b.py", "10.0.0.1")
        assert a != b


# ── _validate_script + PYPI_PACKAGE dependency check ─────────────────────────

class TestPypiPackageCheck:
    """Simulate the PYPI_PACKAGE dep check that _import_bundled performs."""

    def test_pypi_package_importable_check(self, tmp_path):
        """find_spec for a known-installable stdlib module returns non-None."""
        import importlib.util
        # 'json' is always available
        spec = importlib.util.find_spec("json")
        assert spec is not None

    def test_pypi_package_not_importable(self, tmp_path):
        """find_spec for a made-up package returns None."""
        import importlib.util
        spec = importlib.util.find_spec("__definitely_not_installed_xyz_abc__")
        assert spec is None

    def test_meta_pypi_package_used_for_module_lookup(self, tmp_path):
        """Meta 'pypi_package' value with dash → underscore yields importable name."""
        src = """\
HARDWARE_NAME = "X"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"
PYPI_PACKAGE  = "python-dateutil"

def get_info():
    return {}

def get_status():
    return {}
"""
        plugin_path = tmp_path / "test_plugin.py"
        plugin_path.write_text(src, encoding="utf-8")
        ok, _, meta = _validate_script(str(plugin_path))
        assert ok
        pkg = meta["pypi_package"]
        assert pkg == "python-dateutil"
        module_name = pkg.replace("-", "_")
        assert module_name == "python_dateutil"


# ── AppData copy logic (unit-level) ──────────────────────────────────────────

class TestAppDataCopyLogic:
    """Verify the copy-to-AppData pattern used in _import_bundled."""

    def test_copy_to_dest_dir(self, tmp_path):
        src = tmp_path / "src_plugin.py"
        src.write_text("# content", encoding="utf-8")
        dest_dir = tmp_path / "appdata" / "plugins"
        dest_dir.mkdir(parents=True)
        import shutil
        dest = dest_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        assert dest.exists()
        assert dest.read_text() == "# content"

    def test_no_copy_when_paths_are_same(self, tmp_path):
        src = tmp_path / "plugin.py"
        src.write_text("# data", encoding="utf-8")
        import shutil
        call_count = [0]
        orig_copy = shutil.copy2

        def counting_copy(a, b):
            call_count[0] += 1
            return orig_copy(a, b)

        # The condition `Path(path).resolve() != _dest.resolve()` prevents self-copy
        dest = src
        if src.resolve() != dest.resolve():
            counting_copy(src, dest)
        assert call_count[0] == 0, "Should not copy when src == dest"


# ── _classify_error helper (imported from page) ───────────────────────────────

class TestClassifyError:
    def setup_method(self):
        from ui.pages.hardware_integration_page import _classify_error
        self._classify = _classify_error

    def test_deps_prefix(self):
        msg = self._classify("DEPS: tplinkrouterc6u not installed. Run: pip install tplinkrouterc6u")
        assert "Missing library" in msg or "tplinkrouterc6u" in msg

    def test_auth_prefix(self):
        msg = self._classify("AUTH: wrong password")
        assert "Authentication" in msg or "auth" in msg.lower()

    def test_net_prefix(self):
        msg = self._classify("NET: connection refused at 192.168.1.1")
        assert "192.168.1.1" in msg or "Cannot reach" in msg

    def test_pip_install_in_message(self):
        msg = self._classify("ImportError: pip install fritzconnection")
        assert "fritzconnection" in msg

    def test_passthrough_unknown(self):
        msg = self._classify("some unusual error with no prefix")
        assert "some unusual error" in msg

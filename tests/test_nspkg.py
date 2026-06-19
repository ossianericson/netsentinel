"""tests/test_nspkg.py — P3-5: .nspkg bundle format"""
import json
import zipfile
from pathlib import Path

import pytest

from modules.nspkg import unpack_nspkg, validate_manifest, _safe_filename


# ── validate_manifest ──────────────────────────────────────────────────────────

def test_validate_manifest_ok():
    m = {"name": "Test Plugin", "version": "1.0.0", "author": "Alice"}
    assert validate_manifest(m) == []


def test_validate_manifest_missing_name():
    m = {"version": "1.0.0", "author": "Alice"}
    errors = validate_manifest(m)
    assert any("name" in e for e in errors)


def test_validate_manifest_missing_version():
    m = {"name": "X", "author": "Bob"}
    errors = validate_manifest(m)
    assert any("version" in e for e in errors)


def test_validate_manifest_missing_author():
    m = {"name": "X", "version": "1.0.0"}
    errors = validate_manifest(m)
    assert any("author" in e for e in errors)


def test_validate_manifest_bad_pypi_deps():
    m = {"name": "X", "version": "1.0", "author": "B", "pypi_deps": "requests"}
    errors = validate_manifest(m)
    assert any("pypi_deps" in e for e in errors)


def test_validate_manifest_list_pypi_deps():
    m = {"name": "X", "version": "1.0", "author": "B", "pypi_deps": ["requests"]}
    assert validate_manifest(m) == []


# ── _safe_filename ─────────────────────────────────────────────────────────────

def test_safe_filename_basic():
    assert _safe_filename("My Router XYZ") == "my_router_xyz"


def test_safe_filename_special_chars():
    assert _safe_filename("Plug-In #2!") == "plug_in_2"


def test_safe_filename_empty():
    assert _safe_filename("") == "plugin"


# ── unpack_nspkg ──────────────────────────────────────────────────────────────

_PLUGIN_SRC = """\
HARDWARE_NAME = "Test Hardware"
HARDWARE_TYPE = "other"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE}

def get_status():
    return {"connected_clients": 0, "extra": {}}
"""

_MANIFEST = {
    "name": "Test Hardware",
    "version": "1.0.0",
    "author": "Test Author",
    "pypi_deps": [],
    "min_ns_version": "1.9.0",
}


def _make_nspkg(tmp_path: Path, manifest=None, plugin_src=None, include_icon=False) -> Path:
    nspkg = tmp_path / "test_plugin.nspkg"
    with zipfile.ZipFile(str(nspkg), "w") as zf:
        zf.writestr("plugin.py", plugin_src or _PLUGIN_SRC)
        zf.writestr("manifest.json", json.dumps(manifest or _MANIFEST))
        if include_icon:
            # minimal 1×1 PNG
            import base64
            PNG_1x1 = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
            zf.writestr("icon.png", PNG_1x1)
    return nspkg


def test_unpack_basic(tmp_path):
    nspkg = _make_nspkg(tmp_path)
    dest = tmp_path / "dest"
    plugin_path, manifest = unpack_nspkg(str(nspkg), dest)

    assert plugin_path.exists()
    assert plugin_path.suffix == ".py"
    assert manifest["name"] == "Test Hardware"
    assert "_nspkg_sha256" in manifest
    assert len(manifest["_nspkg_sha256"]) == 64


def test_unpack_plugin_content(tmp_path):
    nspkg = _make_nspkg(tmp_path)
    dest = tmp_path / "dest"
    plugin_path, _ = unpack_nspkg(str(nspkg), dest)
    content = plugin_path.read_text()
    assert "get_info" in content
    assert "get_status" in content


def test_unpack_icon_extracted(tmp_path):
    nspkg = _make_nspkg(tmp_path, include_icon=True)
    dest = tmp_path / "dest"
    plugin_path, manifest = unpack_nspkg(str(nspkg), dest)
    # icon should have been extracted alongside plugin
    icon_path = dest / f"{plugin_path.stem}_icon.png"
    assert icon_path.exists()


def test_unpack_missing_plugin_py(tmp_path):
    bad = tmp_path / "bad.nspkg"
    with zipfile.ZipFile(str(bad), "w") as zf:
        zf.writestr("manifest.json", json.dumps(_MANIFEST))
    with pytest.raises(ValueError, match="plugin.py"):
        unpack_nspkg(str(bad), tmp_path / "dest")


def test_unpack_missing_manifest(tmp_path):
    bad = tmp_path / "bad.nspkg"
    with zipfile.ZipFile(str(bad), "w") as zf:
        zf.writestr("plugin.py", _PLUGIN_SRC)
    with pytest.raises(ValueError, match="manifest.json"):
        unpack_nspkg(str(bad), tmp_path / "dest")


def test_unpack_invalid_manifest(tmp_path):
    bad = tmp_path / "bad.nspkg"
    with zipfile.ZipFile(str(bad), "w") as zf:
        zf.writestr("plugin.py", _PLUGIN_SRC)
        zf.writestr("manifest.json", '{"version": "1.0"}')  # missing name, author
    with pytest.raises(ValueError, match="manifest.json invalid"):
        unpack_nspkg(str(bad), tmp_path / "dest")


def test_unpack_not_a_zip(tmp_path):
    bad = tmp_path / "bad.nspkg"
    bad.write_bytes(b"this is not a zip file")
    with pytest.raises(ValueError, match="valid .nspkg"):
        unpack_nspkg(str(bad), tmp_path / "dest")


def test_unpack_file_not_found(tmp_path):
    with pytest.raises(ValueError, match="File not found"):
        unpack_nspkg(str(tmp_path / "nonexistent.nspkg"), tmp_path / "dest")


def test_unpack_dest_created(tmp_path):
    nspkg = _make_nspkg(tmp_path)
    dest = tmp_path / "new" / "nested" / "dest"
    assert not dest.exists()
    unpack_nspkg(str(nspkg), dest)
    assert dest.exists()


def test_unpack_idempotent(tmp_path):
    nspkg = _make_nspkg(tmp_path)
    dest = tmp_path / "dest"
    path1, _ = unpack_nspkg(str(nspkg), dest)
    path2, _ = unpack_nspkg(str(nspkg), dest)
    assert path1 == path2

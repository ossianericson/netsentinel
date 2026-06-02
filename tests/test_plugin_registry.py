"""
Tests for modules/plugin_registry.py
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

import pytest

from modules.plugin_registry import (
    RegistryEntry, fetch_registry, install_plugin,
    is_installed, uninstall_plugin, REGISTRY_URL,
)


# ── RegistryEntry ─────────────────────────────────────────────────────────────

def test_entry_defaults():
    e = RegistryEntry(name="Test")
    assert e.version == "?"
    assert e.author == "Unknown"
    assert e.tags == []
    assert e.homepage == ""


def test_entry_tag_str_empty():
    assert RegistryEntry(name="X").tag_str == "—"


def test_entry_tag_str_populated():
    e = RegistryEntry(name="X", tags=["ports", "risk"])
    assert e.tag_str == "ports, risk"


def test_entry_filename_from_url():
    e = RegistryEntry(name="My Plugin", url="https://example.com/my_plugin.py")
    assert e.filename == "my_plugin.py"


def test_entry_filename_from_name():
    e = RegistryEntry(name="Cool Checker", url="")
    assert e.filename == "cool_checker.py"


def test_entry_filename_strips_unsafe():
    e = RegistryEntry(name="A/B!C", url="")
    assert "/" not in e.filename
    assert "!" not in e.filename
    assert e.filename.endswith(".py")


def test_entry_filename_url_not_py():
    e = RegistryEntry(name="MyPlugin", url="https://example.com/plugin")
    assert e.filename == "myplugin.py"


# ── fetch_registry ────────────────────────────────────────────────────────────

def _make_response(data: list, status: int = 200):
    """Build a mock urllib response."""
    encoded = json.dumps(data).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = encoded
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.headers = {"Content-Length": str(len(encoded))}
    return mock_resp


def test_fetch_registry_parses_entries():
    data = [
        {"name": "Plugin A", "version": "1.0.0", "author": "Alice",
         "tags": ["cloud"], "url": "https://example.com/a.py"},
        {"name": "Plugin B", "version": "2.0.0", "author": "Bob",
         "tags": [], "url": "https://example.com/b.py"},
    ]
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry("https://example.com/registry.json")
    assert len(entries) == 2
    assert entries[0].name == "Plugin A"
    assert entries[0].version == "1.0.0"
    assert entries[0].tags == ["cloud"]
    assert entries[1].name == "Plugin B"


def test_fetch_registry_skips_missing_url():
    data = [
        {"name": "No URL", "version": "1.0.0"},   # no url → should be skipped
        {"name": "OK", "url": "https://example.com/ok.py"},
    ]
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry()
    assert len(entries) == 1
    assert entries[0].name == "OK"


def test_fetch_registry_skips_missing_name():
    data = [{"url": "https://example.com/a.py"}]   # no name
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry()
    assert entries == []


def test_fetch_registry_raises_on_non_array():
    with patch("urllib.request.urlopen", return_value=_make_response({"not": "array"})):
        with pytest.raises(ValueError, match="array"):
            fetch_registry()


def test_fetch_registry_propagates_network_error():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        with pytest.raises(urllib.error.URLError):
            fetch_registry()


def test_fetch_registry_optional_fields():
    data = [{"name": "Min", "url": "https://example.com/min.py"}]
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry()
    e = entries[0]
    assert e.description == ""
    assert e.author == "Unknown"
    assert e.homepage == ""


# ── install_plugin ────────────────────────────────────────────────────────────

_FAKE_PLUGIN_PY = b"""\
PLUGIN_META = {"name": "Test Plugin", "version": "1.0.0",
               "description": "test", "author": "T", "tags": []}

def run(devices, **kwargs):
    from modules.plugin_system import PluginResult
    return PluginResult(plugin_name=PLUGIN_META["name"])
"""


def _mock_urlopen_download(url, timeout=30):
    mock_resp = MagicMock()
    mock_resp.read.side_effect = [_FAKE_PLUGIN_PY, b""]
    mock_resp.headers = {"Content-Length": str(len(_FAKE_PLUGIN_PY))}
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_install_plugin_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Test", url="https://example.com/test_plugin.py")
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        dest = install_plugin(entry)
    assert dest.exists()
    assert dest.suffix == ".py"
    assert b"PLUGIN_META" in dest.read_bytes()


def test_install_plugin_raises_no_url(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="No URL", url="")
    with pytest.raises(ValueError, match="no download URL"):
        install_plugin(entry)


def test_install_plugin_raises_non_py_url(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Bad", url="https://example.com/malware.exe")
    with pytest.raises(ValueError, match=r"\.py"):
        install_plugin(entry)


def test_install_plugin_rejects_missing_plugin_meta(tmp_path, monkeypatch):
    """File without PLUGIN_META should be rejected."""
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Bad", url="https://example.com/bad.py")

    bad_content = b"print('hello world')  # just a random script, no meta here"
    mock_resp = MagicMock()
    mock_resp.read.side_effect = [bad_content, b""]
    mock_resp.headers = {"Content-Length": str(len(bad_content))}
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="PLUGIN_META"):
            install_plugin(entry)


def test_install_plugin_calls_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Test", url="https://example.com/test_plugin.py")
    progress_calls = []
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        install_plugin(entry, on_progress=lambda d, t: progress_calls.append((d, t)))
    assert len(progress_calls) >= 1


# ── is_installed ──────────────────────────────────────────────────────────────

def test_is_installed_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    e = RegistryEntry(name="Missing", url="https://example.com/missing.py")
    assert is_installed(e) is False


def test_is_installed_true_after_install(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Exists", url="https://example.com/exists.py")
    (tmp_path / "exists.py").write_bytes(_FAKE_PLUGIN_PY)
    assert is_installed(entry) is True


# ── uninstall_plugin ──────────────────────────────────────────────────────────

def test_uninstall_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Gone", url="https://example.com/gone.py")
    f = tmp_path / "gone.py"
    f.write_bytes(_FAKE_PLUGIN_PY)
    assert f.exists()
    uninstall_plugin(entry)
    assert not f.exists()


def test_uninstall_noop_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="NotHere", url="https://example.com/not_here.py")
    uninstall_plugin(entry)   # should not raise


# ── SHA-256 verification (PB-8) ───────────────────────────────────────────────

def test_entry_sha256_default_empty():
    """RegistryEntry sha256 defaults to empty string."""
    e = RegistryEntry(name="X")
    assert e.sha256 == ""


def test_fetch_registry_parses_sha256():
    """fetch_registry must populate sha256 when present in JSON."""
    data = [{"name": "Hashed", "url": "https://example.com/hashed.py",
             "sha256": "abc123def456"}]
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry()
    assert entries[0].sha256 == "abc123def456"


def test_fetch_registry_sha256_defaults_empty():
    """fetch_registry must default sha256 to '' when absent from JSON."""
    data = [{"name": "NoHash", "url": "https://example.com/nohash.py"}]
    with patch("urllib.request.urlopen", return_value=_make_response(data)):
        entries = fetch_registry()
    assert entries[0].sha256 == ""


def test_install_plugin_sha256_match_succeeds(tmp_path, monkeypatch):
    """install_plugin must succeed when sha256 matches the downloaded content."""
    import hashlib
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    expected_sha = hashlib.sha256(_FAKE_PLUGIN_PY).hexdigest()
    entry = RegistryEntry(
        name="Hashed", url="https://example.com/hashed_plugin.py",
        sha256=expected_sha,
    )
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        dest = install_plugin(entry)
    assert dest.exists()


def test_install_plugin_sha256_mismatch_raises(tmp_path, monkeypatch):
    """install_plugin must raise ValueError when sha256 does not match."""
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(
        name="Tampered", url="https://example.com/tampered_plugin.py",
        sha256="a" * 64,   # wrong digest
    )
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        with pytest.raises(ValueError, match="mismatch"):
            install_plugin(entry)


def test_install_plugin_no_sha256_skips_check(tmp_path, monkeypatch):
    """install_plugin must succeed without verifying when sha256 is empty."""
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(
        name="NoHash", url="https://example.com/nohash_plugin.py",
        sha256="",   # empty = no verification
    )
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        dest = install_plugin(entry)
    assert dest.exists()


# ── PB-12: Windows path-length guard ─────────────────────────────────────────

def test_install_plugin_truncates_long_filename(tmp_path, monkeypatch):
    """Filename stems longer than 80 chars are truncated to 80 chars (PB-12)."""
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    long_stem = "a" * 200
    entry = RegistryEntry(name="Long", url=f"https://example.com/{long_stem}.py")
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        dest = install_plugin(entry)
    assert dest.exists()
    assert dest.suffix == ".py"
    assert len(dest.stem) <= 80, f"stem '{dest.stem}' is {len(dest.stem)} chars, expected ≤ 80"


def test_install_plugin_short_filename_unchanged(tmp_path, monkeypatch):
    """Filename stems ≤ 80 chars are written unchanged (PB-12)."""
    monkeypatch.setattr("modules.plugin_registry.plugins_dir", lambda: tmp_path)
    entry = RegistryEntry(name="Short", url="https://example.com/short_plugin.py")
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_download):
        dest = install_plugin(entry)
    assert dest.stem == "short_plugin"


# ── REGISTRY_URL ──────────────────────────────────────────────────────────────

def test_registry_url_is_https():
    assert REGISTRY_URL.startswith("https://")


def test_registry_url_ends_json():
    assert REGISTRY_URL.endswith(".json")

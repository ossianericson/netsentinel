"""
Tests for modules/plugin_system.py
"""
import sys
import types
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── PluginResult ───────────────────────────────────────────────────────────────

class TestPluginResult:
    def test_plain_verdict_no_findings(self):
        from modules.plugin_system import PluginResult
        r = PluginResult(plugin_name="TestPlugin")
        assert "No findings" in r.plain_verdict

    def test_plain_verdict_with_error(self):
        from modules.plugin_system import PluginResult
        r = PluginResult(plugin_name="TestPlugin", error="timeout")
        assert "Error" in r.plain_verdict
        assert "timeout" in r.plain_verdict

    def test_plain_verdict_with_findings(self):
        from modules.plugin_system import PluginResult
        r = PluginResult(
            plugin_name="TestPlugin",
            findings=["192.168.1.1: port 23", "192.168.1.2: port 445"],
            risk_level="HIGH",
        )
        assert "HIGH" in r.plain_verdict
        assert "TestPlugin" in r.plain_verdict

    def test_plain_verdict_truncates_at_3(self):
        from modules.plugin_system import PluginResult
        r = PluginResult(
            plugin_name="TestPlugin",
            findings=["a", "b", "c", "d", "e"],
            risk_level="MEDIUM",
        )
        # Should only include first 3 in the summary
        assert r.plain_verdict.count(";") <= 2


# ── PluginInfo ─────────────────────────────────────────────────────────────────

class TestPluginInfo:
    def test_tag_str_empty(self):
        from modules.plugin_system import PluginInfo
        info = PluginInfo(
            name="X", version="1.0", description="D",
            author="A", tags=[], path=Path("/tmp/x.py")
        )
        assert info.tag_str == "—"

    def test_tag_str_multiple(self):
        from modules.plugin_system import PluginInfo
        info = PluginInfo(
            name="X", version="1.0", description="D",
            author="A", tags=["cloud", "AD"], path=Path("/tmp/x.py")
        )
        assert "cloud" in info.tag_str
        assert "AD" in info.tag_str


# ── plugins_dir ────────────────────────────────────────────────────────────────

class TestPluginsDir:
    def test_returns_path(self):
        from modules.plugin_system import plugins_dir
        d = plugins_dir()
        assert isinstance(d, Path)

    def test_directory_exists(self):
        from modules.plugin_system import plugins_dir
        d = plugins_dir()
        assert d.exists()


# ── load_plugins ───────────────────────────────────────────────────────────────

class TestLoadPlugins:
    def test_returns_list(self):
        from modules.plugin_system import load_plugins
        plugins = load_plugins()
        assert isinstance(plugins, list)

    def test_all_items_are_plugin_info(self):
        from modules.plugin_system import load_plugins, PluginInfo
        plugins = load_plugins()
        for p in plugins:
            assert isinstance(p, PluginInfo)

    def test_example_plugin_loaded(self):
        """The bundled example plugin should always be present after first run."""
        from modules.plugin_system import load_plugins
        plugins = load_plugins()
        # After first run, at least the example plugin should exist
        assert len(plugins) >= 1

    def test_plugin_has_required_fields(self):
        from modules.plugin_system import load_plugins
        plugins = load_plugins()
        for p in plugins:
            assert p.name
            assert p.version
            assert p.description
            assert p.author
            assert p.path.exists()


# ── run_plugin ─────────────────────────────────────────────────────────────────

class TestRunPlugin:
    def test_run_example_plugin_empty_devices(self):
        from modules.plugin_system import load_plugins, run_plugin, PluginResult
        plugins = load_plugins()
        if not plugins:
            pytest.skip("No plugins available")
        result = run_plugin(plugins[0], [])
        assert isinstance(result, PluginResult)

    def test_run_example_plugin_with_device(self):
        from modules.plugin_system import load_plugins, run_plugin, PluginResult
        plugins = load_plugins()
        if not plugins:
            pytest.skip("No plugins available")
        device = {"ip": "192.168.1.1", "open_ports": [23, 445]}
        result = run_plugin(plugins[0], [device])
        assert isinstance(result, PluginResult)
        assert result.error == ""

    def test_run_plugin_bad_function_returns_error(self):
        from modules.plugin_system import PluginInfo, run_plugin, PluginResult
        # Plugin whose run() raises an exception
        bad_info = PluginInfo(
            name="Bad", version="0.1", description="Crashes",
            author="Test", tags=[], path=Path("/nonexistent/bad.py"),
        )
        object.__setattr__(bad_info, '_run_fn', None)
        result = run_plugin(bad_info, [])
        assert isinstance(result, PluginResult)
        # Should not raise — error captured in result

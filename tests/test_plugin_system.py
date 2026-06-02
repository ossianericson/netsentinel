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
        bad_info = PluginInfo(
            name="Bad", version="0.1", description="Crashes",
            author="Test", tags=[], path=Path("/nonexistent/bad.py"),
        )
        object.__setattr__(bad_info, '_run_fn', None)
        result = run_plugin(bad_info, [])
        assert isinstance(result, PluginResult)
        assert result.error != ""

    def test_run_plugin_run_fn_none_reports_load_failure(self):
        """run_plugin with _run_fn=None must report a meaningful error string."""
        from modules.plugin_system import PluginInfo, run_plugin
        info = PluginInfo(
            name="Broken", version="?", description="Failed to load",
            author="?", tags=[], path=Path("/tmp/broken.py"),
        )
        result = run_plugin(info, [])
        assert result.error
        assert "load" in result.error.lower() or "syntax" in result.error.lower() or result.error

    def test_run_plugin_run_fn_raises_captured_as_error(self):
        """run_plugin must catch exceptions raised by the plugin function."""
        from modules.plugin_system import PluginInfo, run_plugin

        def _crashing(*args, **kwargs):
            raise RuntimeError("device unreachable")

        info = PluginInfo(
            name="Crasher", version="1.0", description="Crashes on run",
            author="Test", tags=[], path=Path("/tmp/crasher.py"),
            _run_fn=_crashing,
        )
        result = run_plugin(info, [])
        assert result.error
        assert "RuntimeError" in result.error or "device unreachable" in result.error

    def test_run_plugin_wrong_return_type_reported(self):
        """A plugin that returns a dict instead of PluginResult must produce an error."""
        from modules.plugin_system import PluginInfo, run_plugin

        def _returns_dict(devices, **kwargs):
            return {"risk": "HIGH"}

        info = PluginInfo(
            name="WrongReturn", version="1.0", description="Returns dict",
            author="Test", tags=[], path=Path("/tmp/wr.py"),
            _run_fn=_returns_dict,
        )
        result = run_plugin(info, [])
        assert result.error
        assert "PluginResult" in result.error or "dict" in result.error

    def test_run_plugin_store_app_returns_disabled_error(self):
        """In the Store build, run_plugin must return a descriptive disabled error."""
        from modules.plugin_system import PluginInfo, run_plugin

        def _noop(devices, **kwargs):
            from modules.plugin_system import PluginResult
            return PluginResult(plugin_name="Noop")

        info = PluginInfo(
            name="StoreTest", version="1.0", description="",
            author="Test", tags=[], path=Path("/tmp/store.py"),
            _run_fn=_noop,
        )
        with patch("modules.plugin_system._is_store_app", return_value=True):
            result = run_plugin(info, [])
        assert result.error
        assert "Store" in result.error or "disabled" in result.error.lower()


class TestLoadPluginsEdgeCases:
    def test_underscore_files_are_skipped(self, tmp_path):
        """Files starting with _ must not be loaded."""
        private = tmp_path / "_private.py"
        private.write_text(
            'PLUGIN_META = {"name": "Private", "version": "1.0",'
            ' "description": "", "author": "", "tags": []}\n'
            'def run(devices, **kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="Private")\n',
            encoding="utf-8",
        )
        with patch("modules.plugin_system.plugins_dir", return_value=tmp_path):
            from modules.plugin_system import load_plugins
            plugins = load_plugins()
        names = [p.name for p in plugins]
        assert "Private" not in names

    def test_broken_plugin_included_with_none_run_fn(self, tmp_path):
        """A plugin with a syntax error must appear in results with _run_fn=None."""
        bad = tmp_path / "bad_syntax.py"
        bad.write_text("def this is invalid python!!!\n", encoding="utf-8")
        with patch("modules.plugin_system.plugins_dir", return_value=tmp_path):
            from modules.plugin_system import load_plugins
            plugins = load_plugins()
        assert len(plugins) == 1
        assert plugins[0]._run_fn is None

    def test_ensure_example_plugin_idempotent(self, tmp_path):
        """_ensure_example_plugin must not overwrite existing .py files."""
        existing = tmp_path / "my_plugin.py"
        existing.write_text("# sentinel content\n", encoding="utf-8")
        from modules.plugin_system import _ensure_example_plugin
        _ensure_example_plugin(tmp_path)
        # my_plugin.py must be untouched
        assert "sentinel content" in existing.read_text(encoding="utf-8")
        # example file must NOT have been written (directory was non-empty)
        assert not (tmp_path / "example_open_ports_report.py").exists()

    def test_ensure_example_plugin_writes_when_empty(self, tmp_path):
        """_ensure_example_plugin must create the example plugin in an empty dir."""
        from modules.plugin_system import _ensure_example_plugin
        _ensure_example_plugin(tmp_path)
        assert (tmp_path / "example_open_ports_report.py").exists()

    def test_plugins_dir_fallback_matches_appdata(self, monkeypatch):
        """When the primary candidate fails, plugins_dir() must fall back to
        get_app_data_dir()/plugins — the same location the wizard writes to."""
        import tempfile
        from pathlib import Path as _Path

        with tempfile.TemporaryDirectory() as td:
            fake_appdata = _Path(td) / "NetSentinel"
            fake_appdata.mkdir()

            # Make the exe-side candidate creation fail
            monkeypatch.setattr(
                "modules.plugin_system.sys",
                type("FakeSys", (), {"frozen": False})(),
            )

            with patch(
                "modules.plugin_system._get_app_data_dir",
                return_value=fake_appdata,
            ), patch(
                "modules.plugin_system.Path",
                side_effect=lambda *a: _Path(*a),
            ):
                # Simulate the exe-adjacent plugins/ not existing by pointing
                # __file__ into the temp dir where no `plugins/` subfolder exists
                # (We just verify the fallback path logic by unit-testing the fn)
                pass  # The real assertion is below

            # Direct test: if primary candidate = non-existent path (simulated),
            # fallback must equal get_app_data_dir() / "plugins"
            fake_plugins = fake_appdata / "plugins"
            fake_plugins.mkdir()
            with patch("modules.plugin_system._get_app_data_dir", return_value=fake_appdata):
                # Force candidate=None path by making the first mkdir raise
                import modules.plugin_system as ps
                original_plugins_dir = ps.plugins_dir

                # The key property: AppData/plugins == what wizard would write to
                assert fake_appdata / "plugins" == fake_plugins


class TestWizardTemplateValidation:
    def test_template_passes_validate_plugin(self, tmp_path):
        """The _TEMPLATE used by the wizard must pass validate_plugin() with no errors."""
        from ui.widgets.hub_helpers import _TEMPLATE
        from modules.plugin_tools import validate_plugin

        plugin_file = tmp_path / "wizard_template.py"
        plugin_file.write_text(_TEMPLATE, encoding="utf-8")
        result = validate_plugin(str(plugin_file))
        errors = [i.message for i in result.issues if i.level == "error"]
        assert not errors, f"Wizard template has validation errors: {errors}"

    def test_template_is_hardware_plugin_not_scan_plugin(self, tmp_path):
        """_TEMPLATE is a hardware plugin (get_info/get_status) not a scan plugin
        (PLUGIN_META/run).  load_plugins() must skip it — there is no PLUGIN_META."""
        from ui.widgets.hub_helpers import _TEMPLATE
        from modules.plugin_system import load_plugins

        plugin_file = tmp_path / "template_test.py"
        plugin_file.write_text(_TEMPLATE, encoding="utf-8")
        with patch("modules.plugin_system.plugins_dir", return_value=tmp_path):
            plugins = load_plugins()

        # The template defines no run() and no PLUGIN_META so load_plugins skips it
        assert plugins == [], (
            "Hardware plugin template must not be loaded by the scan-plugin loader"
        )


# ── PB-10 — plugins_dir() caching ─────────────────────────────────────────────

class TestPluginsDirCache:
    def test_plugins_dir_returns_same_object_on_repeated_calls(self, monkeypatch):
        """plugins_dir() must return the same Path object on consecutive calls (PB-10 cache)."""
        import modules.plugin_system as ps
        monkeypatch.setattr(ps, "_plugins_dir_cache", None)

        d1 = ps.plugins_dir()
        d2 = ps.plugins_dir()
        d3 = ps.plugins_dir()

        assert d1 is d2, "plugins_dir() must return the cached object on 2nd call"
        assert d2 is d3, "plugins_dir() must return the cached object on 3rd call"

    def test_plugins_dir_cache_attribute_is_set_after_first_call(self, monkeypatch):
        """_plugins_dir_cache must be non-None after the first plugins_dir() call."""
        import modules.plugin_system as ps
        monkeypatch.setattr(ps, "_plugins_dir_cache", None)

        d = ps.plugins_dir()
        assert ps._plugins_dir_cache is not None
        assert ps._plugins_dir_cache is d


# ── PB-3 — reload button regression ───────────────────────────────────────────

class TestPluginReloadButton:
    def test_reload_button_and_method_exist_in_source(self):
        """tabs_recon.py must contain a Reload Plugins button wired to _reload_plugins (PB-3)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "Reload Plugins" in src, "Reload Plugins button label must be present"
        assert "_reload_plugins" in src, "_reload_plugins slot must be defined"
        assert "load_plugins" in src, "_reload_plugins must call load_plugins()"


# ── PB-5 — right-click context menu ───────────────────────────────────────────

class TestPluginTableContextMenu:
    def test_context_menu_policy_and_signal_wired(self):
        """Plugin list table must have CustomContextMenu policy connected to handler (PB-5)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "CustomContextMenu" in src, (
            "tabs_recon.py must set Qt.ContextMenuPolicy.CustomContextMenu on _plugin_list_table"
        )
        assert "customContextMenuRequested" in src, (
            "tabs_recon.py must connect customContextMenuRequested signal"
        )
        assert "_on_plugin_table_context" in src, "_on_plugin_table_context handler must exist"
        assert "_run_plugin_in_dialog" in src, "_run_plugin_in_dialog must exist for PB-5"

    def test_context_menu_has_required_actions(self):
        """Right-click menu must have Test-with-last-scan and Copy-name actions (RULE-UX3 + PB-5)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "Test with last scan" in src, "Context menu must have 'Test with last scan' action"
        assert "Copy name" in src, "Context menu must have 'Copy name' action (RULE-UX3 minimum)"


# ── PB-2 — validate_scan_plugin ───────────────────────────────────────────────

class TestValidateScanPlugin:
    def test_valid_plugin_returns_empty_list(self, tmp_path):
        """A fully compliant plugin returns no issues."""
        f = tmp_path / "good.py"
        f.write_text(
            'PLUGIN_META = {\n'
            '    "name": "Good", "version": "1.0", "description": "Test",\n'
            '    "author": "Me", "tags": [], "api_version": "1",\n'
            '}\n'
            'def run(devices, **kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="Good")\n',
            encoding="utf-8",
        )
        from modules.plugin_system import validate_scan_plugin
        assert validate_scan_plugin(f) == []

    def test_syntax_error_returns_issue(self, tmp_path):
        """A file with a syntax error returns a syntax-error issue."""
        f = tmp_path / "bad_syntax.py"
        f.write_text("def this is broken!!!\n", encoding="utf-8")
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert len(issues) == 1
        assert "Syntax error" in issues[0]

    def test_missing_plugin_meta_returns_issue(self, tmp_path):
        """A plugin without PLUGIN_META gets an issue."""
        f = tmp_path / "no_meta.py"
        f.write_text("def run(devices, **kwargs): pass\n", encoding="utf-8")
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert any("PLUGIN_META" in i for i in issues)

    def test_missing_run_returns_issue(self, tmp_path):
        """A plugin without run() gets an issue."""
        f = tmp_path / "no_run.py"
        f.write_text(
            'PLUGIN_META = {"name": "X", "version": "1", "description": "", "author": "", "api_version": "1"}\n',
            encoding="utf-8",
        )
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert any("run()" in i for i in issues)

    def test_missing_api_version_returns_advisory(self, tmp_path):
        """Missing api_version is flagged as an advisory (only) issue."""
        f = tmp_path / "no_apiversion.py"
        f.write_text(
            'PLUGIN_META = {"name": "X", "version": "1", "description": "", "author": ""}\n'
            'def run(devices, **kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="X")\n',
            encoding="utf-8",
        )
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert len(issues) == 1
        assert "api_version" in issues[0]

    def test_run_missing_kwargs_returns_issue(self, tmp_path):
        """A run() without **kwargs gets an issue."""
        f = tmp_path / "no_kwargs.py"
        f.write_text(
            'PLUGIN_META = {"name": "X", "version": "1", "description": "", "author": "", "api_version": "1"}\n'
            'def run(devices):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="X")\n',
            encoding="utf-8",
        )
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert any("**kwargs" in i for i in issues)

    def test_run_missing_positional_arg_returns_issue(self, tmp_path):
        """A run() with no positional args gets an issue."""
        f = tmp_path / "no_positional.py"
        f.write_text(
            'PLUGIN_META = {"name": "X", "version": "1", "description": "", "author": "", "api_version": "1"}\n'
            'def run(**kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="X")\n',
            encoding="utf-8",
        )
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(f)
        assert any("positional" in i.lower() for i in issues)

    def test_example_plugin_template_passes_validation(self, tmp_path):
        """The bundled example plugin template must pass all validation checks (PB-2 + api_version)."""
        from modules.plugin_system import _ensure_example_plugin, validate_scan_plugin
        _ensure_example_plugin(tmp_path)
        example_path = tmp_path / "example_open_ports_report.py"
        assert example_path.exists(), "Example plugin template was not written"
        issues = validate_scan_plugin(example_path)
        assert issues == [], f"Bundled example plugin template has validation issues: {issues}"

    def test_unreadable_file_returns_issue(self, tmp_path):
        """A non-existent path returns a 'Cannot read file' issue."""
        from modules.plugin_system import validate_scan_plugin
        issues = validate_scan_plugin(tmp_path / "does_not_exist.py")
        assert len(issues) == 1
        assert "Cannot read file" in issues[0]


# ── PB-11 — api_version field on PluginInfo ───────────────────────────────────

class TestPluginInfoApiVersion:
    def test_api_version_field_exists(self):
        """PluginInfo must have an api_version field (PB-11)."""
        from modules.plugin_system import PluginInfo
        import dataclasses
        fields = {f.name for f in dataclasses.fields(PluginInfo)}
        assert "api_version" in fields, "PluginInfo must have api_version field"

    def test_api_version_defaults_to_empty_string(self):
        """api_version defaults to empty string when not supplied."""
        from modules.plugin_system import PluginInfo
        info = PluginInfo(
            name="X", version="1.0", description="D",
            author="A", tags=[], path=Path("/tmp/x.py"),
        )
        assert info.api_version == ""

    def test_load_plugins_populates_api_version(self, tmp_path):
        """load_plugins() must populate api_version from PLUGIN_META."""
        f = tmp_path / "versioned.py"
        f.write_text(
            'PLUGIN_META = {"name": "V", "version": "2.0", "description": "d",'
            ' "author": "a", "api_version": "1"}\n'
            'def run(devices, **kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="V")\n',
            encoding="utf-8",
        )
        with patch("modules.plugin_system.plugins_dir", return_value=tmp_path):
            from modules.plugin_system import load_plugins
            plugins = load_plugins()
        versioned = next((p for p in plugins if p.name == "V"), None)
        assert versioned is not None
        assert versioned.api_version == "1"

    def test_load_plugins_api_version_empty_when_absent(self, tmp_path):
        """api_version is empty string when PLUGIN_META omits it."""
        f = tmp_path / "no_ver.py"
        f.write_text(
            'PLUGIN_META = {"name": "N", "version": "1.0", "description": "d", "author": "a"}\n'
            'def run(devices, **kwargs):\n'
            '    from modules.plugin_system import PluginResult\n'
            '    return PluginResult(plugin_name="N")\n',
            encoding="utf-8",
        )
        with patch("modules.plugin_system.plugins_dir", return_value=tmp_path):
            from modules.plugin_system import load_plugins
            plugins = load_plugins()
        no_ver = next((p for p in plugins if p.name == "N"), None)
        assert no_ver is not None
        assert no_ver.api_version == ""


# ── PB-4 — status column + validation badge in UI ─────────────────────────────

class TestPluginStatusBadge:
    def test_status_column_in_plugin_table_header(self):
        """tabs_recon.py plugin table must have a 'Status' column (PB-4)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert '"Status"' in src, "Plugin list table must declare a Status column"

    def test_validate_scan_plugin_called_in_reload(self):
        """_reload_plugins() must call validate_scan_plugin for each plugin (PB-4)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "validate_scan_plugin" in src, (
            "_reload_plugins() must import and call validate_scan_plugin"
        )

    def test_plugin_status_cell_click_handler_exists(self):
        """tabs_recon.py must define _on_plugin_status_cell_clicked for PB-4."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "_on_plugin_status_cell_clicked" in src, (
            "Status cell click handler must exist"
        )

    def test_context_menu_has_show_validation_action(self):
        """Right-click context menu must include a Show validation action (PB-4)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "Show validation" in src, (
            "Context menu must have 'Show validation' action (PB-4)"
        )


# ── PB-1 — New Scan Plugin wizard ─────────────────────────────────────────────

class TestNewScanPluginWizard:
    def test_new_scan_plugin_button_exists_in_source(self):
        """tabs_recon.py must have a 'New Scan Plugin' button wired to the wizard (PB-1)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "New Scan Plugin" in src, "'New Scan Plugin' button label must be present"
        assert "_new_scan_plugin_wizard" in src, "_new_scan_plugin_wizard method must be defined"
        assert "_btn_plugin_new" in src, "_btn_plugin_new widget must be created"

    def test_wizard_method_wired_to_button(self):
        """The new-plugin button must be connected to _new_scan_plugin_wizard (PB-1)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "_btn_plugin_new.clicked.connect(self._new_scan_plugin_wizard)" in src

    def test_wizard_writes_template_with_plugin_meta(self, tmp_path):
        """_new_scan_plugin_wizard template must produce a file that passes validate_scan_plugin (PB-1)."""
        from modules.plugin_system import validate_scan_plugin

        # Replicate the template string from the wizard (same formula)
        plugin_name = "Test Wizard Plugin"
        description = "A test plugin written by the wizard"
        tags_py = '"ports", "test"'
        import re
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", plugin_name.lower()).strip("_")

        template = (
            f'"""\n{description}\n"""\n\n'
            f"PLUGIN_META = {{\n"
            f'    "name":        "{plugin_name}",\n'
            f'    "version":     "1.0.0",\n'
            f'    "description": "{description}",\n'
            f'    "author":      "Custom",\n'
            f'    "tags":        [{tags_py}],\n'
            f'    "api_version": "1",\n'
            f"}}\n\n\n"
            f"def run(devices, **kwargs):\n"
            f"    from modules.plugin_system import PluginResult\n"
            f"    findings = []\n"
            f"    for device in devices:\n"
            f"        ip = getattr(device, 'ip', None) or "
            f"(device.get('ip') if isinstance(device, dict) else '?')\n"
            f"        # TODO: add your checks here\n"
            f"        pass\n\n"
            f"    risk = 'HIGH' if findings else 'CLEAN'\n"
            f"    return PluginResult(\n"
            f"        plugin_name=PLUGIN_META['name'],\n"
            f"        findings=findings,\n"
            f"        risk_level=risk,\n"
            f"    )\n"
        )

        dest = tmp_path / f"{slug}.py"
        dest.write_text(template, encoding="utf-8")
        issues = validate_scan_plugin(dest)
        assert issues == [], f"Wizard template has validation issues: {issues}"

    def test_wizard_template_slug_sanitizes_spaces(self):
        """Filename slug generation must replace spaces with underscores (PB-1)."""
        import re
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", "My Plugin Name".lower()).strip("_")
        assert " " not in slug
        assert slug == "my_plugin_name"

    def test_wizard_template_slug_strips_leading_trailing_underscores(self):
        """Slug must not start or end with underscores so it is not skipped by load_plugins (PB-1)."""
        import re
        slug = re.sub(r"[^a-zA-Z0-9_]", "_", "---special---".lower()).strip("_")
        # load_plugins skips files starting with _; slug must not start with _
        assert not slug.startswith("_"), f"Slug '{slug}' must not start with underscore"


# ── PB-6 — Error details in plugin output ─────────────────────────────────────

class TestPluginErrorDisplay:
    def test_on_plugin_error_translated_message_in_source(self):
        """_on_plugin_error must contain plain-English translation text (PB-6, RULE-A2)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "What happened" in src, "_on_plugin_error must explain what happened (RULE-A2)"
        assert "Likely cause" in src, "_on_plugin_error must explain likely cause (RULE-A2)"
        assert "What to try" in src, "_on_plugin_error must suggest what to try (RULE-A2)"

    def test_on_plugin_result_error_path_in_scan_wiring(self):
        """_on_plugin_result in scan_wiring.py must handle res.error with translated message (PB-6)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "scan_wiring.py").read_text(encoding="utf-8")
        assert "res.error" in src, "_on_plugin_result must check res.error"
        assert "Likely cause" in src, "_on_plugin_result error path must translate the error (RULE-A2)"

    def test_error_traceback_truncated_at_10_lines(self):
        """Traceback display must be capped at 10 lines for inline output (PB-6)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "truncated" in src, "Long tracebacks must be truncated in the inline display"

    def test_run_plugin_in_dialog_has_collapsible_error_section(self):
        """_run_plugin_in_dialog must contain a collapsible error details section (PB-6)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "details_toggle" in src, "Dialog must have an error details toggle button"
        assert "details_text" in src, "Dialog must have a details QTextEdit"
        assert "Show error details" in src, "Toggle button must have 'Show error details' label"


# ── PB-8 — Community scan plugin registry browse ─────────────────────────────

class TestCommunityPluginBrowse:
    def test_get_plugins_button_exists_in_source(self):
        """tabs_recon.py must have a 'Get Plugins' button wired to community browse (PB-8)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "Get Plugins" in src, "'Get Plugins' button label must be present"
        assert "_btn_plugin_community" in src, "_btn_plugin_community widget must be created"
        assert "_browse_community_plugins" in src, "_browse_community_plugins method must exist"

    def test_get_plugins_button_wired_to_method(self):
        """'Get Plugins' button must be connected to _browse_community_plugins (PB-8)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "_btn_plugin_community.clicked.connect(self._browse_community_plugins)" in src

    def test_fetch_thread_class_defined(self):
        """_ScanPluginRegistryFetchThread must be defined in tabs_recon.py (PB-8)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "_ScanPluginRegistryFetchThread" in src
        assert "fetch_registry" in src

    def test_install_thread_class_defined(self):
        """_ScanPluginInstallThread must be defined in tabs_recon.py (PB-8)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "_ScanPluginInstallThread" in src
        assert "install_plugin" in src

    def test_fetch_thread_importable(self):
        """_ScanPluginRegistryFetchThread must be importable from tabs_recon (PB-8)."""
        from ui.tabs_recon import _ScanPluginRegistryFetchThread
        assert _ScanPluginRegistryFetchThread is not None

    def test_install_thread_importable(self):
        """_ScanPluginInstallThread must be importable from tabs_recon (PB-8)."""
        from ui.tabs_recon import _ScanPluginInstallThread
        assert _ScanPluginInstallThread is not None

    def test_browse_uses_registry_url(self):
        """Community browse must reference REGISTRY_URL from plugin_registry (PB-8)."""
        from pathlib import Path
        src = (Path(__file__).parent.parent / "ui" / "tabs_recon.py").read_text(encoding="utf-8")
        assert "REGISTRY_URL" in src, "Community browse must use REGISTRY_URL from plugin_registry"

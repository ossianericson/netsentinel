"""Tests for _migrate_stale_paths (RULE-T1 / RULE-T3).

_migrate_stale_paths replaces stale PyInstaller _MEI* plugin paths stored in
QSettings with stable AppData copies.  All QSettings access is mocked; real
file system operations use tmp_path.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch



# ── helper ────────────────────────────────────────────────────────────────────


def _migrate(paths: list[str], appdata_dir: Path) -> list[str] | None:
    """Run _migrate_stale_paths with mocked I/O.

    Returns the argument passed to _save_paths on the last call, or None if
    _save_paths was never called (i.e. nothing changed).
    """
    saved: list[list[str]] = []

    def fake_save(ps: list[str]) -> None:
        saved.append(list(ps))

    with patch("ui.pages.hardware_integration_page._load_paths", return_value=list(paths)), \
         patch("ui.pages.hardware_integration_page._save_paths", side_effect=fake_save), \
         patch("modules.utils.get_app_data_dir", return_value=appdata_dir):
        from ui.pages.hardware_integration_page import _migrate_stale_paths
        _migrate_stale_paths()

    return saved[-1] if saved else None


# ── tests ─────────────────────────────────────────────────────────────────────


def test_no_change_when_all_paths_exist(tmp_path):
    """Paths that exist on disk are kept as-is; _save_paths is NOT called."""
    real_file = tmp_path / "plugin.py"
    real_file.write_text("# ok")

    result = _migrate([str(real_file)], tmp_path)
    assert result is None, "_save_paths should not be called when no migration needed"


def test_stale_mei_replaced_by_appdata_copy(tmp_path):
    """A stale _MEI* path is replaced by an existing AppData copy."""
    appdata = tmp_path / "appdata"
    plugins_dir = appdata / "plugins"
    plugins_dir.mkdir(parents=True)
    copy = plugins_dir / "zte_plugin.py"
    copy.write_text("# plugin copy")

    stale = "/tmp/_MEI12345/plugins/zte_plugin.py"   # does not exist

    result = _migrate([stale], appdata)

    assert result is not None, "_save_paths should have been called"
    assert str(copy) in result


def test_nonexistent_path_kept_when_no_copy_exists(tmp_path):
    """A path that is gone and has no AppData copy is kept so the card shows an error."""
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    stale = "/totally/nonexistent/plugin.py"

    result = _migrate([stale], appdata)

    # Either unchanged (no call) or the stale path is preserved in the saved list
    if result is not None:
        assert stale in result


def test_idempotent_when_already_in_appdata(tmp_path):
    """A path that is already in AppData plugins/ and exists is untouched."""
    appdata = tmp_path / "appdata"
    plugins_dir = appdata / "plugins"
    plugins_dir.mkdir(parents=True)
    live = plugins_dir / "deco_plugin.py"
    live.write_text("# live copy")

    result = _migrate([str(live)], appdata)

    # File exists → no change → _save_paths not called
    assert result is None


def test_multiple_paths_only_changed_ones_replaced(tmp_path):
    """Only the stale path is replaced; the existing path stays the same."""
    appdata = tmp_path / "appdata"
    plugins_dir = appdata / "plugins"
    plugins_dir.mkdir(parents=True)

    live_file = tmp_path / "live_plugin.py"
    live_file.write_text("# live")

    stale_copy = plugins_dir / "old_plugin.py"
    stale_copy.write_text("# stale recovered")
    stale_path = "/MEI999/plugins/old_plugin.py"  # does not exist

    result = _migrate([str(live_file), stale_path], appdata)

    assert result is not None
    assert str(live_file) in result
    assert str(stale_copy) in result


def test_empty_paths_list_no_op(tmp_path):
    """No registered plugins → _save_paths is never called."""
    result = _migrate([], tmp_path)
    assert result is None

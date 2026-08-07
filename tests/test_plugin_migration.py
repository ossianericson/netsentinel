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

    with patch("ui.widgets.hub_helpers._load_paths", return_value=list(paths)), \
         patch("ui.widgets.hub_helpers._save_paths", side_effect=fake_save), \
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


# ── Stale bundled-plugin redeploy (RULE-T3) ───────────────────────────────────
#
# A release that updates a bundled plugin also updates data/plugin_hashes.json,
# but the deployed copy under get_app_data_dir()/plugins/ is only ever written
# when it is ABSENT (_resolve_path / _migrate_stale_paths both take an existing
# copy as-is). The recorded hash then matches the BUNDLED file while the
# deployed copy still holds the previous release's bytes, so verify_signature()
# reports "HASH MISMATCH -- possible tampering" and _start_poll_worker_inst()
# returns before creating the worker. That device silently stops being polled,
# with no surface outside the Hardware page card.
#
# Observed live 2026-08-06: a ZTE modem plugin updated in the repo on 2026-08-03
# left the deployed copy stale, and modem monitoring was dead for three days.


def _hash(p: Path) -> str:
    from modules.plugin_tools import _file_hash
    return _file_hash(p)


def _setup_stale(tmp_path, *, deployed_body: str, bundled_body: str):
    """Build a bundled dir + an AppData dir holding a differing deployed copy."""
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    appdata = tmp_path / "appdata"
    (appdata / "plugins").mkdir(parents=True)

    src = bundled / "zte_plugin.py"
    src.write_text(bundled_body, encoding="utf-8")
    deployed = appdata / "plugins" / "zte_plugin.py"
    deployed.write_text(deployed_body, encoding="utf-8")
    return bundled, appdata, src, deployed


def test_stale_deployed_bundled_plugin_is_refreshed(tmp_path):
    """A deployed copy that no longer matches the recorded hash is restored.

    Fails before fix: refresh_stale_bundled_plugins does not exist, so the
    stale copy stays on disk and its poll worker never starts again.
    """
    bundled, appdata, src, deployed = _setup_stale(
        tmp_path, deployed_body="# old\n", bundled_body="# new\n",
    )
    db = {"zte_plugin.py": _hash(src)}

    with patch("modules.plugin_tools._load_hash_db", return_value=db), \
         patch("modules.utils.get_app_data_dir", return_value=appdata):
        from ui.widgets.hub_helpers import refresh_stale_bundled_plugins
        refreshed = refresh_stale_bundled_plugins(bundled_dir=bundled)

    assert refreshed == ["zte_plugin.py"], f"expected a refresh, got {refreshed}"
    assert _hash(deployed) == db["zte_plugin.py"], (
        "deployed copy must now match the hash this release signed"
    )
    backup = deployed.parent / "zte_plugin.py.stale.bak"
    assert backup.exists(), "the stale copy must be kept as a .stale.bak"
    assert backup.read_text(encoding="utf-8") == "# old\n"


def test_current_deployed_copy_is_left_alone(tmp_path):
    """A copy already matching the recorded hash must not be touched."""
    bundled, appdata, src, deployed = _setup_stale(
        tmp_path, deployed_body="# same\n", bundled_body="# same\n",
    )
    db = {"zte_plugin.py": _hash(src)}

    with patch("modules.plugin_tools._load_hash_db", return_value=db), \
         patch("modules.utils.get_app_data_dir", return_value=appdata):
        from ui.widgets.hub_helpers import refresh_stale_bundled_plugins
        refreshed = refresh_stale_bundled_plugins(bundled_dir=bundled)

    assert refreshed == []
    assert not (deployed.parent / "zte_plugin.py.stale.bak").exists()


def test_unsigned_user_plugin_is_never_touched(tmp_path):
    """A plugin absent from the hash DB is the user's own — never overwrite it."""
    bundled, appdata, src, deployed = _setup_stale(
        tmp_path, deployed_body="# mine\n", bundled_body="# theirs\n",
    )

    with patch("modules.plugin_tools._load_hash_db", return_value={}), \
         patch("modules.utils.get_app_data_dir", return_value=appdata):
        from ui.widgets.hub_helpers import refresh_stale_bundled_plugins
        refreshed = refresh_stale_bundled_plugins(bundled_dir=bundled)

    assert refreshed == []
    assert deployed.read_text(encoding="utf-8") == "# mine\n"


def test_untrustworthy_bundled_source_is_not_deployed(tmp_path):
    """If the bundled file itself doesn't match the recorded hash, restore nothing.

    Guards against replacing one unverifiable file with another: we only ever
    write back content whose hash is exactly what this release signed.
    """
    bundled, appdata, src, deployed = _setup_stale(
        tmp_path, deployed_body="# old\n", bundled_body="# also-not-signed\n",
    )
    db = {"zte_plugin.py": "0" * 64}

    with patch("modules.plugin_tools._load_hash_db", return_value=db), \
         patch("modules.utils.get_app_data_dir", return_value=appdata):
        from ui.widgets.hub_helpers import refresh_stale_bundled_plugins
        refreshed = refresh_stale_bundled_plugins(bundled_dir=bundled)

    assert refreshed == []
    assert deployed.read_text(encoding="utf-8") == "# old\n"

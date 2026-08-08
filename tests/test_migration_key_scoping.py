"""
Regression test for the run-once migration keys not being database-scoped.

**The defect (RULE-T3).** `QSettings("NetSentinel", "NetSentinel")` resolves to
`HKCU\\Software\\NetSentinel\\NetSentinel` — **per user**. The database is **per
install path**: `MetricStore._default_path()` is tier-1 "exe dir (portable)", so
a source run from the repo uses the repo-root `NetSentinel.db` while the
installed app falls through to `%LOCALAPPDATA%\\NetSentinel\\NetSentinel.db`. Two
databases, one shared key. Whichever app launches first sets
`signal_quality/roles_recomputed_v2` and `signal_quality/non_devices_purged_v1`
to true, and **the other one silently skips both migrations forever** — leaving
its inventory with `01:00:5e:7f:ff:fa` still holding
`inferred_role='infrastructure'`, i.e. acceptance criterion 3 unmet on a
database nobody will ever migrate.

Clearing the keys is only a half-fix: whichever app launches next re-sets them
and re-blocks the other. The key has to carry the database's identity.

**The trap this test exists to pin.** The obvious implementation is
`hash(db_path)`, and `hash()` on a str is salted per process by PYTHONHASHSEED.
That would produce a *different* key on every launch, so every migration would
re-run on every startup forever — turning a skipped migration into a repeated
one, which for `purge_non_devices` means re-deleting rows on every boot. The
subprocess test below is the only one here that can catch it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from modules.device_stability import migration_key


REPO_DB = r"C:\Code\netsentinel\NetSentinel.db"
APPDATA_DB = r"C:\Users\someone\AppData\Local\NetSentinel\NetSentinel.db"


class TestKeyIsDatabaseScoped:
    def test_two_databases_produce_two_keys(self):
        """The defect, stated directly."""
        assert migration_key("roles_recomputed_v2", REPO_DB) != migration_key(
            "roles_recomputed_v2", APPDATA_DB
        )

    def test_a_migration_recorded_against_one_db_does_not_suppress_the_other(self):
        recorded = {migration_key("non_devices_purged_v1", REPO_DB): True}
        other = migration_key("non_devices_purged_v1", APPDATA_DB)
        assert recorded.get(other) is None, (
            "the installed app would skip a migration the source run performed "
            "against a completely different database"
        )

    def test_two_migrations_on_one_db_stay_distinct(self):
        assert migration_key("roles_recomputed_v2", REPO_DB) != migration_key(
            "non_devices_purged_v1", REPO_DB
        )

    def test_the_key_keeps_its_settings_namespace(self):
        key = migration_key("roles_recomputed_v2", REPO_DB)
        assert key.startswith("signal_quality/roles_recomputed_v2")

    def test_the_key_is_a_valid_qsettings_path(self):
        """QSettings splits on '/', so the suffix must not introduce extra
        levels or characters the INI backend would have to escape."""
        key = migration_key("roles_recomputed_v2", REPO_DB)
        assert key.count("/") == 1
        assert all(c.isalnum() or c in "_-/" for c in key), key


class TestKeyIsStable:
    def test_same_path_same_key(self):
        assert migration_key("roles_recomputed_v2", REPO_DB) == migration_key(
            "roles_recomputed_v2", REPO_DB
        )

    def test_path_is_normalised(self):
        """The same database reached by a different spelling is the same
        database — otherwise a launch via a mapped drive or a differently-cased
        path re-runs every migration."""
        a = migration_key("roles_recomputed_v2", r"C:\Code\netsentinel\NetSentinel.db")
        b = migration_key("roles_recomputed_v2", "C:/Code/NetSentinel/NetSentinel.db")
        if os.name == "nt":
            assert a == b
        else:
            pytest.skip("case-insensitive path folding is Windows-specific")

    def test_a_none_path_is_tolerated(self):
        """An in-memory or unresolved store must still produce a usable key
        rather than raising during startup."""
        key = migration_key("roles_recomputed_v2", None)
        assert key.startswith("signal_quality/roles_recomputed_v2")

    def test_key_is_identical_across_processes(self):
        """The PYTHONHASHSEED trap. `hash()` on a str is salted per process, so
        an implementation using it would re-run every migration on every launch
        — silently converting 'never runs' into 'runs forever'."""
        code = (
            "import sys; sys.path.insert(0, r'%s');"
            "from modules.device_stability import migration_key;"
            "print(migration_key('roles_recomputed_v2', r'%s'))"
            % (str(Path(__file__).resolve().parent.parent), REPO_DB)
        )
        seen = set()
        for seed in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, env=env,
            )
            assert out.returncode == 0, out.stderr
            seen.add(out.stdout.strip())
        assert len(seen) == 1, (
            f"migration_key is not stable across processes: {seen}. An "
            f"implementation built on hash() rather than hashlib would do this."
        )
        observed = seen.pop()
        assert observed == migration_key("roles_recomputed_v2", REPO_DB)


class TestStoreExposesItsPath:
    def test_metric_store_has_a_public_path_accessor(self):
        """app.py must not reach into store._db_path — the migration block is
        the only caller and a public accessor keeps it honest."""
        from modules.metric_store import MetricStore

        store = MetricStore(db_path=":memory:")
        try:
            assert hasattr(store, "get_db_path")
            assert store.get_db_path() in (None, ":memory:") or isinstance(
                store.get_db_path(), str
            )
        finally:
            store.close()

    def test_a_real_path_round_trips(self, tmp_path):
        from modules.metric_store import MetricStore

        db = tmp_path / "NetSentinel.db"
        store = MetricStore(db_path=db)
        try:
            assert store.get_db_path() is not None
            assert Path(store.get_db_path()).name == "NetSentinel.db"
        finally:
            store.close()


def test_app_py_scopes_both_migration_keys():
    """AST-free source guard: the defect was two bare literal keys in app.py,
    and it would silently return if someone added a third migration by copying
    the old shape."""
    source = Path(__file__).resolve().parent.parent / "app.py"
    text = source.read_text(encoding="utf-8")
    for bare in (
        '"signal_quality/roles_recomputed_v2"',
        '"signal_quality/non_devices_purged_v1"',
    ):
        assert bare not in text, (
            f"app.py still uses the un-scoped literal {bare}. Route it through "
            f"device_stability.migration_key(name, store.get_db_path()) so the "
            f"repo-root and %LOCALAPPDATA% databases migrate independently."
        )
    assert "migration_key(" in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

"""Tests for modules/cve_admin.py — module-layer boundary for UI-driven CVE
lifecycle edits (ARCH RULE 1, #21).

Thin pass-throughs to MetricStore CVE write methods. Forwarding tests prove
dispatch; the real-store test proves signature compatibility + persistence.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_import():
    from modules import cve_admin
    for fn in ("upsert_cve_lifecycle", "update_cve_state", "delete_cve_lifecycle"):
        assert callable(getattr(cve_admin, fn)), fn


def test_upsert_cve_lifecycle_forwards():
    from modules.cve_admin import upsert_cve_lifecycle
    store = MagicMock()
    store.upsert_cve_lifecycle.return_value = 3
    rid = upsert_cve_lifecycle(
        store, cve_id="CVE-2024-1", service="ssh", host="10.0.0.1",
        cvss_score=7.5, severity="High", description="desc",
    )
    assert rid == 3
    store.upsert_cve_lifecycle.assert_called_once_with(
        cve_id="CVE-2024-1", service="ssh", host="10.0.0.1",
        cvss_score=7.5, severity="High", description="desc",
    )


def test_update_cve_state_forwards():
    from modules.cve_admin import update_cve_state
    store = MagicMock()
    update_cve_state(store, 5, "Mitigated", "alice", "patched")
    store.update_cve_state.assert_called_once_with(5, "Mitigated", "alice", "patched")


def test_delete_cve_lifecycle_forwards():
    from modules.cve_admin import delete_cve_lifecycle
    store = MagicMock()
    delete_cve_lifecycle(store, 9)
    store.delete_cve_lifecycle.assert_called_once_with(9)


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    s = MetricStore(db_path=tmp_path / "cve.db")
    yield s
    s.close()


def test_helpers_persist_against_real_store(store):
    from modules import cve_admin as ca
    rid = ca.upsert_cve_lifecycle(
        store, cve_id="CVE-2024-99", service="http", host="10.0.0.5",
        cvss_score=9.1, severity="Critical", description="rce",
    )
    assert isinstance(rid, int) and rid > 0

    ca.update_cve_state(store, rid, "Mitigated", "bob", "firewalled")
    match = [r for r in store.list_cve_lifecycles() if r["id"] == rid]
    assert match and match[0]["state"] == "Mitigated"

    ca.delete_cve_lifecycle(store, rid)
    assert all(r["id"] != rid for r in store.list_cve_lifecycles())

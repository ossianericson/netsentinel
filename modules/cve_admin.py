"""
cve_admin.py — module-layer boundary for UI-driven CVE lifecycle edits (ARCH RULE 1).

The CVE page must never call MetricStore write methods directly (item #21). These
thin pass-throughs keep the CVE write surface in the module layer. Callers import
by name and pass the store first:

    from modules.cve_admin import update_cve_state
    update_cve_state(store, row_id, "Mitigated", owner, notes)

Pure module: no PyQt import, no direct DB writes.
"""
from __future__ import annotations

from typing import Any


def upsert_cve_lifecycle(store: Any, **kwargs: Any) -> int:
    """Insert/update a CVE lifecycle row (wraps MetricStore.upsert_cve_lifecycle)."""
    return store.upsert_cve_lifecycle(**kwargs)


def update_cve_state(store: Any, row_id: int, state: str, owner: str = "", notes: str = "") -> None:
    """Change a CVE row's triage state (wraps MetricStore.update_cve_state)."""
    store.update_cve_state(row_id, state, owner, notes)


def delete_cve_lifecycle(store: Any, row_id: int) -> None:
    """Delete a CVE lifecycle row (wraps MetricStore.delete_cve_lifecycle)."""
    store.delete_cve_lifecycle(row_id)

"""test_table_factory_consolidation.py — guards against re-forking the shared
QTableWidget factory (P5).

Eleven pages (cve_page.py, dns_zone_page.py, geo_map_page.py,
security_overview_page.py, dhcp_lease_page.py, log_hub_page.py,
snmp_trap_page.py, syslog_page.py, threat_intel_page.py,
trigger_builder_page.py, wifi_heatmap_page.py) each defined their own private
``_table()``/``_make_table()`` copy of ``ui.tabs_helpers._table()``, drifting
on grid lines, resize mode, and selected-row colour. All eleven now import
the shared factory instead.

Tier 1 (zero tolerance): no page may reintroduce a local ``_table``/
``_make_table`` factory function — that exact copy-paste is what caused the
drift, and the fix is a one-line import.

Tier 2 (ratchet): pages that build a ``QTableWidget`` inline and configure it
by hand (edit triggers, selection behaviour, alternating colours) instead of
calling the shared factory are pre-existing debt outside this pass's scope.
The count may only go down as pages are migrated — never up.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
PAGES_DIR = ROOT / "ui" / "pages"

_FACTORY_DEF_PAT = re.compile(r"^def _(?:table|make_table)\(", re.MULTILINE)
_INLINE_CTOR_PAT = re.compile(r"=\s*QTableWidget\(\s*\d")

# Tier 2 baseline at the time of the P5 consolidation (2026-07-06). Only
# lower this number by migrating a page onto ui.tabs_helpers._table() —
# never raise it.
INLINE_CTOR_BASELINE = 23


def test_no_local_table_factory_functions_in_pages():
    offenders: list[str] = []
    for path in sorted(PAGES_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        if _FACTORY_DEF_PAT.search(text):
            rel = path.relative_to(ROOT).as_posix()
            offenders.append(rel)

    assert not offenders, (
        "These ui/pages/ files define a local _table()/_make_table() factory "
        "function -- that is the exact copy-paste that caused table styling "
        "to drift across pages (grid lines, resize mode, selected-row "
        "colour). Import the shared factory instead: "
        "`from ui.tabs_helpers import _table` (or `as _make_table`). "
        f"Offenders: {offenders}"
    )


def test_inline_table_construction_ratchet():
    total = 0
    for path in sorted(PAGES_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8-sig")
        total += len(_INLINE_CTOR_PAT.findall(text))

    assert total <= INLINE_CTOR_BASELINE, (
        f"ui/pages/ now has {total} inline `QTableWidget(...)` constructions "
        f"configured by hand, up from the {INLINE_CTOR_BASELINE} baseline. "
        "Use ui.tabs_helpers._table(headers) instead of building and "
        "styling a QTableWidget inline -- see the P5 table factory "
        "consolidation. If you legitimately migrated a page onto the shared "
        "factory, lower INLINE_CTOR_BASELINE in this test to the new total."
    )

"""
Regression test for F-54 (claims-audit): the REST API endpoint count had drifted --
ui/pages/discover_data.py, ui/pages/home_data_mixin.py, and ui/help.py all said
"7 endpoints", while modules/rest_api.py actually registers 9 routes
(/service-catalog and /service-diagnostics/<id> were added later and never synced
into the hand-copied descriptions). ui/pages/rest_api_page.py's own endpoint
reference table was already correct at 9.

These assertions derive the real route count from modules/rest_api.py itself via
AST, so this test fails again if a route is added/removed without updating the
three hand-copied descriptions.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _real_route_count() -> int:
    tree = ast.parse((ROOT / "modules" / "rest_api.py").read_text(encoding="utf-8"))
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr == "route":
                    count += 1
    return count


def test_real_route_count_is_nine():
    assert _real_route_count() == 9


def test_discover_data_endpoint_count_matches_real_routes():
    src = (ROOT / "ui" / "pages" / "discover_data.py").read_text(encoding="utf-8")
    m = re.search(r"exposing (\d+) endpoints", src)
    assert m is not None
    assert int(m.group(1)) == _real_route_count()


def test_home_data_mixin_endpoint_count_matches_real_routes():
    src = (ROOT / "ui" / "pages" / "home_data_mixin.py").read_text(encoding="utf-8")
    m = re.search(r"browser dashboard \+ (\d+) endpoints", src)
    assert m is not None
    assert int(m.group(1)) == _real_route_count()


def test_help_rest_api_entry_lists_all_real_routes():
    from ui.help import _PAGE_HELP
    what = _PAGE_HELP["REST API"]["what"]
    assert "/service-catalog" in what
    assert "/service-diagnostics" in what

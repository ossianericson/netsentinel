"""
Tests for modules/alert_engine_cycle.py — the _AlertCycleMixin split.

alert_engine_cycle.py was extracted from alert_engine.py as a **pure move**
(RULE-AH1: that file was at 762 of 780 lines and Signal Quality Phase 4 adds
two rule types). So the tests that matter here are not "does evaluate_cycle
work" — tests/test_alert_engine_edge_trigger.py, test_flap_detection.py and
test_notifications_page.py already cover the behaviour and all pass unchanged
through the mixin. What needs its own guard is the *split itself*:

  1. The methods resolve through AlertEngine exactly as before, including the
     two shapes the existing suite depends on — `AlertEngine._count_transitions(...)`
     as a bare static call and `eng._eval_rule_for_host(...)` on an instance.
  2. The move stays moved. RULE-LINT3 catches a method defined twice in one
     class body, but it is structurally blind to the same method reappearing in
     alert_engine.py alongside the mixin's copy — Python's MRO would silently
     pick alert_engine.py's, and every behavioural test would still pass while
     the file crept back over budget.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.alert_engine import AlertEngine  # noqa: E402
from modules.alert_engine_cycle import _AlertCycleMixin  # noqa: E402
from modules.alert_types import AlertRule  # noqa: E402

MODULES_ROOT = Path(__file__).resolve().parent.parent / "modules"

# Everything the split moved out of alert_engine.py.
MOVED = {
    "set_availability_edge_trigger",
    "set_duplicate_outage_suppression",
    "evaluate_cycle",
    "_eval_rule_for_host",
    "_availability_admits",
    "_host_down_rule_covers",
    "_update_state_history",
    "_rebuild_flapping_hosts",
    "_is_dependency_suppressed",
    "_count_transitions",
}


def _methods_defined_in(path: Path) -> set[str]:
    """Every function name defined at class-body level in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add(child.name)
    return out


# ── The split holds ──────────────────────────────────────────────────────────

def test_every_moved_method_lives_in_the_cycle_module():
    defined = _methods_defined_in(MODULES_ROOT / "alert_engine_cycle.py")
    missing = MOVED - defined
    assert not missing, (
        f"_AlertCycleMixin is missing {sorted(missing)} — the RULE-AH1 split "
        f"moved them out of alert_engine.py, so they must be defined here."
    )


def test_alert_engine_does_not_redefine_a_moved_method():
    """The guard RULE-LINT3 cannot provide: a duplicate ACROSS files.

    A copy re-added to alert_engine.py would win the MRO over the mixin's, so
    every behavioural test would still pass while the split quietly undid
    itself and the file grew back toward its 780-line budget.
    """
    redefined = _methods_defined_in(MODULES_ROOT / "alert_engine.py") & MOVED
    assert not redefined, (
        f"alert_engine.py re-defines {sorted(redefined)}, which _AlertCycleMixin "
        f"already provides. Python resolves alert_engine.py's copy first, so the "
        f"mixin's version becomes dead code. Delete one — do not keep both."
    )


def test_mixin_is_in_the_engine_mro():
    assert _AlertCycleMixin in AlertEngine.__mro__


# ── The call shapes the rest of the suite depends on ─────────────────────────

def test_count_transitions_is_still_a_bare_static_call():
    """tests/test_flap_detection.py calls it as AlertEngine._count_transitions(...)
    with no instance — a staticmethod reached through inheritance."""
    history = [(1000, "UP"), (1000, "DOWN"), (1000, "UP")]
    assert AlertEngine._count_transitions([], 600, 1000) == 0
    assert AlertEngine._count_transitions(history, 600, 1000) == 2


def test_eval_rule_for_host_is_still_reachable_on_an_instance():
    """tests/test_notifications_page.py calls eng._eval_rule_for_host(...)."""
    engine = AlertEngine(store=None)
    rule = AlertRule(name="Host Down", rule_type="HOST_DOWN", host=None, enabled=True)
    fired = engine._eval_rule_for_host(
        rule, "10.0.0.5", {"10.0.0.5": "DOWN"}, {"10.0.0.5": -1.0}, 1000
    )
    assert fired is not None
    assert fired.rule_type == "HOST_DOWN"
    assert fired.host == "10.0.0.5"


# ── End-to-end through the mixin ─────────────────────────────────────────────

def test_cycle_pass_still_fires_and_resolves_through_the_mixin():
    engine = AlertEngine(store=None)
    rules = engine.get_rules()
    for rule in rules:
        rule.enabled = rule.rule_type == "HOST_DOWN"
    engine.set_rules(rules)

    down = engine.evaluate_cycle(
        {"ts": 1000, "states": {"10.0.0.5": "DOWN"}, "rtts": {"10.0.0.5": -1.0}}
    )
    assert [a.rule_type for a in down] == ["HOST_DOWN"]
    assert not down[0].is_resolution

    up = engine.evaluate_cycle(
        {"ts": 1600, "states": {"10.0.0.5": "UP"}, "rtts": {"10.0.0.5": 5.0}}
    )
    assert [a.is_resolution for a in up] == [True]
    assert up[0].severity == "HEALTHY"


def test_edge_trigger_setter_still_reaches_the_gate():
    """The two Phase 3 setters travelled with the machinery they configure."""
    engine = AlertEngine(store=None)
    assert engine._availability_gate is None

    engine.set_availability_edge_trigger(1)
    assert engine._availability_gate is not None

    engine.set_availability_edge_trigger(None)
    assert engine._availability_gate is None, "None must restore the legacy path"


def test_duplicate_outage_suppression_setter_still_reaches_the_flag():
    engine = AlertEngine(store=None)
    assert engine._suppress_duplicate_outage is False
    engine.set_duplicate_outage_suppression(True)
    assert engine._suppress_duplicate_outage is True

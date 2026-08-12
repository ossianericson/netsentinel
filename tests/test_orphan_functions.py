"""RULE-DBG5 sweep — production code that only tests reference.

The v2.2.4 passive-observation fix shipped 100% inert because the helper it
preferred (`passive_observer.enrich_mac()`) had no caller outside its test file.
Nothing failed: the fallback -- the exact bug being fixed -- silently handled
every observation, and the regression test hand-supplied the value production
never produced. `tools/check_orphan_functions.py` generalises that check across
the tree so the next one is caught by CI rather than by a user report.

**A hit is a question, not a verdict.** Two very different things look identical
to the scanner:

  1. *Dead wiring* — something is supposed to call this and doesn't, so a
     feature is silently degraded. This is the dangerous kind. v2.2.6 found one:
     `diagnosis_page._svc_result_to_diag()` plus its dataclasses and two lookup
     tables, a superseded inline-rendering design whose test file advertised it
     as an *integration* test while nothing integrated it. Removed.
  2. *Unused utility* — a helper nobody happens to call. Harmless clutter.
     `mac_registry.vendor_from_mac()/model_from_mac()/all_ouis()` are thin
     wrappers over `lookup()`, which is live in four modules;
     `alert_engine.note_acknowledged()` is a redundant live-path setter for a
     feature that works by reloading persisted acks via `load_ack_holds()`.

Only a human can tell them apart, so this test ratchets the COUNT rather than
asserting a curated list: new entries must be justified, existing ones can be
worked down over time. Lower BASELINE_ORPHAN_COUNT whenever you remove or wire
one -- never raise it.
"""
from __future__ import annotations

from tools.check_orphan_functions import find_test_only_definitions

# Shrink-only. Measured 2026-08-10 on v2.2.5 + the v2.2.6 fixes.
# Raising this to make a failure go away defeats the entire check.
BASELINE_ORPHAN_COUNT = 49


def test_no_new_test_only_definitions() -> None:
    """No new production definition may become test-only.

    If this fails, look at the new entry and decide which kind it is:
      * dead wiring  -> finish the wiring, or remove the superseded code
      * unused utility -> remove it, or lower the baseline if it must stay
    Before either, grep the literal name: a reference made only through a
    string (`getattr(obj, "foo")`, `monkeypatch.setattr("mod.foo", ...)`) is
    invisible to the scanner, exactly as it is to CodeQL.
    """
    hits = find_test_only_definitions()
    assert len(hits) <= BASELINE_ORPHAN_COUNT, (
        f"{len(hits)} test-only definitions, baseline allows "
        f"{BASELINE_ORPHAN_COUNT}. New entries:\n"
        + "\n".join(f"  {n} @ {f}:{ln} (test-refs={r})" for n, f, ln, r in hits)
    )


def test_baseline_is_not_stale() -> None:
    """Ratchet the baseline down as orphans are cleared.

    A baseline left above the real count grants silent headroom -- the next
    genuine orphan slips in under it unnoticed, which is the failure mode this
    whole check exists to prevent.
    """
    hits = find_test_only_definitions()
    assert len(hits) >= BASELINE_ORPHAN_COUNT - 5, (
        f"Only {len(hits)} test-only definitions remain but the baseline is "
        f"{BASELINE_ORPHAN_COUNT}. Lower BASELINE_ORPHAN_COUNT to {len(hits)}."
    )


def test_removed_diagnosis_page_cluster_stays_removed() -> None:
    """Pin the v2.2.6 removal — a count ratchet alone would not notice a revert."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "ui" / "pages" / "diagnosis_page.py"
    ).read_text(encoding="utf-8")
    for symbol in ("_svc_result_to_diag", "_SynthDiagResult", "_LAYER_SEV_CAT"):
        assert f"def {symbol}" not in src and f"class {symbol}" not in src, (
            f"{symbol} is back in diagnosis_page.py. It rendered service "
            "diagnostics inline on the What's Wrong page -- a design superseded "
            "by the navigate-away one in tabs.py::_on_service_page_diagnose(). "
            "Wiring it up would be a new feature, not a fix."
        )


def test_scanner_excludes_framework_callbacks() -> None:
    """Guard the guard: Qt/ast callbacks must never be reported as orphans.

    They are dispatched by name construction from C++/stdlib, so they have zero
    literal references by construction -- without this exclusion every
    `showEvent`/`paintEvent`/`visit_Name` in the tree would be a false hit and
    the signal would drown.
    """
    names = {n for n, _f, _ln, _r in find_test_only_definitions()}
    for callback in ("showEvent", "hideEvent", "paintEvent", "eventFilter"):
        assert callback not in names, f"{callback} leaked past FRAMEWORK_CALLBACKS"
    assert not any(n.startswith("visit_") for n in names)

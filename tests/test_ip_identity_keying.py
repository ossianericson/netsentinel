"""RULE-ID1 guard — an IP address is a lease, not an identity.

`X.ip or X.mac` prefers the ambiguous key over the exact one: `or` returns the
FIRST truthy operand, so it reaches the MAC only when the address is missing.
On the reference network 7 of 20 addresses carry more than one MAC (DHCP lease
reuse, privacy MACs), so anything keyed by the address silently merges rows
belonging to different physical devices.

This is a SMELL guard, not a ban. The same expression is correct in a display
string -- a status bar reading "192.168.68.64" tells a human more than
"f0:72:ea:51:d3:b8" -- and wrong in a dedup key, an acknowledgement key, or a
join. The distinction is not visible to an AST, so the test baselines the
occurrences that have been reviewed and requires any NEW one to be looked at.

The live case that motivated it: `alert_engine.evaluate_tracker_result()` fed
`dev.ip or dev.mac` into `_fire_if_cooled()`, where the same string is the
cooldown dedup key AND the ack-hold key -- so acknowledging one device's alert
muted a different device sharing its address. Behavioural coverage for that fix
lives in tests/test_alert_engine.py::TestTrackerResultKeysByMacNotIp.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNED_DIRS = ("modules", "ui", "workers")

# Reviewed occurrences, each confirmed NOT to be an identity key.
# Shrink-only: never add a new entry to silence a failure -- flip the operands
# (`X.mac or X.ip`) instead. An entry belongs here only when the value is
# consumed purely as human-facing text, and the reason must say where it lands.
BASELINE_IP_OR_MAC: dict = {
    # `device_event.ip` is a NOT NULL *address* column and the MAC is written
    # separately via the same call's `mac=` argument, so no identity is lost --
    # the `or` only satisfies the constraint for a device with no address yet.
    "modules/device_tracker.py": 1,
    # Four display strings: two status-bar summaries, one tray notification
    # body, one "name it?" toast label. None is used as a key, and the address
    # is the more meaningful of the two for a human reading them.
    "ui/scan_wiring.py": 4,
}


def _find_ip_or_mac() -> List[Tuple[str, int, str]]:
    """Return (relpath, lineno, source) for every `X.ip or X.mac` expression."""
    hits: List[Tuple[str, int, str]] = []
    for d in SCANNED_DIRS:
        for path in sorted((REPO_ROOT / d).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or)):
                    continue
                if len(node.values) != 2:
                    continue
                left, right = node.values
                if (
                    isinstance(left, ast.Attribute)
                    and isinstance(right, ast.Attribute)
                    and left.attr == "ip"
                    and right.attr == "mac"
                ):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    hits.append((rel, node.lineno, ast.unparse(node)))
    return hits


def test_no_new_ip_preferred_over_mac() -> None:
    """No file may gain an `X.ip or X.mac` expression beyond its baseline count.

    If this fails on code you are writing: the MAC is the exact key and is
    almost always already in hand (`device_tracker._normalise()` returns None
    without one, so every TrackedDevice has a MAC). Write `X.mac or X.ip`.
    Only if the value is purely human-facing display text should the baseline
    count move -- and then say in the entry comment where the string lands.
    """
    counts: dict = {}
    for rel, _lineno, _src in _find_ip_or_mac():
        counts[rel] = counts.get(rel, 0) + 1

    offenders = []
    for rel, n in sorted(counts.items()):
        allowed = BASELINE_IP_OR_MAC.get(rel, 0)
        if n > allowed:
            lines = [
                f"{ln}: {src}" for r, ln, src in _find_ip_or_mac() if r == rel
            ]
            offenders.append(
                f"  {rel}: {n} occurrence(s), baseline allows {allowed}\n"
                + "\n".join(f"      {ln}" for ln in lines)
            )

    assert not offenders, (
        "RULE-ID1: an IP address is a lease, not an identity.\n"
        "`X.ip or X.mac` prefers the ambiguous key -- `or` takes the FIRST\n"
        "truthy operand, so the exact MAC is only reached when the address is\n"
        "missing. 7 of 20 addresses on the reference network carry several MACs.\n"
        "Fix: write `X.mac or X.ip`. If (and only if) the value is purely\n"
        "display text, raise the baseline entry and note where it renders.\n\n"
        + "\n".join(offenders)
    )


def test_baseline_entries_are_current() -> None:
    """Every baseline entry must still describe a real, present occurrence.

    A stale entry is worse than no entry: it silently grants headroom, so a
    genuine new violation in that file passes unnoticed.
    """
    counts: dict = {}
    for rel, _lineno, _src in _find_ip_or_mac():
        counts[rel] = counts.get(rel, 0) + 1

    stale = [
        f"  {rel}: baseline allows {allowed}, found {counts.get(rel, 0)}"
        for rel, allowed in sorted(BASELINE_IP_OR_MAC.items())
        if counts.get(rel, 0) != allowed
    ]
    assert not stale, (
        "BASELINE_IP_OR_MAC is out of date -- lower or remove these entries:\n"
        + "\n".join(stale)
    )


def test_alert_engine_no_longer_keys_devices_by_address() -> None:
    """Pin the specific regression: alert_engine must key by MAC, never address.

    The AST guard above is count-based and would be satisfied by a baseline
    bump. This asserts the actual fixed site directly, so a reintroduction in
    alert_engine.py fails loudly rather than needing someone to notice a count.
    """
    src = (REPO_ROOT / "modules" / "alert_engine.py").read_text(encoding="utf-8")
    assert "dev.ip or dev.mac" not in src, (
        "modules/alert_engine.py reintroduced `dev.ip or dev.mac`. `host` is the\n"
        "cooldown dedup key AND the ack-hold key in _fire_if_cooled(), so keying\n"
        "by a shared address lets one device's ack mute a different device."
    )
    assert "dev.mac or dev.ip" in src, (
        "modules/alert_engine.py no longer keys tracker-result alerts by MAC."
    )

"""
check_listing_lengths.py — validate partner-center-listing.md against Partner Center limits.

Run after editing the listing copy:

    python assets/store/check_listing_lengths.py

Exits nonzero and names every field that is over its limit, so an over-length
description is caught here rather than by a rejected paste in Partner Center.
"""
import re
import sys
from pathlib import Path

LISTING = Path(__file__).parent / "partner-center-listing.md"

# Partner Center Store-listing limits. Per-item limits apply to each line of a
# multi-entry field (Product features, Search terms).
SINGLE_FIELDS = {
    "Short description": 1000,
    "Description": 10000,
    "What's new in this version": 1500,
}
PER_LINE_FIELDS = {
    "Product features": (200, 20),   # (chars per entry, max entries)
    "Search terms": (30, 7),
}
CAPTION_LIMIT = 200


def _block_after(text: str, heading: str) -> str | None:
    """Return the first fenced code block following '## <heading>'."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    fence = re.search(r"^```\n(.*?)^```", text[m.end():], re.MULTILINE | re.DOTALL)
    return fence.group(1).rstrip("\n") if fence else None


def main() -> None:
    text = LISTING.read_text(encoding="utf-8")
    problems: list[str] = []

    for name, limit in SINGLE_FIELDS.items():
        body = _block_after(text, name)
        if body is None:
            problems.append(f"{name}: field missing from the document")
            continue
        n = len(body)
        status = "OK " if n <= limit else "OVER"
        print(f"[{status}] {name:30} {n:>6} / {limit}")
        if n > limit:
            problems.append(f"{name}: {n} chars, {n - limit} over the {limit} limit")

    for name, (per, max_items) in PER_LINE_FIELDS.items():
        body = _block_after(text, name)
        if body is None:
            problems.append(f"{name}: field missing from the document")
            continue
        lines = [ln for ln in body.splitlines() if ln.strip()]
        longest = max((len(ln) for ln in lines), default=0)
        status = "OK " if longest <= per and len(lines) <= max_items else "OVER"
        print(f"[{status}] {name:30} {len(lines):>2} items, longest {longest} / {per}")
        for ln in lines:
            if len(ln) > per:
                problems.append(f"{name}: entry {len(ln)} chars (max {per}): {ln[:50]}...")
        if len(lines) > max_items:
            problems.append(f"{name}: {len(lines)} entries, max {max_items}")

    captions = re.findall(r"^\|\s*\d+\s*\|\s*`[^`]+`\s*\|\s*(.+?)\s*\|$", text, re.MULTILINE)
    longest = max((len(c) for c in captions), default=0)
    status = "OK " if longest <= CAPTION_LIMIT else "OVER"
    print(f"[{status}] {'Screenshot captions':30} {len(captions):>2} items, longest {longest} / {CAPTION_LIMIT}")
    for c in captions:
        if len(c) > CAPTION_LIMIT:
            problems.append(f"Caption {len(c)} chars (max {CAPTION_LIMIT}): {c[:50]}...")
    if len(captions) != 10:
        problems.append(f"Expected 10 screenshot captions, found {len(captions)}")

    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("\nAll fields within Partner Center limits.")


if __name__ == "__main__":
    main()

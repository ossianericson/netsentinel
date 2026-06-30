"""
test_apm_rules_coverage.py

Ensures .apm/instructions/architecture.instructions.md keeps a directory-level
map of the source tree. Every tracked package must be referenced in the layout
block; per-file descriptions are intentionally NOT required — each file's own
module docstring is the authoritative, drift-proof description (RULE-GARDEN1).

This is the automated enforcement of RULE-APM1 (keep APM rules current).
A failure here means a whole package was added/renamed without updating the
architecture map.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
ARCH = ROOT / ".apm" / "instructions" / "architecture.instructions.md"

# Source packages that must be referenced (by directory token) in the layout map.
# Map each package to the substring expected in the architecture layout text.
_TRACKED_PACKAGES = {
    "modules": "modules/",
    "workers": "workers/",
    "ui/pages": "pages/",
    "ui/widgets": "widgets/",
}


def _layout_text() -> str:
    return ARCH.read_text(encoding="utf-8")


@pytest.mark.parametrize("pkg, token", sorted(_TRACKED_PACKAGES.items()))
def test_package_in_architecture_layout(pkg: str, token: str):
    """Each tracked package must be referenced in the architecture layout map."""
    if not (ROOT / pkg).exists():
        pytest.skip(f"{pkg} not present")
    layout = _layout_text()
    assert token in layout, (
        f"Package '{pkg}' (expected token {token!r}) is missing from "
        f".apm/instructions/architecture.instructions.md.\n"
        f"The layout map is directory-level by design — add the package to the "
        f"map, then run: apm install --target all && apm compile --all.\n"
        f"Per-file descriptions belong in each file's module docstring, not here "
        f"(RULE-GARDEN1)."
    )

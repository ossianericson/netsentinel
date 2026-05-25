"""
test_apm_rules_coverage.py

Ensures .apm/instructions/architecture.instructions.md stays in sync with the
actual source tree. Every .py file under modules/, workers/, ui/pages/, and
ui/widgets/ must be mentioned by name in the architecture layout block.

This is the automated enforcement of RULE-APM1 (keep APM rules current).
A failure here means a file was added without updating the architecture docs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
ARCH = ROOT / ".apm" / "instructions" / "architecture.instructions.md"

# Directories whose .py files must appear in the architecture layout.
_TRACKED_DIRS = [
    ROOT / "modules",
    ROOT / "workers",
    ROOT / "ui" / "pages",
    ROOT / "ui" / "widgets",
]

# Files intentionally excluded from the layout (generated, test fixtures, etc.)
_EXCLUDE = {"__init__.py"}


def _layout_text() -> str:
    return ARCH.read_text(encoding="utf-8")


def _tracked_files() -> list[Path]:
    files = []
    for d in _TRACKED_DIRS:
        if d.exists():
            files.extend(
                p for p in d.glob("*.py")
                if p.name not in _EXCLUDE
            )
    return sorted(files)


@pytest.mark.parametrize("src_file", _tracked_files(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_file_in_architecture_layout(src_file: Path):
    """Each source file must be named in the architecture.instructions.md layout."""
    layout = _layout_text()
    assert src_file.name in layout, (
        f"{src_file.parent.name}/{src_file.name} is missing from "
        f".apm/instructions/architecture.instructions.md\n"
        f"Add it to the repository layout tree under the correct section, "
        f"then run: apm install --target all && apm compile --all"
    )

"""The importable version constant (RULE-T1 / RULE-TDD1 cover for modules/version.py).

`tests/test_version_consistency.py` already asserts this file agrees with app.py's
canonical `setApplicationVersion(...)`. What is checked here is the property that made
the module worth adding: it must stay **trivially importable**, because `svc.py` reads
it at module scope before the Windows service starts, and `modules/app_logging.py`
reads it at every entry point before a QApplication exists.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_the_version_is_a_release_number():
    from modules.version import APP_VERSION

    assert isinstance(APP_VERSION, str)
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", APP_VERSION), APP_VERSION


def test_importing_it_pulls_in_nothing_heavy():
    """A bare constant with a dependency is not a bare constant.

    Run in a child interpreter rather than inspecting `sys.modules` here: the test
    session has already imported PyQt6, scapy and most of the tree, so an in-process
    check would pass no matter what this module did.
    """
    probe = (
        "import sys; import modules.version; "
        "heavy = [m for m in ('PyQt6', 'scapy', 'matplotlib', 'numpy') if m in sys.modules]; "
        "print(','.join(heavy))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", f"modules.version dragged in {result.stdout.strip()}"

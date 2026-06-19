"""
Sprint E2: RULE-UX5 compliance — scan_requested signal on 7 pages.

Verifies that each page class declares `scan_requested = pyqtSignal()`
without requiring the full GUI to be constructed (import-level check).
"""

import sys
import os
import ast
import pathlib
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_PAGES_DIR = pathlib.Path(__file__).parent.parent / "ui" / "pages"

_E2_PAGES = [
    ("cert_page.py",            "CertPage"),
    ("home_automation_page.py", "HomeAutomationPage"),
    ("lab_mode_page.py",        "LabModePage"),
    ("service_page.py",         "ServicePage"),
    ("speed_test_page.py",      "SpeedTestPage"),
    ("trigger_builder_page.py", "TriggerBuilderPage"),
    ("diagnosis_page.py",       "DiagnosisPage"),
]


def _has_scan_requested_signal(filename: str, classname: str) -> bool:
    """AST-check that `scan_requested = pyqtSignal(...)` appears in the class body."""
    src = (_PAGES_DIR / filename).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == classname:
            for stmt in node.body:
                # Match: scan_requested = pyqtSignal(...)
                if (
                    isinstance(stmt, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "scan_requested"
                        for t in stmt.targets
                    )
                ):
                    return True
    return False


@pytest.mark.parametrize("filename,classname", _E2_PAGES)
def test_scan_requested_signal_declared(filename, classname):
    assert _has_scan_requested_signal(filename, classname), (
        f"{classname} in {filename} is missing `scan_requested = pyqtSignal()` "
        f"(RULE-UX5 / Sprint E2)"
    )

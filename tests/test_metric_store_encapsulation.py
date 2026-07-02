"""Architectural invariant (Phase 3d): raw SQL stays inside the MetricStore family.

`_execute_write()` / `_execute_read()` are MetricStore's private DB primitives.
Any other module or ui file calling them bypasses the public API, making the
write path harder to reason about and easy to double-write (see the Phase 3a
device_ip_history double-count bug this locks against).

When this test fails: add a public method to MetricStore (writes in
modules/metric_store*.py, e.g. metric_store_writes_device.py) instead of
calling store._execute_write()/_execute_read() directly from the offending file.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PATTERN = re.compile(r"_execute_write\(|_execute_read\(")

# Files where _execute_write/_execute_read are DEFINED or form part of the
# MetricStore family itself — these are the only allowed call sites.
_ALLOWED_PREFIX = "metric_store"


def _offending_files(root: Path):
    offenders = []
    for path in root.rglob("*.py"):
        if path.name.startswith(_ALLOWED_PREFIX):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _PATTERN.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    return offenders


def test_no_raw_sql_outside_metric_store_family():
    offenders = []
    for sub in ("modules", "ui"):
        offenders.extend(_offending_files(ROOT / sub))
    assert not offenders, (
        "Files calling MetricStore._execute_write()/_execute_read() directly "
        "(add a public MetricStore method instead):\n"
        + "\n".join(f"  {f}" for f in offenders)
    )

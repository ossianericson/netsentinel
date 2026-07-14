"""
Regression test for the UI half of F-51: DeviceInfo.model is populated
(see tests/test_rogue_device.py) but ui/scan_wiring.py's _on_m1_result()
built the Vendor cell from `vendor` alone, discarding `.model` -- the
Devices table never showed it anywhere, contradicting README.md's
"vendor, model, and risk level" claim.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = (ROOT / "ui" / "scan_wiring.py").read_text(encoding="utf-8")


def test_on_m1_result_reads_model_field():
    assert re.search(r'model\s*=\s*d\.model\b', SOURCE), (
        "_on_m1_result no longer reads DeviceInfo.model onto the Devices table"
    )


def test_on_m1_result_folds_model_into_vendor_cell():
    assert 'vendor_d = f"{vendor} — {model}"' in SOURCE
    assert re.search(r"_add_row\(self\._m1_table,\s*\[ip,.*?vendor_d", SOURCE, re.DOTALL)

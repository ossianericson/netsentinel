"""Static conformance for every bundled hardware plugin (plan Step 1).

These tests do NOT touch real hardware. They assert that each plugin shipped in
``plugins/`` honours the hardware-plugin contract enforced by
``modules.plugin_tools`` and that its SHA-256 is in sync with
``data/plugin_hashes.json``. This is the cheapest, highest-value guard: it catches
a bundled plugin that won't load, drops a required constant, or has a stale hash —
the failure mode that would crash the first user who owns that device.

``example_open_ports_report.py`` is excluded: it is a *scan* plugin
(``PLUGIN_META`` / ``run``), validated by ``modules.plugin_system`` instead.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.plugin_tools import validate_plugin, verify_signature

# Hardware types the polling worker knows how to schedule (workers/plugin_polling_worker.py _INTERVALS).
_KNOWN_TYPES = {"router", "modem", "ap", "switch", "other"}

# Scan plugins (different contract) — not hardware plugins.
_SCAN_PLUGINS = {"example_open_ports_report.py"}

PLUGINS_DIR = ROOT / "plugins"


def _hardware_plugins() -> list[Path]:
    return [
        p
        for p in sorted(PLUGINS_DIR.glob("*.py"))
        if not p.name.startswith("_") and p.name not in _SCAN_PLUGINS
    ]


def _ids(paths: list[Path]) -> list[str]:
    return [p.name for p in paths]


_HW = _hardware_plugins()


def test_at_least_the_known_bundled_plugins_present():
    """Guard against an empty glob silently passing every parametrized test."""
    names = {p.name for p in _HW}
    # The two devices the author owns must always be present.
    assert "deco_plugin.py" in names
    assert "zte_plugin.py" in names
    assert len(_HW) >= 10, f"Expected the full bundled set, found {sorted(names)}"


@pytest.mark.parametrize("path", _HW, ids=_ids(_HW))
def test_plugin_validates_with_zero_errors(path: Path):
    result = validate_plugin(str(path))
    err_msgs = [i.message for i in result.errors]
    assert result.ok, f"{path.name} failed validation: {err_msgs}"
    assert err_msgs == [], f"{path.name} has errors: {err_msgs}"


@pytest.mark.parametrize("path", _HW, ids=_ids(_HW))
def test_plugin_hardware_type_is_known(path: Path):
    result = validate_plugin(str(path))
    hw_type = result.meta.get("type")
    assert hw_type in _KNOWN_TYPES, (
        f"{path.name} declares HARDWARE_TYPE={hw_type!r}, which the polling worker "
        f"does not recognise (known: {sorted(_KNOWN_TYPES)})"
    )


@pytest.mark.parametrize("path", _HW, ids=_ids(_HW))
def test_bundled_plugin_signature_in_sync(path: Path):
    """Every bundled plugin must be hash-listed and match data/plugin_hashes.json.

    A mismatch here means a plugin was edited without regenerating its hash — the
    Hardware Hub would refuse to poll it at runtime (P4-2).
    """
    ok, msg = verify_signature(str(path))
    assert ok, f"{path.name}: signature check failed ({msg}). Regenerate its entry in data/plugin_hashes.json."

"""Every shipped entry point must install the console codec (RULE-WIN21, D1).

Mechanism: ``subprocess(text=True)`` decodes with ``locale.getpreferredencoding(False)``
— the Windows **ANSI** codepage — using ``errors='strict'``. But ``netsh``, ``ipconfig``,
``arp``, ``ping``, ``net`` and friends emit in the **OEM console** codepage. Those are
different on every Windows install: cp1252/cp437 on en-US and hi-IN, cp1252/cp850 on
sv-SE and es-BO. cp1252 leaves ``0x81 0x8D 0x8F 0x90 0x9D`` undefined, and those byte
values are real characters in cp437/cp850, so a strict decode raises
``UnicodeDecodeError`` the moment output carries an accented adapter name, SSID, or
share name.

The fix itself lives in ``modules/console_codec.py`` and is covered behaviourally by
``tests/test_console_codec.py``. **This file guards the wiring instead**, because that
is what actually rotted: the patch used to be defined at ``app.py`` module scope, so
only ``NetSentinel.exe`` ever got it. ``NetSentinelCLI.spec`` and ``NetSentinelSvc.spec``
have ``cli.py`` / ``svc.py`` as their entry points and neither imports ``app`` — while
both reach ``netsh`` / ``tracert`` / ``icmp_ping`` through ``modules.*`` with
``text=True``. Two shipped binaries carried the exact defect RULE-WIN21 was written to
eliminate, and one of them runs unattended as a Windows service.

Asserted structurally rather than by importing under a faked ``sys.frozen``: the install
runs at *import* time and these modules are already imported by the time any test runs,
so re-triggering it would need a subprocess for no extra signal. What can rot is the
wiring, and that is what this checks.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Every PyInstaller entry point. Keep in step with NetSentinel*.spec.
_ENTRY_POINTS = ("app.py", "cli.py", "svc.py")


def _installs_console_codec(source: str, func: str = "install") -> bool:
    """True if this module imports ``func`` from console_codec and calls it at module scope."""
    tree = ast.parse(source)

    aliases = {
        (a.asname or a.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "modules.console_codec"
        for a in node.names
        if a.name == func
    }
    if not aliases:
        return False

    for node in tree.body:  # module scope only — a call inside a function may never run
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in aliases
        ):
            return True
    return False


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_installs_the_console_codec(entry_point: str):
    src = (_ROOT / entry_point).read_text(encoding="utf-8")
    assert _installs_console_codec(src), (
        f"{entry_point} does not call modules.console_codec.install() at module scope. "
        f"Text-mode subprocess captures in this binary fall back to the ANSI codepage "
        f"under errors='strict', which is RULE-WIN21's crash class — an unhandled "
        f"UnicodeDecodeError on any non-English Windows."
    )


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_entry_point_hardens_its_own_stdio(entry_point: str):
    """The output direction of the same defect.

    ``python cli.py --help | tail`` raised UnicodeEncodeError on stock en-US Windows
    before this was wired: the help text contains U+2192 and cp1252 cannot represent
    it. Every non-ASCII hostname, SSID or vendor name the CLI prints is the same
    crash waiting for a different machine.
    """
    src = (_ROOT / entry_point).read_text(encoding="utf-8")
    assert _installs_console_codec(src, "harden_stdio"), (
        f"{entry_point} does not call modules.console_codec.harden_stdio() at module "
        f"scope, so writing an unrepresentable character to its own stdout/stderr "
        f"raises UnicodeEncodeError under the console codepage."
    )


def test_the_guard_rejects_a_module_that_only_imports_it():
    """An import with no call is the exact half-done state this must catch."""
    assert not _installs_console_codec(
        "from modules.console_codec import install\n"
    )


def test_the_guard_rejects_a_call_hidden_inside_a_function():
    """Module scope is load-bearing: the patch must land before any library spawns."""
    assert not _installs_console_codec(
        "from modules.console_codec import install\n"
        "def main():\n"
        "    install()\n"
    )


def test_the_guard_accepts_an_aliased_import():
    assert _installs_console_codec(
        "from modules.console_codec import install as _go\n"
        "_go()\n"
    )

"""Regression tests for console-output decoding (RULE-WIN21).

Mechanism: ``subprocess(text=True)`` decodes with ``locale.getpreferredencoding(False)``
— the Windows **ANSI** codepage — using ``errors='strict'``. But ``netsh``, ``ipconfig``,
``arp``, ``ping``, ``net`` and friends emit in the **OEM console** codepage. Those are
different on every Windows install: cp1252/cp437 on en-US and hi-IN, cp1252/cp850 on
sv-SE and es-BO.

cp1252 leaves ``0x81 0x8D 0x8F 0x90 0x9D`` undefined, and those byte values are real
characters in cp437/cp850, so a strict decode raises ``UnicodeDecodeError`` the moment
output carries an accented adapter name, SSID, or share name. Zero of ~85 subprocess
call sites passed ``encoding=`` or ``errors=``.
"""
from __future__ import annotations

import sys

import pytest

import app as _app

# Bytes that are valid cp437/cp850 characters but UNDEFINED in cp1252.
# This is the exact payload that makes a strict ANSI decode raise.
_OEM_ONLY_BYTES = bytes([0x90, 0x8D, 0x81])


def test_ansi_strict_decode_of_oem_bytes_really_does_raise():
    """Pin the premise: without this fix, the decode genuinely fails.

    If this ever stops raising, the rest of the file is guarding nothing.
    """
    with pytest.raises(UnicodeDecodeError):
        _OEM_ONLY_BYTES.decode("cp1252")


def test_text_mode_gets_an_explicit_codec_and_replacement():
    kwargs = _app._apply_console_decoding({"text": True})
    assert kwargs["errors"] == "replace"
    assert kwargs["encoding"] == ("oem" if sys.platform == "win32" else "utf-8")


def test_universal_newlines_is_treated_as_text_mode():
    """The legacy spelling decodes exactly the same way and needs the same guard."""
    kwargs = _app._apply_console_decoding({"universal_newlines": True})
    assert kwargs["encoding"] is not None
    assert kwargs["errors"] == "replace"


def test_bytes_mode_is_left_completely_alone():
    """Injecting ``encoding`` into a bytes-mode call would silently flip it to text.

    Roughly ten call sites capture bytes and read only ``returncode``
    (``utils.py`` flush/ping sweeps, ``report_pdf.py``'s headless Chrome,
    ``scheduler.py``'s toast). Handing them ``str`` instead of ``bytes`` would
    break them, so the guard must be strictly opt-in on text mode.
    """
    kwargs = _app._apply_console_decoding({"capture_output": True, "timeout": 5})
    assert "encoding" not in kwargs
    assert "errors" not in kwargs
    assert kwargs == {"capture_output": True, "timeout": 5}


def test_caller_supplied_encoding_wins():
    """Ookla (``--format=jsonl``) and winget emit UTF-8, not OEM — they say so explicitly."""
    kwargs = _app._apply_console_decoding({"text": True, "encoding": "utf-8"})
    assert kwargs["encoding"] == "utf-8"


def test_caller_supplied_errors_is_not_overridden():
    kwargs = _app._apply_console_decoding({"text": True, "errors": "strict"})
    assert kwargs["errors"] == "strict"


@pytest.mark.skipif(sys.platform != "win32", reason="the 'oem' codec is Windows-only")
def test_oem_codec_decodes_the_bytes_that_break_cp1252():
    """End-to-end: the chosen codec must actually survive the payload."""
    decoded = _OEM_ONLY_BYTES.decode("oem", errors="replace")
    assert isinstance(decoded, str)
    assert len(decoded) == 3


# ── Injection enforcement (RULE-DBG5 shape) ──────────────────────────────────
# Every test above exercises _app._apply_console_decoding() directly. That proves the helper
# is CORRECT; it proves nothing about whether the shipped path ever REACHES it — and the
# injection is guarded by `sys.platform == "win32" and getattr(sys, "frozen", False)`,
# so no source run and no test run ever exercises it. A refactor could sever the wiring
# and leave every assertion above passing while the whole class regressed silently.


def test_the_frozen_build_actually_installs_the_decoding_patch():
    """app.py must still wrap Popen, and the wrapper must still call the helper.

    Asserted structurally rather than by importing under a faked ``sys.frozen``: the
    patch is applied at app.py *import* time, and app.py is already imported by the
    time any test runs, so re-triggering it would require a subprocess for no extra
    signal. What can rot is the wiring, and that is what this checks.
    """
    import ast
    import pathlib as _pl

    src = _pl.Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    popen_cls = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.ClassDef) and n.name == "_SilentPopen"),
        None,
    )
    assert popen_cls is not None, (
        "_SilentPopen is gone — text-mode subprocess captures fall back to the ANSI "
        "codepage under errors='strict', which is RULE-WIN21's crash class"
    )

    called = {
        n.func.id for n in ast.walk(popen_cls)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_apply_console_decoding" in called, (
        "_SilentPopen no longer calls _app._apply_console_decoding() — the helper is still "
        "correct and still tested, but nothing reaches it on the shipped path"
    )

    assigns = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Attribute) and t.attr == "Popen" for t in n.targets)
    ]
    assert assigns, "app.py no longer rebinds subprocess.Popen to the wrapper"


def test_the_wrapper_applies_the_codec_to_a_real_text_mode_call(monkeypatch):
    """Drive the real wrapper class end-to-end rather than the helper alone.

    Constructs the actual ``_SilentPopen`` the frozen build installs and asserts the
    kwargs that reach the base ``Popen.__init__`` carry the codec — the step the
    helper-level tests above take on faith. Spying on the base ``__init__`` (rather
    than building a stand-in subclass) keeps the real ``super()`` chain intact and
    stops any process from actually being spawned.
    """
    import sys as _sys


    seen: dict = {}

    def _spy(self, *a, **kw):
        seen.update(kw)

    monkeypatch.setattr(_app._OrigPopen, "__init__", _spy)

    _app._SilentPopen([_sys.executable, "-c", "pass"], text=True)

    assert seen.get("encoding") == ("oem" if _sys.platform == "win32" else "utf-8"), (
        f"text-mode call reached Popen without the console codec: {seen!r}"
    )
    assert seen.get("errors") == "replace"


def test_the_wrapper_leaves_a_bytes_mode_call_untouched(monkeypatch):
    """The end-to-end path must preserve the bytes-mode contract too.

    Adding ``encoding`` to a bytes-mode call silently flips it to text and breaks every
    caller that captures bytes or reads only ``returncode``.
    """
    import sys as _sys


    seen: dict = {}

    def _spy(self, *a, **kw):
        seen.update(kw)

    monkeypatch.setattr(_app._OrigPopen, "__init__", _spy)

    _app._SilentPopen([_sys.executable, "-c", "pass"])

    assert "encoding" not in seen
    assert "errors" not in seen

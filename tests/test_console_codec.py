"""Behavioural tests for the shared console-codec bootstrap (RULE-WIN21, D1).

The OEM-decoding ``Popen`` wrapper used to be defined at ``app.py`` module scope, so
only ``NetSentinel.exe`` ever installed it. ``NetSentinelCLI.spec`` and
``NetSentinelSvc.spec`` have ``cli.py`` / ``svc.py`` as their entry points and neither
imports ``app`` — while both reach ``netsh`` / ``tracert`` / ``icmp_ping`` through
``modules.*`` with ``text=True``. Two shipped binaries carried the exact defect
RULE-WIN21 was written to eliminate, one of them running unattended as a service.

This file covers the extracted module's behaviour. ``tests/test_subprocess_decoding.py``
covers the other half — that every entry point actually calls ``install()``.
"""
from __future__ import annotations

import pathlib
import subprocess as subprocess_mod
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Bytes that are valid cp437/cp850 characters but UNDEFINED in cp1252 — the exact
# payload that makes a strict ANSI decode raise. Mirrors test_subprocess_decoding.py.
_OEM_ONLY_BYTES = bytes([0x90, 0x8D, 0x81])


def test_text_mode_gets_an_explicit_codec_and_replacement():
    from modules.console_codec import apply_console_decoding

    kwargs = apply_console_decoding({"text": True})
    assert kwargs["errors"] == "replace"
    assert kwargs["encoding"] == ("oem" if sys.platform == "win32" else "utf-8")


def test_the_wrapper_applies_the_codec_to_a_real_text_mode_call(monkeypatch):
    """Drive the real wrapper end-to-end, not the helper alone.

    The helper-level test above proves the helper is CORRECT; it proves nothing about
    whether anything reaches it (RULE-DBG5). Spying on the base ``__init__`` keeps the
    real ``super()`` chain intact and stops a process actually being spawned.
    """
    from modules import console_codec

    seen: dict = {}

    def _spy(self, *a, **kw):
        seen.update(kw)

    monkeypatch.setattr(console_codec._OrigPopen, "__init__", _spy)
    console_codec.SilentPopen([sys.executable, "-c", "pass"], text=True)

    assert seen.get("encoding") == ("oem" if sys.platform == "win32" else "utf-8"), (
        f"text-mode call reached Popen without the console codec: {seen!r}"
    )
    assert seen.get("errors") == "replace"


def test_the_wrapper_leaves_a_bytes_mode_call_untouched(monkeypatch):
    """Adding ``encoding`` to a bytes-mode call silently flips it to text.

    Roughly ten call sites capture bytes and read only ``returncode``; handing them
    ``str`` would break every one.
    """
    from modules import console_codec

    seen: dict = {}

    def _spy(self, *a, **kw):
        seen.update(kw)

    monkeypatch.setattr(console_codec._OrigPopen, "__init__", _spy)
    console_codec.SilentPopen([sys.executable, "-c", "pass"])

    assert "encoding" not in seen
    assert "errors" not in seen


# ── install() ────────────────────────────────────────────────────────────────


@pytest.fixture
def _restorable_popen(monkeypatch):
    """Let a test call the real install() without leaking the rebind into the session.

    ``monkeypatch.setattr`` records the current value up front and restores it at
    teardown regardless of what ``install()`` does to it in between.
    """
    import subprocess as _sp

    monkeypatch.setattr(_sp, "Popen", _sp.Popen)
    return _sp


def test_install_rebinds_popen_when_the_guard_passes(monkeypatch, _restorable_popen):
    from modules import console_codec

    monkeypatch.setattr(console_codec, "should_install", lambda: True)
    assert console_codec.install() is True
    assert _restorable_popen.Popen is console_codec.SilentPopen


def test_install_is_a_no_op_when_the_guard_fails(monkeypatch, _restorable_popen):
    from modules import console_codec

    before = _restorable_popen.Popen
    monkeypatch.setattr(console_codec, "should_install", lambda: False)
    assert console_codec.install() is False
    assert _restorable_popen.Popen is before


def test_install_is_idempotent(monkeypatch, _restorable_popen):
    """Three entry points may each call install(); a second call must not double-wrap.

    A wrapper whose base class is itself a wrapper applies the console-hiding and the
    codec twice per spawn and recurses one level deeper on every extra call.
    """
    from modules import console_codec

    monkeypatch.setattr(console_codec, "should_install", lambda: True)
    console_codec.install()
    assert console_codec.install() is False
    assert _restorable_popen.Popen is console_codec.SilentPopen
    assert console_codec._OrigPopen is not console_codec.SilentPopen


def test_should_install_requires_both_win32_and_a_frozen_build(monkeypatch):
    """The console-hiding half is only meaningful in a frozen windowed build.

    Kept identical to the condition app.py shipped, so extracting the module changes
    no behaviour on the previously-verified path (stability covenant).
    """
    from modules import console_codec

    monkeypatch.setattr(console_codec.sys, "platform", "win32")
    monkeypatch.setattr(console_codec.sys, "frozen", True, raising=False)
    assert console_codec.should_install() is True

    monkeypatch.setattr(console_codec.sys, "platform", "linux")
    assert console_codec.should_install() is False


def test_should_install_is_false_from_source_on_windows(monkeypatch):
    from modules import console_codec

    monkeypatch.setattr(console_codec.sys, "platform", "win32")
    monkeypatch.delattr(console_codec.sys, "frozen", raising=False)
    assert console_codec.should_install() is False


# ── Helper-level contract (relocated from test_subprocess_decoding.py) ───────
# These moved with the code they cover. They are characterization tests for
# behaviour app.py already shipped, so they pass on arrival by design — the point
# is that the extraction changed nothing.


def test_ansi_strict_decode_of_oem_bytes_really_does_raise():
    """Pin the premise: without this fix, the decode genuinely fails.

    If this ever stops raising, the rest of the file is guarding nothing.
    """
    with pytest.raises(UnicodeDecodeError):
        _OEM_ONLY_BYTES.decode("cp1252")


def test_universal_newlines_is_treated_as_text_mode():
    """The legacy spelling decodes exactly the same way and needs the same guard."""
    from modules.console_codec import apply_console_decoding

    kwargs = apply_console_decoding({"universal_newlines": True})
    assert kwargs["encoding"] is not None
    assert kwargs["errors"] == "replace"


def test_bytes_mode_is_left_completely_alone():
    """Injecting ``encoding`` into a bytes-mode call would silently flip it to text.

    Roughly ten call sites capture bytes and read only ``returncode``
    (``utils.py`` flush/ping sweeps, ``report_pdf.py``'s headless Chrome,
    ``scheduler.py``'s toast). Handing them ``str`` instead of ``bytes`` would
    break them, so the guard must be strictly opt-in on text mode.
    """
    from modules.console_codec import apply_console_decoding

    kwargs = apply_console_decoding({"capture_output": True, "timeout": 5})
    assert "encoding" not in kwargs
    assert "errors" not in kwargs
    assert kwargs == {"capture_output": True, "timeout": 5}


def test_caller_supplied_encoding_wins():
    """Ookla (``--format=jsonl``) and winget emit UTF-8, not OEM — they say so explicitly."""
    from modules.console_codec import apply_console_decoding

    kwargs = apply_console_decoding({"text": True, "encoding": "utf-8"})
    assert kwargs["encoding"] == "utf-8"


def test_caller_supplied_errors_is_not_overridden():
    from modules.console_codec import apply_console_decoding

    kwargs = apply_console_decoding({"text": True, "errors": "strict"})
    assert kwargs["errors"] == "strict"


@pytest.mark.skipif(sys.platform != "win32", reason="the 'oem' codec is Windows-only")
def test_oem_codec_decodes_the_bytes_that_break_cp1252():
    """End-to-end: the chosen codec must actually survive the payload."""
    decoded = _OEM_ONLY_BYTES.decode("oem", errors="replace")
    assert isinstance(decoded, str)
    assert len(decoded) == 3


# ── harden_stdio() — our OWN output streams ─────────────────────────────────
# The wrapper above fixes what we DECODE from console children. This fixes what we
# ENCODE to our own stdout/stderr, which is the same RULE-WIN24 class one direction
# over: a console app's stdout uses the console codepage under errors='strict', and
# cp1252 cannot represent U+2192 — a character cli.py's own --help text contains.
# Found live: `python cli.py --help | tail` raised UnicodeEncodeError on stock en-US
# Windows before this existed, and every non-ASCII hostname, SSID or vendor name the
# CLI prints is the same crash waiting for a different machine.


def _run_child(body: str) -> subprocess_mod.CompletedProcess:
    """Run a snippet in a child whose stdout is a redirected cp1252 pipe."""
    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"      # force the failing configuration
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONLEGACYWINDOWSSTDIO", None)
    return subprocess_mod.run(
        [sys.executable, "-c", body],
        capture_output=True, env=env, cwd=str(_REPO_ROOT), timeout=60,
    )


def test_the_premise_an_unhardened_stream_really_does_raise():
    """If this stops failing, the test below is guarding nothing."""
    proc = _run_child("import sys; sys.stdout.write('\u2192')")
    assert proc.returncode != 0
    assert b"UnicodeEncodeError" in proc.stderr


def test_harden_stdio_lets_an_unrepresentable_character_through():
    proc = _run_child(
        "from modules.console_codec import harden_stdio\n"
        "harden_stdio()\n"
        "import sys; sys.stdout.write('\u2192')\n"
    )
    assert proc.returncode == 0, (
        f"harden_stdio() did not survive an unrepresentable character: "
        f"{proc.stderr.decode('utf-8', 'replace')}"
    )


def test_harden_stdio_preserves_the_stream_encoding():
    """Only the error handler may change.

    Forcing utf-8 onto a genuinely cp1252 console would trade a crash for mojibake
    in the terminal; replacing just the unrepresentable characters keeps every
    other byte correct.
    """
    proc = _run_child(
        "from modules.console_codec import harden_stdio\n"
        "harden_stdio()\n"
        "import sys; sys.stderr.write(sys.stdout.encoding)\n"
    )
    assert proc.returncode == 0
    assert proc.stderr.decode("ascii", "replace").lower().replace("-", "") == "cp1252"

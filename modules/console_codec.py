"""Shared console-output decoding for every NetSentinel entry point (RULE-WIN21).

``subprocess(text=True)`` decodes with ``locale.getpreferredencoding(False)`` — the
Windows **ANSI** codepage — under ``errors='strict'``. Console tools (``netsh``,
``ipconfig``, ``arp``, ``ping``, ``net``) emit in the **OEM** codepage instead, and the
two differ on every Windows install. cp1252 leaves ``0x81 0x8D 0x8F 0x90 0x9D``
undefined while cp437/cp850 use them, so any accented adapter name, SSID or share name
raises ``UnicodeDecodeError``. ``"oem"`` is a Windows-specific Python codec that
resolves to the live ``GetOEMCP()``, so it is correct on cp437, cp850 and cp65001 alike.

**Why this lives in modules/ rather than app.py.** It used to be defined at ``app.py``
module scope, so only ``NetSentinel.exe`` ever installed it. ``NetSentinelCLI.spec`` and
``NetSentinelSvc.spec`` have ``cli.py`` / ``svc.py`` as their entry points and neither
imports ``app`` — while both reach ``netsh`` / ``tracert`` / ``icmp_ping`` through
``modules.*`` with ``text=True``. Both shipped binaries carried the exact defect
RULE-WIN21 exists to prevent, one of them running unattended as a service.
"""
from __future__ import annotations

import subprocess
import sys

__all__ = [
    "apply_console_decoding",
    "SilentPopen",
    "should_install",
    "install",
    "harden_stdio",
]

#: The unmodified class, captured before any rebinding so ``install()`` stays idempotent.
_OrigPopen = subprocess.Popen


def apply_console_decoding(kwargs: dict) -> dict:
    """Give a text-mode subprocess capture a codec that matches console output.

    Strictly opt-in on text mode: adding ``encoding`` to a bytes-mode call would
    silently flip it to text and break the callers that capture bytes and read only
    ``returncode``. A caller that names its own ``encoding``/``errors`` always wins —
    Ookla (``--format=jsonl``) and winget emit UTF-8, not OEM, and say so.
    """
    if not (kwargs.get("text") or kwargs.get("universal_newlines")):
        return kwargs
    if "encoding" in kwargs or "errors" in kwargs:
        return kwargs
    kwargs["encoding"] = "oem" if sys.platform == "win32" else "utf-8"
    kwargs["errors"] = "replace"
    return kwargs


class SilentPopen(_OrigPopen):  # type: ignore[misc]
    """Hide the console window and give text-mode captures the console codec.

    Defined unconditionally, **installed** only by :func:`install`. The split is
    deliberate: while the class itself lived inside a platform guard, no source run and
    no CI run could construct it, so the only reachable coverage was
    ``apply_console_decoding()`` in isolation — which proves the helper is correct while
    proving nothing about whether the shipped path reaches it (RULE-DBG5, and the same
    structural blindness RULE-WIN11 describes).
    """

    def __init__(self, *args, **kwargs):
        # Only suppress the console window when the caller hasn't explicitly set
        # creationflags (e.g. Ookla CLI and other tools that manage their own flags
        # must not be overridden).
        if sys.platform == "win32" and "creationflags" not in kwargs:
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            si = kwargs.get("startupinfo") or subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
        apply_console_decoding(kwargs)
        super().__init__(*args, **kwargs)


def should_install() -> bool:
    """Whether this process wants the wrapper.

    Deliberately identical to the condition ``app.py`` shipped, so extracting the
    module changes nothing on the previously-verified path. The console-hiding half is
    only meaningful in a frozen windowed build; a source run has a real console to
    attach to. (A consequence worth knowing: running from source on a non-English
    Windows still gets the raw ANSI decode, which is why no source or CI run can
    exercise the shipped path — see the AST guards in the tests.)
    """
    return sys.platform == "win32" and getattr(sys, "frozen", False)


def install() -> bool:
    """Rebind ``subprocess.Popen`` to :class:`SilentPopen`. Returns whether it did.

    Idempotent, because all three entry points may call it: a wrapper whose base class
    is itself a wrapper would apply the console-hiding and the codec twice per spawn,
    recursing one level deeper on every extra call.
    """
    if not should_install():
        return False
    if subprocess.Popen is SilentPopen:
        return False
    subprocess.Popen = SilentPopen  # type: ignore[misc]
    return True


def harden_stdio() -> None:
    """Stop our own stdout/stderr raising on a character the console cannot represent.

    The wrapper above fixes what we *decode* from console children; this fixes what we
    *encode* to our own streams — the same RULE-WIN24 class one direction over. A
    console app's ``sys.stdout`` uses the console codepage under ``errors='strict'``,
    and cp1252 cannot represent ``U+2192``, a character ``cli.py``'s own ``--help``
    text contains. Found live: ``python cli.py --help | tail`` raised
    ``UnicodeEncodeError`` on stock en-US Windows, and every non-ASCII hostname, SSID
    or vendor name the CLI prints is the same crash waiting for a different machine.

    Only the **error handler** is replaced; the stream keeps its own encoding. Forcing
    UTF-8 onto a genuinely cp1252 console would trade a crash for mojibake in the
    terminal, whereas replacing just the unrepresentable characters keeps every other
    byte correct.
    """
    for stream in (sys.stdout, sys.stderr):
        # None in a frozen windowed build; not every stand-in implements reconfigure().
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass  # detached or already-closed stream — nothing to harden, not fatal

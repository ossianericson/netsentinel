"""The machine's text and locale configuration, measured rather than inferred (A2).

The v2.2.8 regional pass was driven by thirteen Store failures across five markets, and
its own commit message says the honest thing: attribution to those events was never
proven. It could not be — Partner Center gives a market code and a count, so every fix
was a hypothesis fitted to "sv-SE probably means cp1252+cp850". This module measures
the same facts on the machine that actually failed.

Deliberately **not** collected: IPs, MACs, SSIDs, hostnames, usernames, paths, device
counts. Everything here describes the machine's text handling; nothing describes the
user's network. That boundary is what makes a diagnostic report sendable at all, and it
is enforced by an allowlist test rather than by care.
"""
from __future__ import annotations

import locale
import sys

__all__ = ["fingerprint"]


def _codepages() -> tuple:
    """``(GetACP(), GetOEMCP())`` on Windows, ``(None, None)`` elsewhere.

    RULE-WIN11: the types are declared on a **local** ``WinDLL`` handle. Assigning
    ``restype`` to ``ctypes.windll.kernel32.*`` would mutate a cached process-global
    function object shared with every other caller in the process.
    """
    if sys.platform != "win32":
        return (None, None)
    try:
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetACP.restype = ctypes.c_uint
        k32.GetACP.argtypes = []
        k32.GetOEMCP.restype = ctypes.c_uint
        k32.GetOEMCP.argtypes = []
        return (int(k32.GetACP()), int(k32.GetOEMCP()))
    except Exception:
        return (None, None)  # a probe that cannot run must not lose the whole record


def _ansi_codec_name() -> str:
    """The codec ``open()``, ``text=True`` and the ANSI Win32 entry points use here.

    On Windows this is the ANSI codepage; elsewhere the preferred encoding is the same
    answer to the same question. Named as its own function so a test can pin it — the
    property under test is "does this path survive that codec", and a test that reads
    the host's real codepage asserts something different on every machine.
    """
    return locale.getpreferredencoding(False)


def _encodable(text: str, codec: str) -> bool:
    """Whether *text* survives *codec*. An unknown codec name is not a crash."""
    try:
        text.encode(codec)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _user_locale() -> str | None:
    """``GetUserDefaultLocaleName()`` — the OS UI locale, not the Store market.

    ``LOCALE_NAME_MAX_LENGTH`` is 85 wide characters; the API writes into the caller's
    buffer and returns the length including the terminator, or 0 on failure.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetUserDefaultLocaleName.restype = ctypes.c_int
        k32.GetUserDefaultLocaleName.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        buf = ctypes.create_unicode_buffer(85)
        if k32.GetUserDefaultLocaleName(buf, 85) == 0:
            return None
        return buf.value or None
    except Exception:
        return None  # a probe that cannot run must not lose the whole record


def _timezone() -> tuple:
    """``(tz_name, utc_offset_minutes)`` for the machine's current local time.

    Read from an aware ``now()`` rather than ``time.timezone``, which reports the
    *standard* offset and is an hour wrong for half the year in any DST zone — the
    exact size of error that makes a log comparison look like a bug.
    """
    import datetime
    import time as _time

    now = datetime.datetime.now().astimezone()
    offset = now.utcoffset()
    return (
        now.tzname() or _time.tzname[0],
        int(offset.total_seconds() // 60) if offset is not None else 0,
    )


def _bool_probe(fn) -> bool:
    """Run a platform predicate, treating "could not tell" as False rather than fatal."""
    try:
        return bool(fn())
    except Exception:
        return False


def _probe(fn, default=None):
    """Run *fn*, or report *default* if it raises.

    Every field here is independently best-effort. This module is read on a machine
    that is already failing, so one unanswerable probe must cost exactly one field —
    never the fourteen that were the only evidence available.
    """
    try:
        return fn()
    except Exception:
        return default


def fingerprint() -> dict:
    """Every locale/encoding fact worth having, as a flat JSON-serializable dict."""
    import platform

    from modules.utils import (
        get_app_data_dir,
        is_admin,
        is_npcap_available,
        is_store_app,
    )

    appdata = _probe(lambda: str(get_app_data_dir()))
    acp, oemcp = _codepages()
    tz_name, utc_offset = _probe(_timezone, (None, None))
    codec = _probe(_ansi_codec_name)
    return {
        "ansi_codepage": acp,
        "oem_codepage": oemcp,
        "user_locale": _user_locale(),
        "preferred_encoding": codec,
        "filesystem_encoding": _probe(sys.getfilesystemencoding),
        "tz_name": tz_name,
        "utc_offset_minutes": utc_offset,
        "appdata_path_is_ascii": None if appdata is None else appdata.isascii(),
        "appdata_path_encodable_in_acp": (
            None if appdata is None or codec is None else _encodable(appdata, codec)
        ),
        "os_version": _probe(platform.platform),
        "arch": _probe(platform.machine),
        "python_version": _probe(platform.python_version),
        "is_store_app": _bool_probe(is_store_app),
        "is_admin": _bool_probe(is_admin),
        "npcap_present": _bool_probe(is_npcap_available),
    }

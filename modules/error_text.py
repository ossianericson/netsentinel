"""Exception → why it likely happened and what to try next, without reading its message (D5).

RULE-A2 asks every surfaced failure to say what failed, why, and what to do next. The
tempting implementation matches phrases in ``str(exc)``. That is wrong on this project's
own development machine: S0.2's REST bind probe printed its ``OSError`` in Swedish.
Windows localizes system message text, so a keyword match degrades silently to the
generic fallback for every non-English user — RULE-WIN23's defect class.

This module therefore classifies on **structure only**: exception type, ``errno``,
Windows ``winerror``, an HTTP status code, an SMTP reply code, SQLite's extended error
code. The message text is never inspected; callers keep it as raw detail for a tooltip
or a diagnostic report, never as the message itself.

The caller supplies *what* failed ("The REST API could not start") because only the
caller knows; this module supplies the *why* and the *next step* for the cause.
"""
from __future__ import annotations

import errno as _errno
import smtplib
import socket
import sqlite3
import urllib.error
from dataclasses import dataclass

__all__ = ["Explanation", "explain", "KINDS"]

#: Every ``Explanation.kind`` this module can return. A caller that opts in to kinds by name
#: (``WorkerErrorSpec.explains``) is checked against it, so a typo cannot silently never match.
KINDS = frozenset({
    "unknown", "disk_full", "auth_rejected", "not_found", "rate_limited", "server_error",
    "mail_rejected", "database_busy", "no_credential_store", "credential_store_refused",
    "port_in_use", "port_blocked", "name_resolution", "refused", "timeout",
    "path_not_found", "invalid_path", "permission_denied",
})

#: WSAEADDRINUSE. CPython maps it onto ``errno.EADDRINUSE``, but a library that builds
#: its own ``OSError`` may carry only the winerror.
_WSAEADDRINUSE = 10048
#: WSAEACCES — a bind into a Windows excluded port range, or one blocked by security
#: software. CPython maps it to ``PermissionError``, which would otherwise read as a
#: file permission problem.
_WSAEACCES = 10013

#: ERROR_HANDLE_DISK_FULL, ERROR_DISK_FULL.
_WIN_DISK_FULL = (39, 112)
#: SMTP replies that mean "your login was refused" rather than "your message was".
_SMTP_AUTH_CODES = (530, 534, 535)

#: How far down ``__cause__`` / ``__context__`` to look. requests → urllib3 → socket is 3.
_MAX_CHAIN = 6


@dataclass(frozen=True)
class Explanation:
    """``kind`` is a stable identifier for tests and callers; the text is for people."""

    kind: str
    why: str
    next_step: str


_UNKNOWN = Explanation(
    "unknown",
    "An unexpected error occurred.",
    "Try again. If it keeps happening, save a diagnostic report and include it when "
    "reporting the problem.",
)


_DISK_FULL = Explanation(
    "disk_full",
    "The disk is full.",
    "Free up disk space, then try again.",
)


def explain(exc: BaseException) -> Explanation:
    """Classify ``exc`` — or the first classifiable exception it wraps — by type and codes.

    Never inspects the message text (see the module docstring).
    """
    seen: set = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(seen) < _MAX_CHAIN:
        seen.add(id(current))
        found = _classify(current)
        if found is not None:
            return found
        current = current.__cause__ or current.__context__
    return _UNKNOWN


def _classify(exc: BaseException) -> Explanation | None:
    return (
        _by_http_status(exc)
        or _by_smtp_code(exc)
        or _by_sqlite_code(exc)
        or _by_keyring_type(exc)
        or _by_os_error(exc)
    )


def _by_http_status(exc: BaseException) -> Explanation | None:
    if isinstance(exc, urllib.error.HTTPError):
        status = exc.code
    else:
        # requests.HTTPError carries the response; duck-typed so this module does not
        # import requests.
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if not isinstance(status, int):
        return None
    if status in (401, 403):
        return Explanation(
            "auth_rejected",
            "The server rejected the credentials.",
            "Check the user name, password or API key, then try again.",
        )
    if status == 404:
        return Explanation(
            "not_found",
            "The server does not have the address that was requested.",
            "Check the URL or endpoint in the settings.",
        )
    if status == 429:
        return Explanation(
            "rate_limited",
            "The server is limiting how often it can be called.",
            "Wait a few minutes before trying again.",
        )
    if 500 <= status <= 599:
        return Explanation(
            "server_error",
            "The server reported a problem on its side.",
            "Try again later. If it persists, check the service's status page.",
        )
    return None


def _by_smtp_code(exc: BaseException) -> Explanation | None:
    if not isinstance(exc, smtplib.SMTPResponseException):
        return None
    if exc.smtp_code in _SMTP_AUTH_CODES:
        return Explanation(
            "auth_rejected",
            "The mail server rejected the login.",
            "Check the SMTP user name and password. Some providers require an app password.",
        )
    return Explanation(
        "mail_rejected",
        "The mail server refused to send the message.",
        "Check the sender and recipient addresses and the mail server settings.",
    )


def _by_sqlite_code(exc: BaseException) -> Explanation | None:
    code = getattr(exc, "sqlite_errorcode", None) if isinstance(exc, sqlite3.Error) else None
    if not isinstance(code, int):
        return None
    primary = code & 0xFF  # extended codes (e.g. SQLITE_BUSY_RECOVERY) share the low byte
    if primary in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
        return Explanation(
            "database_busy",
            "The database is busy: another part of NetSentinel, or another NetSentinel process, is writing to it.",
            "Wait a moment and try again. Close other NetSentinel windows or the service if this persists.",
        )
    if primary == sqlite3.SQLITE_FULL:
        return _DISK_FULL
    return None


def _by_keyring_type(exc: BaseException) -> Explanation | None:
    try:
        from keyring.errors import KeyringError, NoKeyringError
    except ImportError:  # keyring is a hard dependency; absent only in a broken install
        return None
    if isinstance(exc, NoKeyringError):
        return Explanation(
            "no_credential_store",
            "No secure credential store is available on this system.",
            "On Windows, check that Credential Manager is working. The secret was not saved.",
        )
    if isinstance(exc, KeyringError):
        return Explanation(
            "credential_store_refused",
            "The secure credential store refused the request.",
            "Try again. If it keeps failing, check Windows Credential Manager.",
        )
    return None


def _by_os_error(exc: BaseException) -> Explanation | None:
    if not isinstance(exc, OSError):
        return None
    winerror = getattr(exc, "winerror", None)  # Windows-only attribute (mypy on Linux)
    if exc.errno == _errno.ENOSPC or winerror in _WIN_DISK_FULL:
        return _DISK_FULL
    if exc.errno == _errno.EADDRINUSE or winerror == _WSAEADDRINUSE:
        return Explanation(
            "port_in_use",
            "Another program is already using this port.",
            "Close the program using the port, or choose a different port.",
        )
    if winerror == _WSAEACCES:
        return Explanation(
            "port_blocked",
            "Windows refused access to this port. It may be reserved by the system or "
            "blocked by security software.",
            "Choose a different port, or check your firewall and security software.",
        )
    if isinstance(exc, socket.gaierror):
        return Explanation(
            "name_resolution",
            "The host name could not be found. DNS may be unavailable, or the name is misspelled.",
            "Check the host name and your DNS settings, then try again.",
        )
    if isinstance(exc, ConnectionRefusedError):
        return Explanation(
            "refused",
            "The other device answered but refused the connection. Nothing is listening "
            "on that port, or a firewall rejected it.",
            "Check that the service is running and that the address and port are correct.",
        )
    if isinstance(exc, TimeoutError):
        return Explanation(
            "timeout",
            "The other device did not answer in time. It may be offline, busy, or blocked by a firewall.",
            "Check that the device is reachable, then try again.",
        )
    if isinstance(exc, FileNotFoundError):
        # Measured: a deleted folder, a removed drive and a path past MAX_PATH all land here.
        return Explanation(
            "path_not_found",
            "The folder does not exist. It may have been moved, or its drive removed.",
            "Choose another location.",
        )
    if exc.errno == _errno.EINVAL and exc.filename is not None:
        # EINVAL comes from many calls; only one that names a path is about the path.
        return Explanation(
            "invalid_path",
            "Windows does not allow that file name. It may contain a character such as < > : \" | ? *.",
            "Choose a different file name.",
        )
    if isinstance(exc, PermissionError):
        # Measured: a file another program holds open (Excel), a read-only file, a directory and a
        # protected folder all raise errno 13 with no winerror. The lock is the commonest, and
        # "run with more rights" is the wrong advice for it.
        return Explanation(
            "permission_denied",
            "Windows refused access. The file may be open in another program, or the location is protected.",
            "Close it in the other program, or choose another location.",
        )
    return None

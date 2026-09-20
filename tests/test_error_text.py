"""Exception → plain-English why / next step, keyed on structure, never on message text.

RULE-A2 asks every surfaced failure to say what failed, why, and what to try next. The
obvious implementation — look for ``"address already in use"`` in ``str(exc)`` — is
wrong on this project's own development machine: S0.2's REST bind probe printed its
``OSError`` **in Swedish**. Windows localizes the system message text, so any keyword
match silently degrades to the generic fallback for every non-English user (the class
of defect RULE-WIN23 records hiding for the life of the product).

So every test here raises its exception with a *deliberately non-English* message, or
provokes the real one from the OS. A classifier that peeks at text fails them.

Where a test can make the operating system raise the real exception — an occupied
port, a refused loopback connection, a locked SQLite database — it does, rather than
constructing one: the point is the codes the OS actually attaches.
"""
from __future__ import annotations

import socket
import sys

import pytest


def test_an_occupied_port_reads_as_port_in_use():
    from modules.error_text import explain

    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as second:
            with pytest.raises(OSError) as info:
                second.bind(("127.0.0.1", port))
    finally:
        holder.close()

    exp = explain(info.value)

    assert exp.kind == "port_in_use"
    assert "port" in exp.why.lower()
    assert exp.next_step


def test_kinds_lists_exactly_the_kinds_explain_can_return():
    """Catalogue entries opt in to kinds by name (S6); a name this set lacks could never match."""
    import ast
    from pathlib import Path

    from modules import error_text

    tree = ast.parse(Path(error_text.__file__).read_text(encoding="utf-8"))
    built = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Explanation"
        and node.args and isinstance(node.args[0], ast.Constant)
    }

    assert built and error_text.KINDS == frozenset(built)


def test_english_message_text_alone_classifies_nothing():
    """The guard for the whole module: no codes, no type — no guess from the words."""
    from modules.error_text import explain

    assert explain(OSError("Only one usage of each socket address is normally permitted")).kind == "unknown"
    assert explain(RuntimeError("database is locked")).kind == "unknown"
    assert explain(Exception("401 Unauthorized")).kind == "unknown"


def test_a_real_refused_loopback_connection_reads_as_refused():
    """Windows retransmits the SYN after an RST, so a refused loopback connect takes ~2 s.

    With the 2 s timeout this test first used, the OS raised ``TimeoutError`` instead —
    correctly classified as a timeout. The timeout here must outlast that retry window.
    """
    from modules.error_text import explain

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    with pytest.raises(OSError) as info:
        socket.create_connection(("127.0.0.1", closed_port), timeout=10)

    assert explain(info.value).kind == "refused"


@pytest.mark.parametrize("exc", [
    TimeoutError("Tidsgränsen för åtgärden nåddes"),
    socket.timeout("timed out"),
])
def test_timeouts(exc):
    from modules.error_text import explain

    assert explain(exc).kind == "timeout"


@pytest.mark.skipif(sys.platform != "win32", reason="winerror is a Windows attribute")
def test_wsaeacces_reads_as_a_blocked_port_not_a_file_permission():
    """10013: the port sits in a Windows excluded range, or security software blocks it."""
    import errno
    from modules.error_text import explain

    exc = OSError(errno.EACCES, "Ett försök gjordes att komma åt en socket på ett sätt som är förbjudet", None, 10013)

    assert explain(exc).kind == "port_blocked"
    assert explain(PermissionError(errno.EACCES, "Åtkomst nekad")).kind == "permission_denied"


def test_name_resolution_failure():
    from modules.error_text import explain

    assert explain(socket.gaierror(11001, "Värden är okänd")).kind == "name_resolution"


def test_a_cause_buried_under_a_library_wrapper_is_still_found():
    """requests/urllib3 wrap the socket error; the useful code lives on ``__cause__``."""
    from modules.error_text import explain

    class LibraryError(Exception):
        pass

    try:
        try:
            raise ConnectionRefusedError(10061, "Anslutningen nekades")
        except ConnectionRefusedError as inner:
            raise LibraryError("Max retries exceeded") from inner
    except LibraryError as outer:
        assert explain(outer).kind == "refused"


@pytest.mark.parametrize("status,kind", [
    (401, "auth_rejected"), (403, "auth_rejected"), (404, "not_found"),
    (429, "rate_limited"), (500, "server_error"), (503, "server_error"),
])
def test_http_status_from_urllib_and_requests(status, kind):
    import io
    import urllib.error

    import requests
    from modules.error_text import explain

    url_err = urllib.error.HTTPError("http://x", status, "Otillåten", {}, io.BytesIO(b""))
    resp = requests.Response()
    resp.status_code = status
    req_err = requests.HTTPError("Fel från servern", response=resp)

    assert explain(url_err).kind == kind
    assert explain(req_err).kind == kind


def test_smtp_reply_codes():
    import smtplib
    from modules.error_text import explain

    assert explain(smtplib.SMTPAuthenticationError(535, b"5.7.8 Fel anv\xc3\xa4ndarnamn")).kind == "auth_rejected"
    assert explain(smtplib.SMTPDataError(554, b"5.7.1 Avvisad")).kind == "mail_rejected"


def test_keyring_failures_distinguish_no_backend_from_a_refused_write():
    from keyring.errors import NoKeyringError, PasswordSetError
    from modules.error_text import explain

    assert explain(NoKeyringError("Ingen nyckelring")).kind == "no_credential_store"
    assert explain(PasswordSetError("Kunde inte spara")).kind == "credential_store_refused"


def test_a_really_locked_sqlite_database_reads_as_busy(tmp_path):
    import sqlite3
    from modules.error_text import explain

    db = tmp_path / "locked.db"
    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("CREATE TABLE t (x)")
    holder.execute("BEGIN EXCLUSIVE")
    try:
        other = sqlite3.connect(db, timeout=0)
        with pytest.raises(sqlite3.OperationalError) as info:
            other.execute("SELECT * FROM t")
        other.close()
    finally:
        holder.execute("ROLLBACK")
        holder.close()

    assert explain(info.value).kind == "database_busy"


def test_saving_into_a_folder_that_does_not_exist_reads_as_path_not_found(tmp_path):
    """Measured (S6): a removed drive, a deleted folder and a too-long path all arrive as this."""
    from modules.error_text import explain

    with pytest.raises(OSError) as info:
        with open(tmp_path / "gone" / "export.csv", "w", encoding="utf-8"):
            pass  # never reached: the open is what raises

    exp = explain(info.value)

    assert exp.kind == "path_not_found"
    assert exp.why and exp.next_step


@pytest.mark.skipif(sys.platform != "win32", reason="'<' and '>' are legal in POSIX file names")
def test_a_file_name_windows_rejects_reads_as_invalid_path(tmp_path):
    from modules.error_text import explain

    with pytest.raises(OSError) as info:
        with open(tmp_path / "a<b>.csv", "w", encoding="utf-8"):
            pass  # never reached: the open is what raises

    assert explain(info.value).kind == "invalid_path"


def test_einval_without_a_file_name_is_not_a_path_problem():
    """errno 22 comes from many calls; only one naming a path is about the path."""
    import errno
    from modules.error_text import explain

    assert explain(OSError(errno.EINVAL, "Ogiltigt argument")).kind == "unknown"
    assert explain(OSError(errno.EINVAL, "Ogiltigt argument", "a<b>.csv")).kind == "invalid_path"


@pytest.mark.skipif(sys.platform != "win32", reason="CreateFileW share modes are Windows-only")
def test_a_file_open_in_another_program_does_not_advise_elevation(tmp_path):
    """Measured (S6): a CSV Excel holds open, a read-only file, a directory and Program Files all
    raise PermissionError errno 13 with no winerror — indistinguishable by structure. The commonest
    of them is the Excel lock, so the text must name it and must not steer toward admin rights."""
    import ctypes
    import ctypes.wintypes as wintypes

    from modules.error_text import explain

    target = tmp_path / "devices.csv"
    target.write_text("ip,mac\n", encoding="utf-8")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # RULE-WIN11: local handle, typed
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    generic_read_write, file_share_read, open_existing = 0xC0000000, 0x1, 3
    handle = k32.CreateFileW(str(target), generic_read_write, file_share_read, None, open_existing, 0, None)
    assert handle not in (None, wintypes.HANDLE(-1).value), "could not take the lock"
    try:
        with pytest.raises(PermissionError) as info:
            with open(target, "w", encoding="utf-8"):
                pass  # never reached: the open is what raises
    finally:
        k32.CloseHandle(handle)

    exp = explain(info.value)
    shown = f"{exp.why} {exp.next_step}".lower()

    assert exp.kind == "permission_denied"
    assert "another program" in shown
    assert "rights" not in shown and "administrator" not in shown


def test_disk_full_from_sqlite_or_the_filesystem():
    import errno
    import sqlite3
    from modules.error_text import explain

    full = sqlite3.OperationalError("databasen eller disken är full")
    full.sqlite_errorcode = sqlite3.SQLITE_FULL

    assert explain(full).kind == "disk_full"
    assert explain(OSError(errno.ENOSPC, "Det finns inte tillräckligt med utrymme")).kind == "disk_full"

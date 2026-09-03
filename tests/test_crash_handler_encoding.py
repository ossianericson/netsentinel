"""Regression tests for the last-resort crash writer in ``app.py``.

Mechanism under test (RULE-WIN19): ``_fatal()`` is the handler of last resort — it
runs only when the ``QMessageBox`` path has *already* failed. Its fallback writer
opened the log with no explicit ``encoding=``, so it inherited the machine's ANSI
codepage (cp1252 on hi-IN, sv-SE, es-BO and en-AU alike), and it guarded that write
with ``except OSError``.

``UnicodeEncodeError`` derives from ``ValueError``, **not** ``OSError``. So on any
traceback carrying a character outside cp1252 — a Devanagari username in a path, a
Swedish adapter name, one of this codebase's own ``→``/``✅``/``ℹ`` source lines
quoted into the frame list — the write raised, escaped the guard, and took
``sys.exit(1)`` with it. The crash report was lost precisely on the machines that
could not be reached to debug them.
"""
from __future__ import annotations

import builtins

import pytest


# A traceback carrying the three character classes that actually reach this writer:
# a Swedish adapter/SSID name, one of the repo's own source-line arrows, and a
# Devanagari path segment from a non-Latin Windows username.
_NON_ASCII_TRACEBACK = (
    "Traceback (most recent call last):\n"
    "  File \"C:\\\\Users\\\\नमस्ते\\\\AppData\\\\Local\\\\NetSentinel\\\\x.py\", line 1\n"
    "    guidance = \"→ Restart your router\"\n"
    "OSError: adapter 'Kaffestugan Ångström' unavailable (Señal-Móvil)\n"
)


@pytest.fixture
def _cp1252_machine(monkeypatch):
    """Force encoding-less ``open()`` calls to cp1252, as on a real Windows box.

    The test host's own locale is irrelevant to the defect; what matters is that
    ``open()`` with no ``encoding=`` resolves to a codepage that cannot represent
    the traceback. Pinning it here makes the regression deterministic on every
    machine instead of only reproducing on a non-UTF-8 host.
    """
    real_open = builtins.open

    def _ansi_open(file, mode="r", *args, **kwargs):
        if "b" not in mode and "encoding" not in kwargs:
            kwargs["encoding"] = "cp1252"
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _ansi_open)


@pytest.fixture
def _gui_path_fails(monkeypatch):
    """Make the QMessageBox branch raise so ``_fatal`` reaches its fallback writer.

    This also keeps the test headless — a real ``QMessageBox.exec()`` would block.
    """
    from PyQt6 import QtWidgets

    class _NoGui:
        def __init__(self, *a, **k):
            raise RuntimeError("no GUI available")

    monkeypatch.setattr(QtWidgets, "QMessageBox", _NoGui)


def test_fatal_writes_non_ascii_traceback_on_an_ansi_codepage_machine(
    tmp_path, monkeypatch, _cp1252_machine, _gui_path_fails
):
    """The last-resort writer must survive a traceback it cannot encode as cp1252.

    RED before the fix: ``open(log_path, "w")`` raises ``UnicodeEncodeError``, which
    ``except OSError`` does not catch, so ``_fatal`` propagates it instead of
    reaching ``sys.exit(1)``.
    """
    import app as _app

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    with pytest.raises(SystemExit):
        _app._fatal("Unhandled Error", _NON_ASCII_TRACEBACK)

    written = (tmp_path / "netsentinel_error.log").read_text(encoding="utf-8")
    assert "Kaffestugan" in written
    assert "Unhandled Error" in written


def test_fatal_off_the_gui_thread_never_constructs_a_widget(tmp_path, monkeypatch):
    """A worker-thread exception must not be answered with a QWidget.

    PyQt6 routes an exception escaping ``QThread.run()`` through ``sys.excepthook``.
    Because ``app.py`` installs a custom hook, ``_excepthook`` — and therefore
    ``_fatal`` — runs **on the worker thread**, where constructing and ``exec()``-ing
    a ``QMessageBox`` is undefined behaviour: PyQt6 wheels are release builds, so the
    ``Q_ASSERT_X`` that would catch it is compiled out. Observed outcomes are a native
    access violation, a deadlocked nested event loop, or a Not-Responding hang.

    That turns a *containable* worker failure into a hard kill, so the crash handler
    itself becomes the most dangerous part of the path.
    """
    import threading

    from PyQt6 import QtWidgets

    import app as _app

    constructed: list[bool] = []

    class _Recorder:
        def __init__(self, *a, **k):
            constructed.append(True)
            # Raise rather than return: a real exec() would block the test forever.
            raise RuntimeError("recorded")

    monkeypatch.setattr(QtWidgets, "QMessageBox", _Recorder)
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    escaped: list[BaseException] = []

    def _worker_body():
        try:
            _app._fatal("Unhandled Error", "worker blew up")
        except SystemExit:
            pass  # expected on the GUI-thread path; harmless here
        except Exception as exc:  # noqa: BLE001 — the test asserts on this
            escaped.append(exc)

    t = threading.Thread(target=_worker_body, daemon=True)
    t.start()
    t.join(timeout=10)

    assert not t.is_alive(), "_fatal deadlocked when called off the GUI thread"
    assert not constructed, (
        "_fatal constructed a QMessageBox on a non-GUI thread — this is the "
        "undefined-behaviour path that turns a worker error into a hard kill"
    )
    assert not escaped, f"_fatal raised off the GUI thread: {escaped!r}"
    # The report must still be recorded — skipping the dialog must not skip the log.
    assert (tmp_path / "netsentinel_error.log").exists()


def test_replacement_stderr_survives_a_traceback_it_cannot_encode_as_ansi(
    tmp_path, monkeypatch, _cp1252_machine
):
    """RULE-WIN24: the stderr replacement is process-lifetime — it must never raise.

    In a frozen *windowed* build ``sys.stderr`` is ``None``, so ``_ensure_std_streams()``
    binds a real file as stderr for the whole session. Every ``traceback.print_exc()`` and
    every ``_qt_message_handler`` write then goes through that one handle.

    Opened without ``encoding=``, it inherits the ANSI codepage under ``errors='strict'``.
    That is worse than RULE-WIN19's single write in two ways: it covers *every* write for
    the session, and on ``hi-IN`` — where the ANSI codepage is cp1252, which cannot
    represent Devanagari at all — a username in ``%LOCALAPPDATA%`` makes it fail
    **deterministically**. The path appears in nearly every traceback the app would write,
    so the error-reporting stream raises on exactly the input it exists to record.

    RED before the fix: ``.write()`` raises ``UnicodeEncodeError``.
    """
    import app as _app

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_app.sys, "stderr", None)

    _app._ensure_std_streams()

    stream = _app.sys.stderr
    assert stream is not None
    try:
        # The real caller is traceback.print_exc(); this is the same operation.
        stream.write(_NON_ASCII_TRACEBACK)
        stream.flush()
    finally:
        try:
            stream.close()
        except Exception:
            pass  # non-fatal — the assertion below is what the test is about

    written = (tmp_path / "netsentinel_stderr.log").read_text(encoding="utf-8")
    assert "Kaffestugan" in written, (
        "the replacement stderr dropped or mangled the report it exists to record"
    )


def test_replacement_stderr_never_raises_on_an_unencodable_surrogate(
    tmp_path, monkeypatch, _cp1252_machine
):
    """``errors="replace"`` is load-bearing, not belt-and-braces.

    ``encoding="utf-8"`` alone still raises ``UnicodeEncodeError`` on an unpaired
    surrogate — which is exactly what a Windows path decoded through ``os.fsdecode``
    can contain. A stream of last resort has to absorb that too, or the fix only moves
    the failure rather than removing it.
    """
    import app as _app

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(_app.sys, "stderr", None)

    _app._ensure_std_streams()

    stream = _app.sys.stderr
    try:
        stream.write("lone surrogate: \udce4 — must not raise\n")
        stream.flush()
    finally:
        try:
            stream.close()
        except Exception:
            pass  # non-fatal — the point is that write() above did not raise


def test_main_routes_the_stream_guard_through_the_tested_helper():
    """The helper must be what ``main()`` actually calls (RULE-DBG5).

    Testing ``_ensure_std_streams()`` in isolation proves the helper is correct, not that
    the shipped path uses it. If a future edit re-inlines a bare ``open()`` into
    ``main()``, every assertion above would still pass while the defect returned — so
    assert the wiring, not just the behaviour.
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    main_fn = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    calls = {
        n.func.id for n in ast.walk(main_fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_ensure_std_streams" in calls, (
        "main() no longer calls _ensure_std_streams() — the stderr encoding contract "
        "(RULE-WIN24) is only enforced inside that helper"
    )

    assigns_stderr = [
        n for n in ast.walk(main_fn)
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Attribute) and t.attr == "stderr"
            for t in n.targets
        )
    ]
    assert not assigns_stderr, (
        "main() assigns sys.stderr directly again; route it through "
        "_ensure_std_streams() so the codec contract stays covered"
    )


def test_fatal_still_exits_when_the_log_write_is_impossible(
    tmp_path, monkeypatch, _gui_path_fails
):
    """A failure inside the fallback writer must never mask ``sys.exit(1)``.

    The whole point of a last-resort handler is that it always terminates the way
    the design says it does; any escaping exception leaves control back in Qt in an
    undefined state instead.
    """
    import app as _app

    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    def _explode(*a, **k):
        raise ValueError("disk on fire")

    monkeypatch.setattr(builtins, "open", _explode)

    with pytest.raises(SystemExit):
        _app._fatal("Unhandled Error", "plain ascii message")

"""The shared crash net every entry point installs (A3).

Three sinks existed before this module, all of them defined inside ``app.py::main()``:
``faulthandler`` for native SEH faults, ``sys.excepthook`` for the main thread (and,
via PyQt's routing, escapes from ``QThread.run()``), and nothing at all for plain
``threading.Thread`` workers. ``cli.py`` and ``svc.py`` installed **none** of it, so
both shipped binaries were entirely silent in the field.

The gap that matters most is `threading.excepthook`: the SSDP and mDNS discovery
threads fixed in v2.2.8 are plain ``threading.Thread``, so an exception escaping one of
them left no record anywhere.
"""
from __future__ import annotations

import pathlib
import sys
import threading

import pytest

_DEVANAGARI = "नमस्ते"


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """Redirect the app-data dir, using a non-Latin path.

    The crash net's whole job is to write a record on the machines that are hardest to
    reach, and a Devanagari username is the case that makes an unencoded write fail
    deterministically (hi-IN Windows uses cp1252 as its ANSI codepage, which cannot
    represent Devanagari at all). Testing on that path by default means the encoding
    contract is exercised by every test here, not only the one that names it.
    """
    home = tmp_path / (_DEVANAGARI + "-home")
    target = home / "NetSentinel"
    target.mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(home))
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)
    return target


@pytest.fixture
def restorable_hooks(monkeypatch):
    """Keep install() from leaking its hooks into the rest of the session."""
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)


def test_an_exception_in_a_plain_thread_is_recorded(appdata, restorable_hooks):
    """The gap nothing covered: a plain threading.Thread, not a QThread."""
    from modules import crash_net

    crash_net.install()

    def _boom():
        raise ValueError("thread-level failure")

    t = threading.Thread(target=_boom)
    t.start()
    t.join(timeout=5)

    log = pathlib.Path(crash_net.exceptions_log_path())
    assert log.exists(), "threading.excepthook wrote no record at all"
    text = log.read_text(encoding="utf-8")
    assert "thread-level failure" in text
    assert "ValueError" in text


def test_a_thread_exiting_via_systemexit_is_not_recorded(appdata, restorable_hooks):
    """SystemExit is how a thread is asked to stop — it is not a failure.

    Several workers stop by raising it. Logging those would bury real tracebacks in
    routine shutdown noise, which is the same "a log nobody trusts" failure mode as a
    gate that cries wolf.
    """
    from modules import crash_net

    crash_net.install()

    t = threading.Thread(target=lambda: (_ for _ in ()).throw(SystemExit))
    t.start()
    t.join(timeout=5)

    log = pathlib.Path(crash_net.exceptions_log_path())
    assert not log.exists() or "SystemExit" not in log.read_text(encoding="utf-8")


def test_the_main_thread_hook_records_and_then_notifies(appdata, restorable_hooks):
    """Order is load-bearing: the record must be on disk before the notifier runs.

    app.py's notifier builds a QMessageBox. If it raised (or the process died inside
    it) after being called first, the traceback it exists to report would be lost.
    """
    from modules import crash_net

    seen: list = []
    crash_net.install(on_unhandled=lambda title, msg: seen.append((title, msg)))

    try:
        raise RuntimeError("main-thread failure")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())

    text = pathlib.Path(crash_net.exceptions_log_path()).read_text(encoding="utf-8")
    assert "main-thread failure" in text
    assert len(seen) == 1
    assert "main-thread failure" in seen[0][1]


def test_a_raising_notifier_cannot_lose_the_record(appdata, restorable_hooks):
    """modules/ cannot import PyQt (ARCH RULE 1), so the notifier is caller-supplied
    and therefore arbitrary code. It must not be able to destroy the evidence."""
    from modules import crash_net

    def _bad_notifier(title, msg):
        raise OSError("dialog subsystem unavailable")

    crash_net.install(on_unhandled=_bad_notifier)

    try:
        raise RuntimeError("failure behind a broken dialog")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())   # must not propagate

    text = pathlib.Path(crash_net.exceptions_log_path()).read_text(encoding="utf-8")
    assert "failure behind a broken dialog" in text


def test_faulthandler_is_enabled_and_points_at_the_crash_log(appdata, restorable_hooks):
    """Native SEH faults reach no Python hook — faulthandler is their only recorder."""
    import faulthandler

    from modules import crash_net

    was_enabled = faulthandler.is_enabled()
    try:
        crash_net.install()
        assert faulthandler.is_enabled()
        assert pathlib.Path(crash_net.crash_log_path()).parent == appdata
    finally:
        if not was_enabled:
            faulthandler.disable()


def test_the_crash_log_is_opened_append_only(appdata, restorable_hooks):
    """RULE-CHAOS2: tools/monkey_test.py detects native faults by baselining this
    file's BYTE SIZE at run start and seeking to that offset. Truncating it makes a
    shrink read as "nothing new" while the stale baseline stays large, so every later
    fault in that run goes unseen — silently disarming the only native-fault detector.
    """
    import faulthandler

    from modules import crash_net

    log = pathlib.Path(crash_net.crash_log_path())
    log.write_text("previous session evidence\n", encoding="utf-8")

    was_enabled = faulthandler.is_enabled()
    try:
        crash_net.install()
        assert "previous session evidence" in log.read_text(encoding="utf-8")
    finally:
        if not was_enabled:
            faulthandler.disable()


def test_a_traceback_the_ansi_codepage_cannot_encode_is_still_written(
    appdata, restorable_hooks, monkeypatch
):
    """The hi-IN case, deterministic rather than probabilistic.

    hi-IN Windows uses cp1252 as its ANSI codepage, which cannot represent Devanagari
    at all — so a Devanagari username in %LOCALAPPDATA% appears in nearly every
    traceback and makes an unencoded write fail every time. The recorder must name its
    own codec (RULE-WIN19/WIN24), or the evidence vanishes on exactly the machines
    that cannot be reached to debug them.
    """
    import builtins

    real_open = builtins.open

    def _ansi_open(file, mode="r", *args, **kwargs):
        if "b" not in str(mode) and "encoding" not in kwargs:
            kwargs["encoding"] = "cp1252"      # what an unnamed codec resolves to there
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _ansi_open)

    from modules import crash_net

    crash_net.record_exception("main", f"path {_DEVANAGARI} and an arrow →\n")

    text = pathlib.Path(crash_net.exceptions_log_path()).read_text(encoding="utf-8")
    assert "path" in text and "and an arrow" in text


# ── Wiring guard ─────────────────────────────────────────────────────────────
# The module above is correct and covered. What actually rotted historically was the
# WIRING: the net was defined at app.py module scope, so cli.py and svc.py -- separate
# PyInstaller entry points that never import app -- silently had none of it. A guard on
# the helper alone is structurally blind to that (RULE-DBG5), so assert the call sites.

_ENTRY_POINTS = ("app.py", "cli.py", "svc.py")
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _calls_crash_net_install(source: str) -> bool:
    import ast

    tree = ast.parse(source)
    aliases = {
        (a.asname or a.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "modules.crash_net"
        for a in node.names
        if a.name == "install"
    }
    if not aliases:
        return False
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in aliases
        for n in ast.walk(tree)
    )


@pytest.mark.parametrize("entry_point", _ENTRY_POINTS)
def test_every_entry_point_installs_the_crash_net(entry_point):
    src = (_REPO_ROOT / entry_point).read_text(encoding="utf-8")
    assert _calls_crash_net_install(src), (
        f"{entry_point} never calls modules.crash_net.install(), so an unhandled "
        f"exception or native fault in this binary leaves no record at all — the exact "
        f"state cli.py and svc.py shipped in."
    )


def test_the_wiring_guard_rejects_an_import_with_no_call():
    assert not _calls_crash_net_install("from modules.crash_net import install\n")


def test_app_passes_a_notifier_so_the_user_still_sees_a_dialog(monkeypatch):
    """cli/svc are headless and pass nothing; app.py must not silently become headless.

    Losing the notifier would turn a visible crash dialog into a silent write-and-carry-on,
    which reads as the app freezing for no reason.
    """
    import ast

    tree = ast.parse((_REPO_ROOT / "app.py").read_text(encoding="utf-8"))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id.endswith("install_crash_net")
    ]
    assert calls, "app.py no longer calls the crash-net installer"
    assert any(k.arg == "on_unhandled" for c in calls for k in c.keywords), (
        "app.py installs the crash net without on_unhandled, so unhandled errors are "
        "recorded but never shown to the user"
    )

"""Bounding the logs that grow forever — with netsentinel_crash.log exempt (A4).

There is no rotation anywhere in shipped code: no `RotatingFileHandler`, no `maxBytes`,
no age pruning. Measured on a real install, the app-data directory held
`netsentinel_crash.log` at 6.78 MB, `netsentinel_theme_switch.log` at 4.08 MB and still
growing that day, plus stderr, shutdown and scan-timing logs around 1 MB each.

**The crash log is deliberately exempt, and that is not an oversight.**
`tools/monkey_test.py::_check_crash_log()` is the only detector for native SEH faults,
and it works by baselining that file's byte size at run start and seeking to the offset.
Its guard is `if size <= self._crash_log_size0: return False`, so a rotation makes the
shrink read as "nothing new" *and* leaves a stale, too-large baseline — every later fault
in that run goes unseen. The chaos harness restarts the app mid-run, so a rotate-on-start
scheme would fire mid-run and silently disarm the project's primary stability gate.

**The size threshold is what keeps the rest safe to rotate.** `netsentinel_exceptions.log`
sits at 58 KB and chaos-run verification reads its mtime; a threshold well above that
means rotation cannot fire during a run, so the behaviour there is byte-identical to
today. Rotation only ever happens to a log that has genuinely grown large, which is the
only case A4 is about.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    target = tmp_path / "NetSentinel"
    target.mkdir()
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: target)
    return target


def _write(path, size: int) -> None:
    path.write_bytes(b"x" * size)


def test_a_log_past_the_threshold_is_rotated_to_one_generation(appdata):
    """The whole point: an oversized log is moved aside, not deleted outright.

    Keeping one generation means the last session's evidence survives the rotation that
    bounds it — a log that is simply truncated at startup would destroy exactly the
    record someone is about to come looking for.
    """
    from modules import log_rotation

    log = appdata / "netsentinel_theme_switch.log"
    _write(log, log_rotation.MAX_LOG_BYTES + 1)

    log_rotation.rotate_logs()

    assert (appdata / "netsentinel_theme_switch.log.1").exists(), "no generation kept"
    assert not log.exists() or log.stat().st_size == 0


def test_the_crash_log_is_never_rotated_however_large_it_gets(appdata):
    """Rotating this file silently disarms the project's only native-fault detector.

    `monkey_test.py::_check_crash_log()` baselines its byte size at run start and seeks
    to that offset, guarded by `if size <= self._crash_log_size0: return False`. Shrink
    the file and every later fault in that run reads as "nothing new" — the harness goes
    on reporting clean runs while native SEH faults land unseen. The real install's copy
    is 6.78 MB, far past any threshold, so this is the case that would fire first.
    """
    from modules import log_rotation

    log = appdata / "netsentinel_crash.log"
    _write(log, log_rotation.MAX_LOG_BYTES * 10)
    size_before = log.stat().st_size

    rotated = log_rotation.rotate_logs()

    assert "netsentinel_crash.log" not in rotated
    assert log.stat().st_size == size_before, (
        "the crash log shrank — monkey_test.py's baseline seek is now past EOF and "
        "every native fault for the rest of the run is undetectable"
    )
    assert not (appdata / "netsentinel_crash.log.1").exists()


def test_a_log_under_the_threshold_is_left_completely_alone(appdata):
    """The threshold is what makes rotation safe to run during a chaos session.

    `netsentinel_exceptions.log` sits around 58 KB and chaos-run verification reads its
    mtime to decide whether a run was clean. Rotation must be structurally unable to
    fire at that size, so a run's mtime evidence means exactly what it meant before.
    """
    from modules import log_rotation

    log = appdata / "netsentinel_exceptions.log"
    _write(log, 58 * 1024)
    mtime_before = log.stat().st_mtime_ns

    assert log_rotation.rotate_logs() == []
    assert log.stat().st_mtime_ns == mtime_before, "an untouched log was touched"
    assert not (appdata / "netsentinel_exceptions.log.1").exists()


def test_rotating_twice_keeps_one_generation_not_a_growing_pile(appdata):
    """One generation, replaced — otherwise this bounds nothing, it just renames.

    A scheme that appended `.1`, `.2`, `.3` would leave the same unbounded total on disk
    under different names, which is the problem restated rather than solved.
    """
    from modules import log_rotation

    log = appdata / "netsentinel_stderr.log"
    _write(log, log_rotation.MAX_LOG_BYTES + 1)
    log_rotation.rotate_logs()
    _write(log, log_rotation.MAX_LOG_BYTES + 1)
    log_rotation.rotate_logs()

    generations = sorted(p.name for p in appdata.glob("netsentinel_stderr.log.*"))
    assert generations == ["netsentinel_stderr.log.1"], generations


def test_a_log_held_open_by_another_process_does_not_abort_the_sweep(appdata):
    """Windows refuses to rename an open file, and that must cost one log, not all of them.

    A second NetSentinel process, or a tail/editor someone left open, is enough to make
    one rename fail. Rotation runs on the startup path, so an exception here would be a
    launch failure caused purely by housekeeping.
    """
    from modules import log_rotation

    locked = appdata / "netsentinel_scan_timing.log"
    other = appdata / "netsentinel_stderr.log"
    _write(locked, log_rotation.MAX_LOG_BYTES + 1)
    _write(other, log_rotation.MAX_LOG_BYTES + 1)

    with open(locked, "a"):                       # held open for the whole sweep
        rotated = log_rotation.rotate_logs()

    assert "netsentinel_stderr.log" in rotated, (
        "one unrotatable log aborted the sweep, so every later log stayed unbounded"
    )

    # The assertion above is the invariant and holds everywhere. The two below are
    # the Windows *mechanism*, and only Windows has it: POSIX `rename(2)` does not
    # care about open descriptors, so on Linux and macOS the held-open log rotates
    # successfully and the writer keeps writing to the now-unlinked inode. Asserting
    # the mechanism unconditionally failed both POSIX runners while proving nothing
    # about the guard.
    if sys.platform == "win32":
        # Confirms the skip branch actually ran: Windows raises PermissionError on
        # os.replace() of an open file, so without the per-file guard this sweep
        # would have thrown rather than merely skipped one entry.
        assert "netsentinel_scan_timing.log" not in rotated
        assert locked.exists(), "the locked log was rotated out from under its writer"
    else:
        assert "netsentinel_scan_timing.log" in rotated, (
            "POSIX renames an open file, so this log should have rotated"
        )


def test_rotation_never_raises_when_app_data_is_unreachable(monkeypatch):
    """Housekeeping must never be the reason an entry point fails to start."""
    from modules import log_rotation

    def _boom():
        raise OSError("the app-data directory is not reachable")

    monkeypatch.setattr("modules.utils.get_app_data_dir", _boom)

    assert log_rotation.rotate_logs() == []


#: Every shipped entry point must bound its own logs. `cli.py` and `svc.py` write the
#: same sinks as `app.py` — svc.py unattended as a Windows service, where nobody is
#: watching the directory grow — and a fix installed at one entry point's module scope
#: protects only that binary (RULE-WIN26's mechanism, one concern over).
ENTRY_POINTS = ("app.py", "cli.py", "svc.py")


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_every_entry_point_bounds_its_logs_before_opening_one(entry_point):
    """Rotation must be called, and called before anything holds a log open.

    Order is not cosmetic on Windows: `os.replace()` raises PermissionError on a file
    another handle has open, so rotating after `_ensure_std_streams()` has bound
    `netsentinel_stderr.log` would skip that log every single time — silently, since the
    sweep is required to swallow exactly that error.
    """
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    tree = ast.parse((root / entry_point).read_text(encoding="utf-8"))

    aliases = {
        alias.asname: alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names if alias.asname
    }

    def _line_of(target: str):
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", None))
            if name is not None and aliases.get(name, name) == target:
                return node.lineno
        return None

    rotate_line = _line_of("rotate_logs")
    assert rotate_line is not None, (
        f"{entry_point} never calls rotate_logs() — its logs grow without limit, and "
        f"the theme-switch log alone reached 4.08 MB on a real install"
    )

    streams_line = _line_of("_ensure_std_streams")
    if streams_line is not None:
        assert rotate_line < streams_line, (
            f"{entry_point} rotates at line {rotate_line}, after _ensure_std_streams() "
            f"at line {streams_line} has already opened netsentinel_stderr.log — "
            f"Windows cannot rename an open file, so that log is skipped forever"
        )

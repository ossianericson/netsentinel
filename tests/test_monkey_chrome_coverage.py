"""
Guards the window-chrome chaos coverage in tools/monkey_test.py.

WHY THIS EXISTS
---------------
A broken maximize button shipped to users: it called showFullScreen(), which
covers the taskbar, instead of showMaximized(). No chaos run could ever have
caught it, because the harness excluded the window chrome twice over:

  1. _BLACKLIST listed the maximize/restore/minimize/close glyphs AND a
     "_chromebutton" auto_id catch-all.
  2. _enabled_controls() spatially skipped EVERY Button in the top 60px of the
     window -- the entire header (chrome, settings gear, Scan button).

The blacklist comments recorded these as a "confirmed crash cause from seed=99",
i.e. the controls were excluded to make the harness pass rather than to fix the
app. That is the anti-pattern this file locks out.

INVARIANT: a control may be blacklisted only for an APP-LIFECYCLE reason (it
kills or hides the app under test). Never because clicking it crashed -- a crash
is the harness doing its job.

These tests are plain-import (no pywinauto UIA session), so they run in the
normal suite rather than under the `monkey` marker.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

CLOSE = ""   # Segoe MDL2 ChromeClose
MINIMIZE = ""   # ChromeMinimize
MAXIMIZE = ""   # ChromeMaximize
RESTORE = ""   # ChromeRestore

CHROME_AUTO_ID = "QApplication.Dashboard.QWidget.appBar._ChromeButton"


@pytest.fixture(scope="module")
def monkey():
    """Import tools/monkey_test.py without running its CLI."""
    spec = importlib.util.spec_from_file_location(
        "monkey_test_mod", REPO / "tools" / "monkey_test.py"
    )
    mod = importlib.util.module_from_spec(spec)
    argv = sys.argv
    sys.argv = ["monkey_test.py"]
    try:
        spec.loader.exec_module(mod)
    except ImportError:
        pytest.skip("pywinauto/psutil not installed (dev-only dependency)")
    except SystemExit:
        pass  # argparse ran; module object is still populated
    finally:
        sys.argv = argv
    return mod


def test_blacklist_has_no_empty_pattern(monkey):
    """An empty pattern matches EVERY control.

    _is_blacklisted() does `any(pat in combined for pat in _BLACKLIST)`, and
    "" is a substring of every string -- one blank entry silently disables the
    entire chaos run while still reporting success.
    """
    blank = [i for i, pat in enumerate(monkey._BLACKLIST) if not pat.strip()]
    assert not blank, (
        f"_BLACKLIST entries {blank} are empty/whitespace. An empty pattern is a "
        f"substring of every control name, so EVERY control would be skipped and "
        f"the run would pass without testing anything."
    )


def test_maximize_and_restore_are_exercised(monkey):
    """The maximize/restore button must be clickable by chaos runs.

    It is benign and reversible. Blacklisting it is what let the showFullScreen()
    bug reach users.
    """
    for glyph, label in ((MAXIMIZE, "maximize"), (RESTORE, "restore")):
        assert not monkey._is_blacklisted(glyph, CHROME_AUTO_ID), (
            f"The {label} button is blacklisted again. It is benign and reversible, "
            f"and excluding it is exactly why a broken maximize button shipped. "
            f"Only app-lifecycle controls (close/minimize) may be blacklisted."
        )


def test_close_and_minimize_stay_blacklisted(monkey):
    """These two are the legitimate exclusions -- for app-lifecycle reasons.

    close    -> terminates the app under test
    minimize -> hides the window, so UIA can no longer see any control
    """
    assert monkey._is_blacklisted(CLOSE, CHROME_AUTO_ID), \
        "close button must stay blacklisted -- it kills the app under test"
    assert monkey._is_blacklisted(MINIMIZE, CHROME_AUTO_ID), \
        "minimize must stay blacklisted -- it hides the window from UIA"


def test_start_minimised_checkbox_stays_blacklisted(monkey):
    """The Settings "Start minimised to the system tray" checkbox is an
    app-lifecycle exclusion — the same class as minimize, only PERSISTENT.

    It writes QSettings startup/start_minimised, and app.py honours that flag on
    EVERY subsequent launch by never showing a window at all (tray-only). One
    chaos click therefore makes every later relaunch in the run — and every future
    run on the machine, since the value lives in the registry — start with no
    window for UIA to find, so _connect() times out and _assert_focus()/
    _focus_heartbeat() have nothing to reclaim. Reads as "the run lost focus".
    """
    label = ("Start minimised to the system tray  "
             "(applies to every launch, not just automatic startup)")
    assert monkey._is_blacklisted(label, "QApplication.Dashboard.QCheckBox"), (
        "the 'Start minimised to the system tray' checkbox is clickable by chaos "
        "runs again. It hides the app from UIA on every FUTURE launch too "
        "(QSettings startup/start_minimised), which is a persistent version of the "
        "minimize exclusion — RULE-CHAOS2 app-lifecycle, not a crash workaround."
    )


def test_both_launch_paths_reset_hazardous_settings(monkey):
    """A machine where start_minimised is already set must self-heal.

    Blacklisting only stops the flag being set from here on. Both launch paths
    must also clear it, or a run on an already-tripped machine (set by a prior
    run, by a real user, or before the blacklist entry existed) starts tray-only
    forever with no window to drive.
    """
    import inspect

    assert hasattr(monkey.MonkeyTester, "_reset_hazardous_settings"), (
        "no _reset_hazardous_settings(): an already-set startup/start_minimised "
        "registry value would make every launch in the run tray-only"
    )
    for meth in ("_launch_exe", "_launch_source"):
        src = inspect.getsource(getattr(monkey.MonkeyTester, meth))
        assert "_reset_hazardous_settings" in src, (
            f"MonkeyTester.{meth}() does not call _reset_hazardous_settings(), so a "
            f"machine with startup/start_minimised already set launches tray-only"
        )


def test_chrome_actions_are_registered_in_every_chaos_pool(monkey):
    """Window-chrome actions must run at every chaos level, not just 'wild'.

    Maximize/restore/snap live in the NON-CLIENT area, which is not a UIA control,
    so clicking controls alone never reaches them.
    """
    for chaos in ("mild", "moderate", "wild"):
        names = [f.__name__ for f in monkey._nav_pool(chaos)]
        assert any(n.startswith("_chrome_") for n in names), (
            f"chaos level {chaos!r} has no window-chrome action: {names}"
        )


def test_snap_layout_flyout_is_exercised_at_wild(monkey):
    """Win+Z (the Snap Layouts flyout) is the interaction that produced the
    0x8001010d COM-reentrancy fault. It must be driven at the highest chaos level."""
    names = [f.__name__ for f in monkey._nav_pool("wild")]
    assert "_chrome_snap_layout_flyout" in names, (
        "the Snap Layouts flyout is the known crash surface and must be exercised"
    )


def test_crash_log_watcher_targets_the_apps_real_crash_log(monkey):
    """faulthandler's netsentinel_crash.log is the ONLY record of a native fault
    (0x8001010d and friends are SEH faults -- no Python except can catch them, and
    they never reach netsentinel_exceptions.log). The harness must watch the same
    file app.py writes, resolved through the app's own get_app_data_dir()."""
    from modules.utils import get_app_data_dir

    path = monkey._crash_log_path()
    assert path is not None, "crash-log watcher could not resolve a path"
    assert path.name == "netsentinel_crash.log"
    assert Path(path).parent == Path(get_app_data_dir()), (
        f"harness watches {path}, but app.py writes to "
        f"{Path(get_app_data_dir()) / 'netsentinel_crash.log'}"
    )


# ── Real-quit phase (Part 3 of the shutdown plan) ────────────────────────────
#
# Every chaos run used to end with self._win.close() -- a native WM_CLOSE, which
# Dashboard.closeEvent() answers by hiding to the tray whenever
# tray/minimize_to_tray is on (it defaults True). The harness then fell through
# to psutil terminate(). So the shutdown path real users take -- titlebar X ->
# _quit_app -> the full worker drain and hard exit -- was NEVER exercised by
# automation in any run. That is exactly how a shutdown crash reached the Store.

def _quit_phase_code(monkey) -> str:
    """Source of _real_quit_phase with its docstring removed.

    The docstring legitimately names the patterns the phase must NOT use (it
    explains why win.close() is the wrong call), so a raw-source substring check
    would flag that prose as a violation.
    """
    import ast
    import inspect
    import textwrap

    fn = ast.parse(
        textwrap.dedent(inspect.getsource(monkey.MonkeyTester._real_quit_phase))
    ).body[0]
    if ast.get_docstring(fn) is not None:
        fn.body = fn.body[1:]
    return ast.unparse(fn)


def test_real_quit_phase_exists_on_the_tester(monkey):
    assert hasattr(monkey.MonkeyTester, "_real_quit_phase"), (
        "no real-quit phase: the harness cannot detect a shutdown crash or hang"
    )


def test_real_quit_phase_does_not_rely_on_win_close(monkey):
    """win.close() posts WM_CLOSE, which the tray branch swallows — it drives the
    minimize path, not the quit path. The phase must click the titlebar X."""
    code = _quit_phase_code(monkey)
    assert ".close()" not in code, (
        "the real-quit phase still uses win.close() (WM_CLOSE), which "
        "minimize-to-tray swallows — it would test the tray path, not the quit path"
    )
    assert "click_input" in code, "the phase must click the real titlebar close button"


def test_real_quit_phase_fails_on_hang_and_on_crash_log_growth(monkey):
    """Both failure modes must be detected. A shutdown that never completes is a
    hang; a native SEH fault during teardown does not kill the process at all, so
    crash-log growth is its only witness (RULE-CHAOS2)."""
    import inspect

    src = inspect.getsource(monkey.MonkeyTester._real_quit_phase)
    assert "_check_crash_log" in src, (
        "the real-quit phase does not check crash-log growth — a native fault "
        "during shutdown would pass silently"
    )
    assert "QUIT_DEADLINE_S" in src, "the real-quit phase has no hang deadline"
    assert hasattr(monkey.MonkeyTester, "QUIT_DEADLINE_S")
    assert 0 < monkey.MonkeyTester.QUIT_DEADLINE_S <= 60, (
        "quit deadline must be a real bound; the drain itself is capped at 3 s"
    )


def test_systematic_tester_also_runs_the_real_quit_phase():
    """tools/systematic_test.py had the identical win.close()/terminate() teardown."""
    src = (REPO / "tools" / "systematic_test.py").read_text(encoding="utf-8")
    assert "_real_quit_phase" in src, (
        "systematic_test.py does not run the real-quit phase, so its 62-page "
        "sweep still never exercises the actual shutdown path"
    )

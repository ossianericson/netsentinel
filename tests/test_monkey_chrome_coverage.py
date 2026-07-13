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

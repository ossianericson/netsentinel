"""
Shared pytest fixtures for NetSentinel test suite.

Keeps a single QApplication instance alive for the entire session so that
Qt-based tests (overview_page, settings_and_onboarding, themes, etc.) do not
segfault when the app is garbage-collected between test modules.

Also processes pending Qt events after each test to flush deleteLater() queues
and prevent C++ object use-after-free segfaults caused by accumulated widgets.

AppData redirect (import-time, before any test runs):
  Production code calls get_app_data_dir() which resolves to
  %LOCALAPPDATA%/NetSentinel/ on Windows and ~/Library/... on macOS.
  Without redirection, test runs silently create files in the real user
  profile.  We point LOCALAPPDATA (Windows) and HOME (POSIX) at a
  per-session tmp directory so all file writes are hermetic.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path
import pytest

# --- Hermetic AppData / home directory (runs at import time) ---

_TMP_APPDATA = Path(tempfile.mkdtemp(prefix="netsentinel-test-"))

if os.name == "nt":
    os.environ.setdefault("LOCALAPPDATA", str(_TMP_APPDATA))
    os.environ.setdefault("APPDATA", str(_TMP_APPDATA))
    os.environ.setdefault("USERPROFILE", str(_TMP_APPDATA))
    os.environ.setdefault("HOMEDRIVE", _TMP_APPDATA.drive)
    os.environ.setdefault("HOMEPATH", str(_TMP_APPDATA)[len(_TMP_APPDATA.drive):])
else:
    os.environ.setdefault("HOME", str(_TMP_APPDATA))
    os.environ.setdefault("XDG_CONFIG_HOME", str(_TMP_APPDATA))

# Patch Path.home() so any code that calls it directly gets the hermetic dir.
def _hermetic_home(_cls=Path) -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    return Path(home) if home else _TMP_APPDATA

Path.home = classmethod(_hermetic_home)  # type: ignore[method-assign]

# Patch Path.expanduser() so ~/... paths never raise RuntimeError on CI.
_ORIGINAL_EXPANDUSER = Path.expanduser

def _hermetic_expanduser(self: Path) -> Path:
    try:
        return _ORIGINAL_EXPANDUSER(self)
    except RuntimeError:
        parts = self.parts
        if not parts or not parts[0].startswith("~"):
            return self
        remainder = parts[1:]
        return _TMP_APPDATA.joinpath(*remainder) if remainder else _TMP_APPDATA

Path.expanduser = _hermetic_expanduser  # type: ignore[method-assign]

# --- Hermetic QSettings (runs at import time, before any test runs) ---
#   The LOCALAPPDATA/HOME redirect above only covers *file* writes. On Windows
#   QSettings defaults to NativeFormat, i.e. the REGISTRY
#   (HKCU\Software\NetSentinel\NetSentinel), which that redirect cannot reach.
#
#   Production code constructs QSettings("NetSentinel", "NetSentinel") directly,
#   and ui/styles.py::apply_theme() ends by calling set_active_theme_name(),
#   which persists "ui/theme". tests/test_charts_theme_switch.py and
#   tests/test_badge_medallion.py drive the REAL apply_theme("Arctic Clean"),
#   so a full suite run rewrote the developer's own saved theme (verified live:
#   Midnight Pro before a run, Arctic Clean after). Those tests restore the
#   previous value only if the file runs to completion — any mid-file failure
#   left the developer stuck on the wrong theme. The same hole let
#   test_lab_mode_page.py / test_protocol_viz_page.py write real QSettings flags.
#
#   Qt offers no way to redirect this on Windows: QSettings(organization,
#   application) hard-selects NativeFormat and ignores setDefaultFormat(), and
#   setPath() has no effect for NativeFormat on Windows (both verified
#   experimentally, 2026-07-22). So the store cannot be sandboxed — instead the
#   _preserve_real_theme fixture below snapshots and restores the one key the
#   suite is known to clobber.
#   Guarded by tests/test_qsettings_isolation.py.


@pytest.fixture(scope="session", autouse=True)
def _preserve_real_theme():
    """Restore the developer's real `ui/theme` after the suite finishes.

    `ui/styles.py::apply_theme()` calls `set_active_theme_name()`, which writes
    "ui/theme" to the real QSettings store (the Windows registry — see the
    import-time note above for why it cannot be sandboxed).
    `tests/test_charts_theme_switch.py` and `tests/test_badge_medallion.py`
    drive the REAL `apply_theme("Arctic Clean")`, so before this fixture a full
    suite run left the developer on Arctic Clean (verified live: Midnight Pro
    before a run, Arctic Clean after).

    Those tests do restore the prior value themselves, but only when the file
    runs to completion — a mid-file failure skipped it. This session finalizer
    runs even when tests fail, so the value survives a red suite.
    """
    try:
        from PyQt6.QtCore import QSettings
    except ImportError:
        yield
        return

    original = QSettings("NetSentinel", "NetSentinel").value("ui/theme")
    try:
        yield
    finally:
        qs = QSettings("NetSentinel", "NetSentinel")
        if original is None:
            qs.remove("ui/theme")      # key did not exist before the run
        else:
            qs.setValue("ui/theme", original)
        qs.sync()


@pytest.fixture(scope="session", autouse=True)
def _preserve_real_window_settings():
    """Restore the developer's real NetSentinel.ini after the suite finishes.

    Unlike the registry-backed theme setting above, ui.app_settings.settings_path()
    resolves to a real FILE at the repo root (not frozen -> exe_dir = repo root),
    so it CAN be sandboxed by snapshotting its bytes -- no registry redirect
    limitation applies here.

    Why this matters: tests/_lazy_pages_child.py, tests/_startup_minimised_child.py
    and tests/_theme_switch_deferred_child.py each run subprocess children that
    construct a real, never-shown, offscreen Dashboard and call dash.close(),
    whose closeEvent() unconditionally calls save_settings() -- on the real
    on-disk NetSentinel.ini if not redirected. That silently overwrote the
    developer's actual saved window geometry with the degenerate rect a
    never-shown widget reports (small, often off-screen-ish coordinates) on
    every test-suite run -- confirmed live via an MD5 hash of the file before
    and after. Those three files now redirect ui.app_settings.settings_path to
    an isolated temp file themselves; this fixture is the session-level
    backstop for any test (present or future) that does not.
    """
    from ui.app_settings import settings_path

    path = settings_path()
    original = path.read_bytes() if path.exists() else None
    try:
        yield
    finally:
        if original is None:
            path.unlink(missing_ok=True)   # file did not exist before the run
        else:
            path.write_bytes(original)


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Session-scoped QApplication — created once, lives until all tests finish."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        yield None
        return

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv + ["-platform", "offscreen"])
    yield app
    # Do NOT call app.quit() or del app here — let Python GC handle it after
    # pytest has finished so no test module is left with a dangling reference.


@pytest.fixture(scope="session", autouse=True)
def _crash_logger(tmp_path_factory):
    """Write each test name to a file before it runs.

    After a process-level crash (STATUS_STACK_BUFFER_OVERRUN) the last line
    in crash_last_test.txt is the test that triggered the crash.
    """
    log_path = Path(tempfile.gettempdir()) / "ns_test_crash_log.txt"
    log_path.write_text("", encoding="utf-8")
    return log_path


@pytest.fixture(autouse=True)
def _log_test_name(request, _crash_logger):
    """Append the current test node-id to the crash log before it runs."""
    with open(_crash_logger, "a", encoding="utf-8") as f:
        f.write(request.node.nodeid + "\n")
    yield


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Give each test its own QSettings namespace so registry state cannot
    leak between tests.  Without this, a test that writes to QSettings can
    change the behaviour of a completely unrelated test that reads the same key.
    """
    try:
        from PyQt6.QtCore import QCoreApplication
    except ImportError:
        yield
        return

    key = str(uuid.uuid4())[:8]
    original_org = QCoreApplication.organizationName()
    original_app = QCoreApplication.applicationName()
    QCoreApplication.setOrganizationName(f"NetSentinel-test-{key}")
    QCoreApplication.setApplicationName("test")
    yield
    QCoreApplication.setOrganizationName(original_org)
    QCoreApplication.setApplicationName(original_app)


@pytest.fixture(autouse=True)
def _flush_qt_events(qt_app):
    """
    After every test: close any orphaned top-level widgets created during the
    test (timers keep them alive otherwise), then drain the deleteLater queue.
    Without this, OverviewPage / other QWidget-heavy tests accumulate Qt
    objects across tests and trigger a C-level segfault.
    """
    yield
    if qt_app is None:
        return
    for w in list(qt_app.topLevelWidgets()):
        try:
            w.close()
            w.deleteLater()
        except Exception:
            pass  # non-fatal
    # processEvents() alone does NOT process DeferredDelete events in Qt6; we
    # must call sendPostedEvents(DeferredDelete) explicitly to drain the queue.
    try:
        from PyQt6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    except Exception:
        pass  # non-fatal — best-effort cleanup
    for _ in range(3):
        qt_app.processEvents()


@pytest.fixture
def fake_windows(monkeypatch):
    """Make a POSIX host take the Windows branch of a platform-switched module.

    Many ``modules/`` functions branch on ``platform.system()`` and, inside the Windows
    branch, reference Windows-only ``subprocess`` constants. Those constants **do not
    exist** on Linux or macOS, so a test that fakes ``platform.system() == "Windows"``
    without supplying them makes the branch raise ``AttributeError: module 'subprocess'
    has no attribute 'CREATE_NO_WINDOW'`` — a failure in the *test's* fiction, not in the
    shipped code, which never reaches that line on a real POSIX box.

    This broke the v2.2.8 release CI: ``test_locale_independent_parsing.py`` passed on the
    Windows runner and failed on both POSIX runners, so no macOS or Linux artifact was
    produced. Worth having as a shared fixture rather than a per-test stub, because the
    locale-parsing tests are precisely the ones that must fake Windows to be meaningful,
    and there are ~15 modules carrying the same constant.
    """
    import platform as _platform
    import subprocess as _subprocess

    monkeypatch.setattr(_platform, "system", lambda: "Windows")

    for _name, _value in (
        ("CREATE_NO_WINDOW", 0x08000000),
        ("STARTF_USESHOWWINDOW", 0x00000001),
        ("SW_HIDE", 0),
        ("DETACHED_PROCESS", 0x00000008),
        ("CREATE_NEW_PROCESS_GROUP", 0x00000200),
    ):
        if not hasattr(_subprocess, _name):
            monkeypatch.setattr(_subprocess, _name, _value, raising=False)

    if not hasattr(_subprocess, "STARTUPINFO"):
        class _StartupInfo:
            dwFlags = 0
            wShowWindow = 0

        monkeypatch.setattr(_subprocess, "STARTUPINFO", _StartupInfo, raising=False)

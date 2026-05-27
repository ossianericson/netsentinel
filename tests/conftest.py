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
            pass
    # Three passes ensures deleteLater() chains are fully resolved.
    for _ in range(3):
        qt_app.processEvents()

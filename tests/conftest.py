"""
Shared pytest fixtures for NetSentinel test suite.

Keeps a single QApplication instance alive for the entire session so that
Qt-based tests (overview_page, settings_and_onboarding, themes, etc.) do not
segfault when the app is garbage-collected between test modules.

Also processes pending Qt events after each test to flush deleteLater() queues
and prevent C++ object use-after-free segfaults caused by accumulated widgets.
"""
import sys
import pytest


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

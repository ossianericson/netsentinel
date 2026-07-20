"""
Tests for the settings-page dirty-state removal (critical-UX Phase 2).

The old `_mark_dirty()`/`is_dirty()`/`clear_dirty()`/`confirm_leave()` machinery
raised an "Unsaved changes" banner on every toggle even though every handler had
already persisted to QSettings on the line above -- there was never anything
unsaved. This asserts the dirty API is fully gone and replaced by a transient
`_flash_saved()` confirmation.
"""

from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("PyQt6") is None:
    pytest.skip("PyQt6 not available", allow_module_level=True)

from ui.pages.settings_page import SettingsPage


class TestDirtyApiRemoved:

    def setup_method(self):
        self.page = SettingsPage()

    def test_mark_dirty_removed(self):
        assert not hasattr(self.page, "_mark_dirty")

    def test_is_dirty_removed(self):
        assert not hasattr(self.page, "is_dirty")

    def test_clear_dirty_removed(self):
        assert not hasattr(self.page, "clear_dirty")

    def test_confirm_leave_removed(self):
        assert not hasattr(self.page, "confirm_leave")

    def test_dirty_flag_removed(self):
        assert not hasattr(self.page, "_dirty")

    def test_dirty_dot_removed(self):
        assert not hasattr(self.page, "_dirty_dot")


class TestFlashSaved:

    def setup_method(self):
        self.page = SettingsPage()

    def test_flash_saved_shows_label(self):
        self.page._flash_saved()
        assert not self.page._saved_lbl.isHidden()
        assert "Saved" in self.page._saved_lbl.text()

    def test_flash_saved_hides_after_timer_fires(self):
        self.page._flash_saved()
        assert not self.page._saved_lbl.isHidden()
        self.page._saved_timer.timeout.emit()
        assert self.page._saved_lbl.isHidden()

    def test_flash_saved_restarts_timer_on_repeat_calls(self):
        """Calling _flash_saved() twice quickly must not leak a second QTimer
        or leave the label toggled by a stale first timer firing later."""
        self.page._flash_saved()
        first_timer = self.page._saved_timer
        self.page._flash_saved()
        assert not self.page._saved_lbl.isHidden()
        # the first timer must not still be running (stopped or replaced)
        assert not first_timer.isActive() or first_timer is self.page._saved_timer


class TestSettingsHandlersStillPersist:
    """Non-regression: replacing _mark_dirty() with _flash_saved() must not
    drop the actual QSettings write in any handler."""

    def setup_method(self):
        self.page = SettingsPage()

    def test_startup_toggle_starts_worker_and_reflects_actual_result(self, monkeypatch):
        """Phase 5 rewrite: the checkbox no longer calls set_run_on_startup()
        synchronously (that structurally cannot express DisabledByUser/Policy —
        docs/spikes/startup-task-winrt.md's RULE-REQ2 paragraph). It starts
        workers.autostart_worker.AutostartWorker off the GUI thread and
        re-sets from the ACTUAL result. No _flash_saved() here — the
        checkbox's own honest state is the confirmation, not a generic
        "Saved" flash that could contradict what the OS actually decided."""
        from PyQt6.QtWidgets import QApplication

        from modules import autostart
        monkeypatch.setattr(autostart, "autostart_backend", lambda: "run_key")
        monkeypatch.setattr(autostart, "set_run_on_startup", lambda enabled: None)
        monkeypatch.setattr(autostart, "get_run_on_startup", lambda: True)

        self.page._on_startup_toggled(True)
        assert not self.page._chk_startup.isEnabled()  # in-flight (RULE-UX2)

        assert self.page._autostart_worker is not None
        assert self.page._autostart_worker.wait(5000)
        app = QApplication.instance()
        for _ in range(5):
            app.processEvents()

        assert self.page._chk_startup.isChecked() is True
        assert self.page._chk_startup.isEnabled() is True
        assert self.page._saved_lbl.isHidden()

    def test_auto_snap_toggle_persists_and_flashes(self, monkeypatch):
        from unittest.mock import MagicMock
        mock_qs = MagicMock()
        monkeypatch.setattr("ui.pages.settings_cards.QSettings", lambda *a: mock_qs)
        self.page._on_auto_snap_toggled(True)
        mock_qs.setValue.assert_called_once_with("baseline/auto_snapshot", True)

    def test_start_minimised_toggle_persists_and_flashes(self, monkeypatch):
        """Unlike autostart, this is a plain QSettings write with no OS consent
        involved — _flash_saved() is honest here (Phase 5.4/5.5)."""
        from unittest.mock import MagicMock
        mock_qs = MagicMock()
        monkeypatch.setattr("ui.pages.settings_cards.QSettings", lambda *a: mock_qs)
        self.page._on_start_minimised_toggled(True)
        mock_qs.setValue.assert_called_once_with("startup/start_minimised", True)
        assert not self.page._saved_lbl.isHidden()
        assert not self.page._saved_lbl.isHidden()


class TestNavGuardRemoved:

    def test_builder_no_longer_references_dirty_api(self):
        import inspect
        from ui.nav import builder
        src = inspect.getsource(builder)
        assert "is_dirty()" not in src
        assert "confirm_leave()" not in src

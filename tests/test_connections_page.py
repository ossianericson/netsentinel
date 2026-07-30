"""Behavioral test (RULE-T7) — ConnectionsPage firewall control plumbing.

Bug: _block_process()/_unblock_process()/_get_blocked_rules() ran
subprocess.run(..., timeout=10-15) synchronously on the GUI thread,
including during __init__ (before the window is even shown), freezing
the whole app for up to the timeout window (RULE 4 violation).

Fix: the netsh calls now run on a FirewallWorker QThread
(workers/firewall_worker.py); ConnectionsPage only starts the worker
(_run_fw_worker) and updates its label/KPI state from the result_ready
signal (_on_list_result / _on_block_result / _on_unblock_result).

Exercises the real ConnectionsPage methods against a lightweight MagicMock
double (RULE-T7 explicitly allows "a mock of the dashboard" for pages whose
full widget tree is expensive to construct), following the pattern in
tests/test_dashboard_scan_watchdog.py. Each method under test is called as
an unbound call (ConnectionsPage.<method>(fake, ...)) so `self.<other
method>` calls resolve against the fake's mocked attributes -- delegation
is asserted directly rather than relying on the fake to run real code, with
one end-to-end test at the bottom wiring the fake's _run_fw_worker to the
real implementation to prove the full chain doesn't block.
"""
import functools
from unittest.mock import MagicMock

import pytest

try:
    from ui.pages.connections_page import ConnectionsPage
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _FakeSignal:
    """Minimal stand-in for a pyqtSignal(dict): connect() + manual emit()."""

    def __init__(self):
        self._cb = None

    def connect(self, cb):
        self._cb = cb

    def emit(self, *args):
        assert self._cb is not None, "nothing connected to this signal"
        self._cb(*args)


class _FakeFirewallWorker:
    """Stand-in for workers.firewall_worker.FirewallWorker.

    Captures constructor args and never actually runs a subprocess or a
    real QThread -- start() just flips a flag so tests can assert the
    call returned without blocking.
    """

    instances: list = []

    def __init__(self, op, exe_path="", exe_name="", parent=None):
        self.op = op
        self.exe_path = exe_path
        self.exe_name = exe_name
        self.result_ready = _FakeSignal()
        self.started = False
        _FakeFirewallWorker.instances.append(self)

    def isRunning(self):
        return False

    def start(self):
        self.started = True


@pytest.fixture(autouse=True)
def _reset_fake_instances():
    _FakeFirewallWorker.instances.clear()
    yield
    _FakeFirewallWorker.instances.clear()


# ── Tier 1: call-site methods delegate to _run_fw_worker ────────────────────

def test_load_blocked_rules_delegates_to_worker():
    fake = MagicMock()
    ConnectionsPage._load_blocked_rules(fake)
    fake._run_fw_worker.assert_called_once_with("list", fake._on_list_result)


def test_toggle_block_unblock_path_delegates_to_worker():
    fake = MagicMock()
    conn = MagicMock(exe_name="foo.exe", exe_path="C:\\foo.exe")

    ConnectionsPage._toggle_block(fake, conn, currently_blocked=True)

    fake._run_fw_worker.assert_called_once()
    args, kwargs = fake._run_fw_worker.call_args
    assert args[0] == "unblock"
    assert kwargs.get("exe_name") == "foo.exe"


def test_do_undo_block_captures_exe_before_hide_then_delegates():
    fake = MagicMock()
    fake._undo_exe = "foo.exe"

    ConnectionsPage._do_undo_block(fake)

    fake._hide_undo_bar.assert_called_once()
    fake._run_fw_worker.assert_called_once()
    args, kwargs = fake._run_fw_worker.call_args
    assert args[0] == "unblock"
    assert kwargs.get("exe_name") == "foo.exe"


def test_do_undo_block_noop_when_no_pending_undo():
    fake = MagicMock()
    fake._undo_exe = ""

    ConnectionsPage._do_undo_block(fake)

    fake._run_fw_worker.assert_not_called()


# ── Tier 2: _run_fw_worker itself starts a worker and does not block ────────

def test_run_fw_worker_starts_thread_without_blocking(monkeypatch):
    monkeypatch.setattr("workers.firewall_worker.FirewallWorker", _FakeFirewallWorker)
    fake = MagicMock()
    fake._fw_worker = None
    on_done = MagicMock()

    ConnectionsPage._run_fw_worker(fake, "list", on_done)

    assert len(_FakeFirewallWorker.instances) == 1
    w = _FakeFirewallWorker.instances[0]
    assert w.op == "list"
    assert w.started is True, "_run_fw_worker must call worker.start()"
    on_done.assert_not_called(), "the result callback must not fire synchronously"

    w.result_ready.emit({"op": "list", "rules": ["chrome.exe"]})
    on_done.assert_called_once_with({"op": "list", "rules": ["chrome.exe"]})


def test_run_fw_worker_reentrancy_guard(monkeypatch):
    """A second call while an op is already running must not start a
    second worker (same isRunning() guard pattern used throughout the app,
    e.g. ui/tabs_scan.py)."""
    monkeypatch.setattr("workers.firewall_worker.FirewallWorker", _FakeFirewallWorker)
    fake = MagicMock()
    running = MagicMock()
    running.isRunning.return_value = True
    fake._fw_worker = running

    ConnectionsPage._run_fw_worker(fake, "list", MagicMock())

    assert len(_FakeFirewallWorker.instances) == 0


# ── Tier 3: result handlers update the correct widget state ─────────────────

def test_on_list_result_updates_kpi_and_label():
    fake = MagicMock()
    ConnectionsPage._on_list_result(fake, {"op": "list", "rules": ["chrome.exe", "steam.exe"]})
    fake._lbl_blocked.set_value.assert_called_once_with(2)
    fake._apply_filters.assert_called_once()


def test_on_list_result_empty_shows_no_active_blocks():
    fake = MagicMock()
    ConnectionsPage._on_list_result(fake, {"op": "list", "rules": []})
    fake._blocked_lbl.setText.assert_called_once_with("No active blocks")
    fake._lbl_blocked.set_value.assert_called_once_with(0)


def test_on_unblock_result_prefixes_undo_message():
    fake = MagicMock()
    ConnectionsPage._on_unblock_result(
        fake, {"ok": False, "message": "Rule not found"}, prefix="Undo: "
    )
    fake._status_lbl.setText.assert_called_once_with("⚠  Undo: Rule not found")
    fake._load_blocked_rules.assert_called_once()


def test_on_unblock_result_no_prefix_for_plain_toggle():
    fake = MagicMock()
    ConnectionsPage._on_unblock_result(fake, {"ok": True, "message": "Unblocked: foo.exe"})
    fake._status_lbl.setText.assert_called_once_with("✓  Unblocked: foo.exe")


def test_on_block_result_success_shows_undo_bar():
    fake = MagicMock()
    fake._pending_block_exe = "foo.exe"
    ConnectionsPage._on_block_result(fake, {"ok": True, "message": "Blocked: foo.exe"})
    assert fake._undo_exe == "foo.exe"
    fake._undo_bar.setVisible.assert_called_once_with(True)
    fake._undo_timer.start.assert_called_once_with(10_000)


def test_on_block_result_failure_shows_status_not_undo_bar():
    fake = MagicMock()
    ConnectionsPage._on_block_result(fake, {"ok": False, "message": "Access denied."})
    fake._status_lbl.setText.assert_called_once_with("⚠  Access denied.")
    fake._undo_bar.setVisible.assert_not_called()


# ── End-to-end: full chain from _load_blocked_rules to the result handler ───

def test_block_confirmation_dialog_shows_ok_button(monkeypatch):
    """Regression: the QDialogButtonBox (Ok='Block Process'/Cancel) is built
    and wired (btns.accepted/rejected connected) but was never added to the
    dialog's layout -- missing lay.addWidget(btns) -- so the confirmation
    dialog rendered with no visible buttons and the user could not proceed
    or cancel."""
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QWidget

    captured = {}

    def _fake_exec(self):
        captured["dialog"] = self
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", _fake_exec)

    page_stub = QWidget()
    conn = MagicMock(exe_name="foo.exe", exe_path="C:\\foo.exe")
    try:
        ConnectionsPage._toggle_block(page_stub, conn, currently_blocked=False)

        dlg = captured.get("dialog")
        assert dlg is not None, "dialog was never constructed/exec'd"
        btn_box = dlg.findChild(QDialogButtonBox)
        assert btn_box is not None, (
            "QDialogButtonBox was never added to the dialog's layout "
            "(missing lay.addWidget(btns)) -- no OK/Cancel buttons visible"
        )
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_btn is not None
        assert ok_btn.text() == "Block Process"
    finally:
        page_stub.deleteLater()
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


def test_auto_refresh_checkbox_defaults_checked_and_starts_timer_on_show():
    """Regression (F-84 claims-audit): ui/help.py's Active Connections entry says
    'The list refreshes every few seconds automatically', but QCheckBox("Auto (5s)")
    was constructed with no setChecked(True) -- it defaulted unchecked, so nothing
    auto-refreshed unless the user found and ticked the box themselves. Checking
    the box must actually start _auto_timer, not just look checked.

    Amended 2026-07-30 (RULE-WIN18): the timer must NOT start at construction --
    this page is lazily built at startup whether or not the user ever opens it,
    and a 5 s psutil enumeration + full table rebuild running forever on an
    unopened page was the confirmed root cause of ~556 MB/hr idle RSS growth
    (docs/spikes/idle-rss-leak-lazy-page-timers.md). F-84's real intent -- "the
    box is ticked AND it genuinely drives the timer" -- is preserved by asserting
    the timer runs once the page is actually visible.

    Uses a subclass rather than monkeypatch.setattr(ConnectionsPage, "_refresh",
    ...): _refresh is decorated @pyqtSlot(), and replacing it on the CLASS breaks
    PyQt's slot resolution permanently -- after monkeypatch restores it, every
    later ConnectionsPage() in the same pytest process dies with
    "TypeError: connect() failed between timeout() and _refresh()". That made this
    file a latent landmine for any future test that constructs the page.
    """
    from PyQt6.QtWidgets import QApplication

    class _QuietPage(ConnectionsPage):
        """No psutil worker / no firewall query -- overrides on the SUBCLASS, so
        ConnectionsPage itself is never mutated."""

        def _refresh(self):
            pass  # test double — the real one spawns a ConnectionSnapshotWorker

        def _load_blocked_rules(self):
            pass  # test double — the real one shells out to the firewall

    page = _QuietPage()
    try:
        assert page._chk_auto.isChecked() is True, "box must be ticked by default"
        assert page._auto_timer.isActive() is False, (
            "timer must not run before the page has ever been shown (RULE-WIN18)"
        )

        page.show()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
        assert page._auto_timer.isActive() is True, (
            "a ticked box must genuinely drive _auto_timer once visible (F-84)"
        )
    finally:
        page._auto_timer.stop()
        page.close()
        page.deleteLater()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()


def test_load_blocked_rules_end_to_end_does_not_block(monkeypatch):
    """Wires the fake's _run_fw_worker/_on_list_result to the real bound
    methods so the full _load_blocked_rules -> FirewallWorker ->
    result_ready -> _on_list_result chain runs, proving the KPI/label
    update happens only after the (fake, non-blocking) worker reports back."""
    monkeypatch.setattr("workers.firewall_worker.FirewallWorker", _FakeFirewallWorker)
    fake = MagicMock()
    fake._fw_worker = None
    fake._run_fw_worker = functools.partial(ConnectionsPage._run_fw_worker, fake)
    fake._on_list_result = functools.partial(ConnectionsPage._on_list_result, fake)

    ConnectionsPage._load_blocked_rules(fake)

    assert len(_FakeFirewallWorker.instances) == 1
    fake._lbl_blocked.set_value.assert_not_called()

    w = _FakeFirewallWorker.instances[0]
    w.result_ready.emit({"op": "list", "rules": ["chrome.exe"]})

    fake._lbl_blocked.set_value.assert_called_once_with(1)

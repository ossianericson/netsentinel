"""Behavioural tests -- Dashboard._maybe_confirm_scan_environment() pre-scan notice.

Exercises the real Dashboard method against a lightweight double instead of
constructing the full widget tree (RULE-T7 / RULE-TP4-DASH), mirroring the
pattern in tests/test_dashboard_scan_reentrancy.py.

MagicMock() gotcha: getattr(magicmock, "_net_env", None) never falls back to
None -- MagicMock auto-vivifies any accessed attribute -- so the method under
test must (and does) check isinstance(env, NetworkEnvironment) rather than
`is None`. The "no env yet" test below locks that in.
"""
from unittest.mock import MagicMock

import pytest

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget
    from ui.dashboard import Dashboard
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")

from modules.network_environment import NetworkEnvironment

_FP = "vpn:GlobalProtect:"


def _fresh():
    QSettings("NetSentinel", "NetSentinel").remove(f"scan/env_ack/{_FP}")


def _vpn_env() -> NetworkEnvironment:
    return NetworkEnvironment(
        kind="vpn", confidence="high", title="VPN detected: GlobalProtect",
        reasons=["Active VPN adapter detected: GlobalProtect"],
        effects=["Device names may be missing."],
        vpn_adapter="GlobalProtect", domain="", prefix_len=16, subnet_hosts=65534,
    )


def _fake_widget(env) -> QWidget:
    QApplication.instance()
    w = QWidget()
    w._net_env = env
    return w


def _cleanup(w: QWidget) -> None:
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed -- safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


class TestMaybeConfirmScanEnvironment:
    def setup_method(self):    _fresh()
    def teardown_method(self): _fresh()

    def test_home_network_never_shows_dialog(self, monkeypatch):
        fake = MagicMock()
        fake._net_env = NetworkEnvironment(kind="home")
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not show dialog on a home network")),
        )
        assert Dashboard._maybe_confirm_scan_environment(fake) is True

    def test_no_environment_detected_yet_never_shows_dialog(self, monkeypatch):
        """Before the first NetworkInfoWorker result, self._net_env doesn't exist on a
        real Dashboard -- on this MagicMock double it auto-vivifies to a bare Mock, which
        must still be treated as "nothing detected yet", not accidentally satisfy .kind."""
        fake = MagicMock()
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not show dialog with no real env")),
        )
        assert Dashboard._maybe_confirm_scan_environment(fake) is True

    def test_already_acknowledged_fingerprint_skips_dialog(self, monkeypatch):
        QSettings("NetSentinel", "NetSentinel").setValue(f"scan/env_ack/{_FP}", True)
        fake = MagicMock()
        fake._net_env = _vpn_env()
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not re-show an acknowledged notice")),
        )
        assert Dashboard._maybe_confirm_scan_environment(fake) is True

    def test_scan_anyway_returns_true_and_persists_ack(self, monkeypatch):
        w = _fake_widget(_vpn_env())
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "Scan Anyway"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        result = Dashboard._maybe_confirm_scan_environment(w)

        assert result is True
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value(f"scan/env_ack/{_FP}", False, type=bool) is True
        _cleanup(w)

    def test_cancel_returns_false_and_does_not_persist_ack(self, monkeypatch):
        w = _fake_widget(_vpn_env())
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "Cancel"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        result = Dashboard._maybe_confirm_scan_environment(w)

        assert result is False
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value(f"scan/env_ack/{_FP}", False, type=bool) is False
        _cleanup(w)

    def test_start_full_scan_aborts_when_notice_cancelled(self, monkeypatch):
        """_start_full_scan must bail out before touching any scan state if the
        pre-scan notice is cancelled -- same guard shape as the re-entrancy check."""
        fake = MagicMock()
        fake._is_scanning = False
        fake._maybe_confirm_scan_environment.return_value = False

        Dashboard._start_full_scan(fake)

        fake._set_scanning.assert_not_called()
        fake._verdict.update.assert_not_called()
        fake._graph.reset.assert_not_called()
        fake._scan_watchdog.start.assert_not_called()

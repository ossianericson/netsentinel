"""Behavioural tests -- L6 active-probe authorization gating in ui/tabs_recon.py.

Exercises the real Dashboard/_ReconTabsMixin methods against a lightweight
MagicMock double instead of constructing the full widget tree (RULE-T7 /
RULE-TP4-DASH), mirroring the pattern in tests/test_scan_environment_notice.py.

Covers:
  - _ensure_active_probe_authorization(): home never prompts; non-home prompts
    once per fingerprint and persists the answer; a different fingerprint is
    asked separately.
  - _confirm_credential_test_on_managed_network(): never persisted, re-shown
    every call.
  - _start_syn_scan(): exclusion list refuses to start; unauthorized network
    caps the rate (soft gate); authorized+home leaves the rate untouched.
  - _start_cred_scan(): exclusion list refuses to start; unauthorized network
    refuses entirely (hard gate); authorized+managed network requires the
    extra un-persisted confirmation.
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
from ui.tabs_recon import _ReconTabsMixin

_FP_KEY_PREFIX = "scan/net_auth/"


def _env(kind: str, gateway="10.10.0.1"):
    return NetworkEnvironment(kind=kind, scope_cidr="10.10.0.0/16" if kind != "home" else "192.168.1.0/24")


def _net_info(gateway="10.10.0.1"):
    return {
        "local_ips": [{"ip": "10.10.5.23", "mask": "255.255.0.0", "adapter": "GlobalProtect"}],
        "gateway": gateway,
        "dns_servers": [], "domain": "",
    }


class _ProbeWidget(_ReconTabsMixin, QWidget):
    """Real QWidget with _ReconTabsMixin methods properly bound -- needed
    because _ensure_active_probe_authorization() calls self._active_probe_fingerprint()
    and constructs QMessageBox(self), neither of which works against a bare
    MagicMock or a plain QWidget with no mixin."""


def _fake_widget(net_env, net_info=None) -> QWidget:
    QApplication.instance()
    w = _ProbeWidget()
    w._net_env = net_env
    w._net_info = net_info or _net_info()
    return w


def _cleanup(w) -> None:
    app = QApplication.instance()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already destroyed -- safe to skip
    if app:
        for _ in range(3):
            app.processEvents()


def _clear_auth(fp: str):
    QSettings("NetSentinel", "NetSentinel").remove(f"{_FP_KEY_PREFIX}{fp}")


class TestEnsureActiveProbeAuthorization:
    def test_home_network_never_shows_dialog_and_returns_true(self, monkeypatch):
        fake = MagicMock()
        fake._net_env = NetworkEnvironment(kind="home")
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not show dialog on a home network")),
        )
        assert Dashboard._ensure_active_probe_authorization(fake) is True

    def test_non_home_never_asked_shows_dialog_yes_persists_true(self, monkeypatch):
        w = _fake_widget(_env("vpn"))
        fp = Dashboard._active_probe_fingerprint(w)
        _clear_auth(fp)
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "Yes, I'm authorized"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        result = Dashboard._ensure_active_probe_authorization(w)

        assert result is True
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value(f"{_FP_KEY_PREFIX}{fp}", None, type=bool) is True
        _clear_auth(fp)
        _cleanup(w)

    def test_non_home_never_asked_shows_dialog_no_persists_false(self, monkeypatch):
        w = _fake_widget(_env("corporate"))
        fp = Dashboard._active_probe_fingerprint(w)
        _clear_auth(fp)
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "No / Not sure"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        result = Dashboard._ensure_active_probe_authorization(w)

        assert result is False
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value(f"{_FP_KEY_PREFIX}{fp}", None, type=bool) is False
        _clear_auth(fp)
        _cleanup(w)

    def test_already_authorized_fingerprint_skips_dialog(self, monkeypatch):
        w = _fake_widget(_env("vpn"))
        fp = Dashboard._active_probe_fingerprint(w)
        QSettings("NetSentinel", "NetSentinel").setValue(f"{_FP_KEY_PREFIX}{fp}", True)
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not re-show an already-answered fingerprint")),
        )

        assert Dashboard._ensure_active_probe_authorization(w) is True
        _clear_auth(fp)
        _cleanup(w)

    def test_already_declined_fingerprint_skips_dialog_and_stays_false(self, monkeypatch):
        w = _fake_widget(_env("vpn"))
        fp = Dashboard._active_probe_fingerprint(w)
        QSettings("NetSentinel", "NetSentinel").setValue(f"{_FP_KEY_PREFIX}{fp}", False)
        monkeypatch.setattr(
            QMessageBox, "exec",
            MagicMock(side_effect=AssertionError("must not re-show an already-answered fingerprint")),
        )

        assert Dashboard._ensure_active_probe_authorization(w) is False
        _clear_auth(fp)
        _cleanup(w)

    def test_different_fingerprint_is_asked_separately(self, monkeypatch):
        w1 = _fake_widget(_env("vpn"), _net_info(gateway="10.10.0.1"))
        w2 = _fake_widget(_env("vpn"), _net_info(gateway="10.20.0.1"))
        fp1 = Dashboard._active_probe_fingerprint(w1)
        fp2 = Dashboard._active_probe_fingerprint(w2)
        assert fp1 != fp2
        _clear_auth(fp1)
        _clear_auth(fp2)
        QSettings("NetSentinel", "NetSentinel").setValue(f"{_FP_KEY_PREFIX}{fp1}", True)

        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "No / Not sure"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        # fp1 already authorized -- must not re-prompt (would raise if it tried
        # a real dialog exec with a bad clickedButton wiring, but simplest is
        # just to check the returned value matches the stored one).
        assert Dashboard._ensure_active_probe_authorization(w1) is True
        # fp2 never asked -- prompts and (per the mocked "No" click) is declined.
        assert Dashboard._ensure_active_probe_authorization(w2) is False

        _clear_auth(fp1)
        _clear_auth(fp2)
        _cleanup(w1)
        _cleanup(w2)


class TestConfirmCredentialTestOnManagedNetwork:
    def test_continue_returns_true(self, monkeypatch):
        w = _fake_widget(_env("vpn"))
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "Continue"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        assert Dashboard._confirm_credential_test_on_managed_network(w, "10.10.5.5") is True
        _cleanup(w)

    def test_cancel_returns_false(self, monkeypatch):
        w = _fake_widget(_env("vpn"))
        monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
        btn = MagicMock()
        btn.text.return_value = "Cancel"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        assert Dashboard._confirm_credential_test_on_managed_network(w, "10.10.5.5") is False
        _cleanup(w)

    def test_never_persisted_asks_again_every_call(self, monkeypatch):
        w = _fake_widget(_env("corporate"))
        exec_calls = MagicMock(return_value=0)
        monkeypatch.setattr(QMessageBox, "exec", exec_calls)
        btn = MagicMock()
        btn.text.return_value = "Continue"
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: btn)

        Dashboard._confirm_credential_test_on_managed_network(w, "10.10.5.5")
        Dashboard._confirm_credential_test_on_managed_network(w, "10.10.5.5")

        assert exec_calls.call_count == 2
        _cleanup(w)


class _StubWorker:
    """Captures constructor kwargs so tests can assert on rate_pps/host without
    a real SYN/UDP/credential probe ever running."""
    last_kwargs = None

    def __init__(self, **kw):
        type(self).last_kwargs = kw
        self.result = MagicMock()
        self.status = MagicMock()
        self.error = MagicMock()

    def start(self):
        pass


def _syn_fake(host="192.168.1.50", authorized=True, kind="home", rate=500):
    fake = MagicMock()
    fake._syn_host.text.return_value = host
    fake._syn_worker = None
    fake._syn_ports_combo.currentText.return_value = "Top 1000"
    fake._syn_rate.value.return_value = rate
    fake._net_env = NetworkEnvironment(kind=kind)
    fake._ensure_active_probe_authorization = MagicMock(return_value=authorized)
    return fake


class TestStartSynScanGating:
    def test_excluded_host_never_constructs_worker(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.SYNScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: True)
        _StubWorker.last_kwargs = None
        fake = _syn_fake()

        Dashboard._start_syn_scan(fake)

        assert _StubWorker.last_kwargs is None
        fake._syn_status.setText.assert_called()
        assert "exclusion list" in fake._syn_status.setText.call_args[0][0]

    def test_unauthorized_network_caps_rate_to_polite_tier(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.SYNScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _syn_fake(authorized=False, kind="corporate", rate=500)

        Dashboard._start_syn_scan(fake)

        assert _StubWorker.last_kwargs is not None
        assert _StubWorker.last_kwargs["rate_pps"] == 50

    def test_authorized_home_network_uses_requested_rate_unchanged(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.SYNScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _syn_fake(authorized=True, kind="home", rate=500)

        Dashboard._start_syn_scan(fake)

        assert _StubWorker.last_kwargs is not None
        assert _StubWorker.last_kwargs["rate_pps"] == 500

    def test_authorized_managed_network_caps_to_managed_tier(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.SYNScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _syn_fake(authorized=True, kind="vpn", rate=500)

        Dashboard._start_syn_scan(fake)

        assert _StubWorker.last_kwargs["rate_pps"] == 150


def _cred_fake(host="192.168.1.50", authorized=True, kind="home", confirm_managed=True):
    fake = MagicMock()
    fake._cred_host.text.return_value = host
    fake._cred_worker = None
    fake._cred_port.value.return_value = 22
    fake._cred_user.text.return_value = "root"
    fake._cred_pass.text.return_value = ""
    fake._cred_key.text.return_value = ""
    fake._cred_os.currentText.return_value = "auto"
    fake._net_env = NetworkEnvironment(kind=kind)
    fake._ensure_active_probe_authorization = MagicMock(return_value=authorized)
    fake._confirm_credential_test_on_managed_network = MagicMock(return_value=confirm_managed)
    return fake


class TestStartCredScanGating:
    def test_excluded_host_never_constructs_worker(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.CredentialedScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: True)
        _StubWorker.last_kwargs = None
        fake = _cred_fake()

        Dashboard._start_cred_scan(fake)

        assert _StubWorker.last_kwargs is None
        assert "exclusion list" in fake._cred_status.setText.call_args[0][0]

    def test_unauthorized_network_refuses_to_run_at_all(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.CredentialedScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _cred_fake(authorized=False, kind="corporate")

        Dashboard._start_cred_scan(fake)

        assert _StubWorker.last_kwargs is None
        assert "authorization" in fake._cred_status.setText.call_args[0][0].lower()

    def test_authorized_managed_network_cancel_extra_confirm_refuses(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.CredentialedScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _cred_fake(authorized=True, kind="vpn", confirm_managed=False)

        Dashboard._start_cred_scan(fake)

        assert _StubWorker.last_kwargs is None
        fake._confirm_credential_test_on_managed_network.assert_called_once()

    def test_authorized_managed_network_confirm_proceeds(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.CredentialedScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _cred_fake(authorized=True, kind="vpn", confirm_managed=True)

        Dashboard._start_cred_scan(fake)

        assert _StubWorker.last_kwargs is not None

    def test_authorized_home_network_skips_extra_confirm_entirely(self, monkeypatch):
        monkeypatch.setattr("workers.scan_worker.CredentialedScanWorker", _StubWorker)
        monkeypatch.setattr("ui.scan_settings.is_host_excluded", lambda h: False)
        _StubWorker.last_kwargs = None
        fake = _cred_fake(authorized=True, kind="home")

        Dashboard._start_cred_scan(fake)

        assert _StubWorker.last_kwargs is not None
        fake._confirm_credential_test_on_managed_network.assert_not_called()

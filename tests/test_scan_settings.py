"""Tests for ui.scan_settings — environment-aware "flush caches before scan" default.

QSettings key scan/flush_caches:
  absent  -> default computed from detect_environment().kind ("home" -> True, else False)
  present -> explicit user override always wins, regardless of environment
"""
import pytest

try:
    from PyQt6.QtCore import QSettings
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt6 not available")

_KEY = "scan/flush_caches"


def _fresh():
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.remove(_KEY)
    return qs


class TestEffectiveFlushCaches:
    def setup_method(self):    _fresh()
    def teardown_method(self): _fresh()

    def test_defaults_true_on_home_network(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "home"})(),
        )
        assert effective_flush_caches() is True

    def test_defaults_false_on_vpn_network(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "vpn"})(),
        )
        assert effective_flush_caches() is False

    def test_defaults_false_on_corporate_network(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "corporate"})(),
        )
        assert effective_flush_caches() is False

    def test_defaults_false_on_large_subnet(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "large_subnet"})(),
        )
        assert effective_flush_caches() is False

    def test_explicit_true_override_wins_on_vpn_network(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "vpn"})(),
        )
        QSettings("NetSentinel", "NetSentinel").setValue(_KEY, True)
        assert effective_flush_caches() is True

    def test_explicit_false_override_wins_on_home_network(self, monkeypatch):
        from ui.scan_settings import effective_flush_caches
        monkeypatch.setattr(
            "modules.network_environment.detect_environment",
            lambda: type("E", (), {"kind": "home"})(),
        )
        QSettings("NetSentinel", "NetSentinel").setValue(_KEY, False)
        assert effective_flush_caches() is False


def _env(kind: str, scope_cidr: str = "192.168.1.0/24"):
    return type("E", (), {"kind": kind, "scope_cidr": scope_cidr})()


_SCOPE_KEY = "scan/bound_scope"
_AUTH_PREFIX = "scan/net_auth/"
_EXCLUDED_KEY = "scan/excluded_hosts"


class TestEffectiveScanScopeCidr:
    """L5: scope_cidr bounding defaults ON for non-home kinds (mirrors the
    effective_flush_caches() env-aware-default precedent), OFF for home — a
    home ARP table essentially never contains foreign-subnet noise anyway, so
    this is empirically a no-op there, but stays structurally opt-in-only."""

    def setup_method(self):    QSettings("NetSentinel", "NetSentinel").remove(_SCOPE_KEY)
    def teardown_method(self): QSettings("NetSentinel", "NetSentinel").remove(_SCOPE_KEY)

    def test_home_defaults_to_no_bounding(self):
        from ui.scan_settings import effective_scan_scope_cidr
        assert effective_scan_scope_cidr(_env("home")) is None

    def test_vpn_defaults_to_bounded_by_scope_cidr(self):
        from ui.scan_settings import effective_scan_scope_cidr
        assert effective_scan_scope_cidr(_env("vpn", "10.10.0.0/16")) == "10.10.0.0/16"

    def test_corporate_defaults_to_bounded(self):
        from ui.scan_settings import effective_scan_scope_cidr
        assert effective_scan_scope_cidr(_env("corporate", "10.20.0.0/16")) == "10.20.0.0/16"

    def test_large_subnet_defaults_to_bounded(self):
        from ui.scan_settings import effective_scan_scope_cidr
        assert effective_scan_scope_cidr(_env("large_subnet", "172.16.0.0/20")) == "172.16.0.0/20"

    def test_explicit_true_override_bounds_home_too(self):
        from ui.scan_settings import effective_scan_scope_cidr
        QSettings("NetSentinel", "NetSentinel").setValue(_SCOPE_KEY, True)
        assert effective_scan_scope_cidr(_env("home", "192.168.1.0/24")) == "192.168.1.0/24"

    def test_explicit_false_override_disables_bounding_on_vpn(self):
        from ui.scan_settings import effective_scan_scope_cidr
        QSettings("NetSentinel", "NetSentinel").setValue(_SCOPE_KEY, False)
        assert effective_scan_scope_cidr(_env("vpn", "10.10.0.0/16")) is None

    def test_blank_scope_cidr_on_environment_yields_none_even_when_bounded(self):
        from ui.scan_settings import effective_scan_scope_cidr
        assert effective_scan_scope_cidr(_env("vpn", "")) is None


class TestNetworkAuthorization:
    """L6: per-fingerprint authorization state, keyed by gateway MAC + subnet
    (modules.network_environment.network_fingerprint()), not by environment kind."""

    def setup_method(self):
        QSettings("NetSentinel", "NetSentinel").remove(f"{_AUTH_PREFIX}fp1")

    def teardown_method(self):
        QSettings("NetSentinel", "NetSentinel").remove(f"{_AUTH_PREFIX}fp1")

    def test_unknown_fingerprint_returns_none(self):
        from ui.scan_settings import is_network_authorized
        assert is_network_authorized("fp1") is None

    def test_set_true_then_read_true(self):
        from ui.scan_settings import is_network_authorized, set_network_authorized
        set_network_authorized("fp1", True)
        assert is_network_authorized("fp1") is True

    def test_set_false_then_read_false(self):
        from ui.scan_settings import is_network_authorized, set_network_authorized
        set_network_authorized("fp1", False)
        assert is_network_authorized("fp1") is False

    def test_different_fingerprints_are_independent(self):
        from ui.scan_settings import is_network_authorized, set_network_authorized
        set_network_authorized("fp1", True)
        assert is_network_authorized("fp2") is None
        QSettings("NetSentinel", "NetSentinel").remove(f"{_AUTH_PREFIX}fp2")


class TestEffectiveSynRateCap:
    """L6: unauthorized -> polite tier regardless of kind; authorized+managed
    (vpn/corporate) -> a still-reduced managed tier; authorized+home/large_subnet
    -> the user's requested rate, unchanged."""

    def test_unauthorized_caps_to_polite_tier_regardless_of_kind(self):
        from ui.scan_settings import effective_syn_rate_cap
        assert effective_syn_rate_cap(500, authorized=None, kind="home") == 50
        assert effective_syn_rate_cap(500, authorized=False, kind="corporate") == 50

    def test_unauthorized_never_raises_a_low_request(self):
        from ui.scan_settings import effective_syn_rate_cap
        assert effective_syn_rate_cap(10, authorized=False, kind="home") == 10

    def test_authorized_managed_network_caps_to_managed_tier(self):
        from ui.scan_settings import effective_syn_rate_cap
        assert effective_syn_rate_cap(500, authorized=True, kind="vpn") == 150
        assert effective_syn_rate_cap(500, authorized=True, kind="corporate") == 150

    def test_authorized_home_network_uses_full_requested_rate(self):
        from ui.scan_settings import effective_syn_rate_cap
        assert effective_syn_rate_cap(500, authorized=True, kind="home") == 500

    def test_authorized_large_subnet_uses_full_requested_rate(self):
        from ui.scan_settings import effective_syn_rate_cap
        assert effective_syn_rate_cap(500, authorized=True, kind="large_subnet") == 500


class TestExcludedHosts:
    def setup_method(self):    QSettings("NetSentinel", "NetSentinel").remove(_EXCLUDED_KEY)
    def teardown_method(self): QSettings("NetSentinel", "NetSentinel").remove(_EXCLUDED_KEY)

    def test_defaults_to_empty_list(self):
        from ui.scan_settings import get_excluded_hosts
        assert get_excluded_hosts() == []

    def test_set_then_get_round_trips(self):
        from ui.scan_settings import get_excluded_hosts, set_excluded_hosts
        set_excluded_hosts(["192.168.1.5", "printer.local"])
        assert get_excluded_hosts() == ["192.168.1.5", "printer.local"]

    def test_set_strips_blank_entries(self):
        from ui.scan_settings import get_excluded_hosts, set_excluded_hosts
        set_excluded_hosts(["192.168.1.5", "  ", "", "printer.local"])
        assert get_excluded_hosts() == ["192.168.1.5", "printer.local"]

    def test_is_host_excluded_true_for_listed_host(self):
        from ui.scan_settings import is_host_excluded, set_excluded_hosts
        set_excluded_hosts(["192.168.1.5"])
        assert is_host_excluded("192.168.1.5") is True

    def test_is_host_excluded_false_for_unlisted_host(self):
        from ui.scan_settings import is_host_excluded, set_excluded_hosts
        set_excluded_hosts(["192.168.1.5"])
        assert is_host_excluded("192.168.1.6") is False

    def test_is_host_excluded_is_case_insensitive_for_hostnames(self):
        from ui.scan_settings import is_host_excluded, set_excluded_hosts
        set_excluded_hosts(["Printer.local"])
        assert is_host_excluded("printer.local") is True

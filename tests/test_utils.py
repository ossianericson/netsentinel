"""
Behavioural tests for modules/utils.py

Covers:
  - flush_network_caches()  — returns (label, bool) tuples; never raises
  - get_local_ip()          — returns a valid IPv4 string; falls back to 127.0.0.1
  - ping_sweep_subnet()     — returns only IPs that responded; bad input → []

All network / subprocess calls are mocked — no real sockets or processes.
"""

import sys
import os
import subprocess
from unittest.mock import patch, MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.utils import flush_network_caches, get_local_ip, ping_sweep_subnet


# ── flush_network_caches ──────────────────────────────────────────────────────

class TestFlushNetworkCaches:
    def test_returns_list_of_tuples(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            results = flush_network_caches()
        assert isinstance(results, list)
        assert len(results) > 0
        for label, success in results:
            assert isinstance(label, str)
            assert isinstance(success, bool)

    def test_all_labels_non_empty(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            results = flush_network_caches()
        for label, _ in results:
            assert len(label) > 0

    def test_success_true_when_subprocess_does_not_raise(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            results = flush_network_caches()
        assert all(success is True for _, success in results)

    def test_success_false_when_subprocess_raises(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("no binary")):
            results = flush_network_caches()
        assert all(success is False for _, success in results)

    def test_never_raises_on_subprocess_exception(self):
        with patch("subprocess.run", side_effect=OSError("kernel error")):
            # Must not raise — caller should always get a result list
            results = flush_network_caches()
        assert isinstance(results, list)

    def test_timeout_exception_yields_false(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="arp", timeout=6)):
            results = flush_network_caches()
        assert all(success is False for _, success in results)


# ── get_local_ip ──────────────────────────────────────────────────────────────

class TestGetLocalIp:
    def test_returns_string(self):
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = lambda s: s
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.getsockname.return_value = ("192.168.1.5", 0)
            mock_sock_cls.return_value = mock_sock
            result = get_local_ip()
        assert isinstance(result, str)

    def test_returns_ip_from_socket(self):
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = lambda s: s
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.getsockname.return_value = ("10.0.0.42", 0)
            mock_sock_cls.return_value = mock_sock
            result = get_local_ip()
        assert result == "10.0.0.42"

    def test_falls_back_to_loopback_on_socket_error(self):
        with patch("socket.socket", side_effect=OSError("network unreachable")):
            result = get_local_ip()
        assert result == "127.0.0.1"

    def test_falls_back_to_loopback_on_connect_error(self):
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = lambda s: s
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.connect.side_effect = OSError("no route")
            mock_sock_cls.return_value = mock_sock
            result = get_local_ip()
        assert result == "127.0.0.1"

    def test_result_has_four_octets(self):
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.__enter__ = lambda s: s
            mock_sock.__exit__ = MagicMock(return_value=False)
            mock_sock.getsockname.return_value = ("172.16.0.1", 0)
            mock_sock_cls.return_value = mock_sock
            result = get_local_ip()
        parts = result.split(".")
        assert len(parts) == 4
        assert all(p.isdigit() for p in parts)


# ── ping_sweep_subnet ─────────────────────────────────────────────────────────

class TestPingSweepSubnet:
    def _make_run(self, alive_ips):
        """Return a subprocess.run mock where only alive_ips return code 0."""
        def _run(cmd, **kwargs):
            ip = cmd[-1]
            mock = MagicMock()
            mock.returncode = 0 if ip in alive_ips else 1
            return mock
        return _run

    def test_returns_only_alive_ips(self):
        alive = {"192.168.1.1", "192.168.1.100"}
        with patch("subprocess.run", side_effect=self._make_run(alive)):
            result = ping_sweep_subnet("192.168.1.50")
        assert set(result) == alive

    def test_returns_empty_list_when_none_respond(self):
        with patch("subprocess.run", side_effect=self._make_run(set())):
            result = ping_sweep_subnet("192.168.1.50")
        assert result == []

    def test_bad_ip_returns_empty(self):
        # Should not raise and should return [] for non-IPv4 input
        result = ping_sweep_subnet("not-an-ip")
        assert result == []

    def test_bad_ip_too_few_octets_returns_empty(self):
        result = ping_sweep_subnet("192.168")
        assert result == []

    def test_sweeps_correct_subnet(self):
        """All probed IPs must be in the same /24 as the given local IP."""
        probed = []

        def _run(cmd, **kwargs):
            probed.append(cmd[-1])
            mock = MagicMock()
            mock.returncode = 1
            return mock

        with patch("subprocess.run", side_effect=_run):
            ping_sweep_subnet("10.0.5.7")

        assert len(probed) == 254
        for ip in probed:
            assert ip.startswith("10.0.5.")

    def test_exception_during_ping_does_not_propagate(self):
        with patch("subprocess.run", side_effect=OSError("ping failed")):
            result = ping_sweep_subnet("192.168.1.1")
        assert isinstance(result, list)

    def test_all_254_hosts_probed(self):
        probed = []

        def _run(cmd, **kwargs):
            probed.append(cmd[-1])
            mock = MagicMock()
            mock.returncode = 1
            return mock

        with patch("subprocess.run", side_effect=_run):
            ping_sweep_subnet("192.168.0.1")

        assert len(probed) == 254

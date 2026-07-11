"""
Tests for modules/firewall_control.py

Pure-Python Windows Firewall (netsh) helpers extracted from
ui/pages/connections_page.py so they can run inside a QThread worker
(workers/firewall_worker.py) instead of blocking the GUI thread (RULE 4).

Covers:
  - rule_name() naming convention
  - block_process() / unblock_process() / get_blocked_rules() success paths
  - non-Windows short-circuit
  - subprocess failure / non-zero returncode handling
"""
from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

from modules.firewall_control import (
    block_process,
    get_blocked_rules,
    rule_name,
    unblock_process,
)


def test_rule_name_prefix():
    assert rule_name("chrome.exe") == "NS-Block-chrome.exe"


class TestBlockProcess:
    def test_non_windows_short_circuits(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        ok, msg = block_process("/usr/bin/foo", "foo")
        assert ok is False
        assert "Windows" in msg

    def test_no_exe_path(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        ok, msg = block_process("", "foo.exe")
        assert ok is False
        assert "foo.exe" in msg

    def test_success(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        fake_result = MagicMock(returncode=0, stdout="Ok.", stderr="")
        with patch("modules.firewall_control.subprocess.run", return_value=fake_result) as m:
            ok, msg = block_process("C:\\Program Files\\Foo\\foo.exe", "foo.exe")
        assert ok is True
        assert "foo.exe" in msg
        cmd = m.call_args[0][0]
        assert cmd[0] == "netsh"
        assert "name=NS-Block-foo.exe" in cmd
        assert m.call_args.kwargs.get("timeout") == 10

    def test_failure_returns_stderr(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        fake_result = MagicMock(returncode=1, stdout="", stderr="Access denied.")
        with patch("modules.firewall_control.subprocess.run", return_value=fake_result):
            ok, msg = block_process("C:\\foo.exe", "foo.exe")
        assert ok is False
        assert "Access denied" in msg

    def test_subprocess_exception_caught(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("modules.firewall_control.subprocess.run", side_effect=subprocess.TimeoutExpired("netsh", 10)):
            ok, msg = block_process("C:\\foo.exe", "foo.exe")
        assert ok is False


class TestUnblockProcess:
    def test_non_windows_short_circuits(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        ok, msg = unblock_process("foo.exe")
        assert ok is False

    def test_success(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        fake_result = MagicMock(returncode=0, stdout="Ok.", stderr="")
        with patch("modules.firewall_control.subprocess.run", return_value=fake_result):
            ok, msg = unblock_process("foo.exe")
        assert ok is True
        assert "foo.exe" in msg

    def test_rule_not_found(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        fake_result = MagicMock(returncode=1, stdout="", stderr="")
        with patch("modules.firewall_control.subprocess.run", return_value=fake_result):
            ok, msg = unblock_process("foo.exe")
        assert ok is False
        assert "not found" in msg.lower()


class TestGetBlockedRules:
    def test_non_windows_returns_empty(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert get_blocked_rules() == []

    def test_parses_rule_names(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        stdout = (
            "Rule Name:                           NS-Block-chrome.exe\n"
            "----------------------------------------------------------------------\n"
            "Enabled:                              Yes\n\n"
            "Rule Name:                           NS-Block-steam.exe\n"
        )
        fake_result = MagicMock(returncode=0, stdout=stdout, stderr="")
        with patch("modules.firewall_control.subprocess.run", return_value=fake_result):
            rules = get_blocked_rules()
        assert rules == ["chrome.exe", "steam.exe"]

    def test_exception_returns_empty(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with patch("modules.firewall_control.subprocess.run", side_effect=OSError("boom")):
            assert get_blocked_rules() == []

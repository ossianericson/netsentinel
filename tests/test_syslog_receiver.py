"""
Tests for T3#14 — Syslog receiver module.

Covers:
  • RFC 3164 parsing (with and without tag/PID)
  • RFC 5424 parsing
  • PRI field → facility + severity decoding
  • Malformed/bare messages — graceful degradation
  • SyslogReceiver lifecycle (open / receive / close)
  • SyslogMessage dataclass defaults
"""

from __future__ import annotations

import socket
import threading
import time


from modules.syslog_receiver import (
    SyslogMessage,
    SyslogReceiver,
    parse_syslog_message,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _raw(msg: str) -> bytes:
    return msg.encode("utf-8")


# ── PRI / facility / severity decoding ───────────────────────────────────────

class TestPriDecoding:
    def test_facility_and_severity_from_pri(self):
        # PRI 34 = facility 4 (auth), severity 2 (CRIT)
        msg = parse_syslog_message(_raw("<34>Oct 11 22:14:15 host su: failed"), "1.2.3.4", 0)
        assert msg.facility == 4
        assert msg.severity == 2

    def test_facility_name_auth(self):
        msg = parse_syslog_message(_raw("<34>Oct 11 22:14:15 host su: failed"), "1.2.3.4", 0)
        assert msg.facility_name == "auth"

    def test_severity_name_crit(self):
        msg = parse_syslog_message(_raw("<34>Oct 11 22:14:15 host su: failed"), "1.2.3.4", 0)
        assert msg.severity_name == "CRIT"

    def test_pri_0_kern_emerg(self):
        msg = parse_syslog_message(_raw("<0>Oct  1 00:00:00 host kernel: panic"), "1.2.3.4", 0)
        assert msg.facility == 0
        assert msg.severity == 0
        assert msg.facility_name == "kern"
        assert msg.severity_name == "EMERG"

    def test_pri_local7_debug(self):
        # facility 23 = local7, severity 7 = DEBUG → PRI = 23*8+7 = 191
        msg = parse_syslog_message(_raw("<191>Oct  1 00:00:00 host myapp: debug msg"), "1.2.3.4", 0)
        assert msg.facility == 23
        assert msg.severity == 7
        assert msg.facility_name == "local7"
        assert msg.severity_name == "DEBUG"

    def test_src_ip_preserved(self):
        msg = parse_syslog_message(_raw("<13>Oct  1 00:00:01 host app: msg"), "10.0.0.99", 514)
        assert msg.src_ip == "10.0.0.99"
        assert msg.src_port == 514


# ── RFC 3164 parsing ──────────────────────────────────────────────────────────

class TestRfc3164:
    def test_hostname_extracted(self):
        msg = parse_syslog_message(
            _raw("<13>Oct 11 22:14:15 myhost sshd[1234]: Connection from 1.2.3.4"),
            "10.0.0.1", 514,
        )
        assert msg.hostname == "myhost"

    def test_app_name_extracted(self):
        msg = parse_syslog_message(
            _raw("<13>Oct 11 22:14:15 myhost sshd[1234]: Connection from 1.2.3.4"),
            "10.0.0.1", 514,
        )
        assert msg.app_name == "sshd"

    def test_procid_extracted(self):
        msg = parse_syslog_message(
            _raw("<13>Oct 11 22:14:15 myhost sshd[1234]: Connection from 1.2.3.4"),
            "10.0.0.1", 514,
        )
        assert msg.procid == "1234"

    def test_message_extracted(self):
        msg = parse_syslog_message(
            _raw("<13>Oct 11 22:14:15 myhost sshd[1234]: Connection from 1.2.3.4"),
            "10.0.0.1", 514,
        )
        assert "Connection from" in msg.message

    def test_no_pid_still_parses(self):
        msg = parse_syslog_message(
            _raw("<13>Oct 11 22:14:15 myhost cron: job ran"),
            "10.0.0.1", 514,
        )
        assert msg.app_name == "cron"
        assert "job ran" in msg.message

    def test_single_digit_day(self):
        msg = parse_syslog_message(
            _raw("<13>Oct  1 08:00:00 router dhcpd: OFFER sent"),
            "10.0.0.1", 514,
        )
        assert msg.hostname == "router"

    def test_raw_preserved(self):
        raw_str = "<13>Oct 11 22:14:15 myhost sshd[1234]: Connection from 1.2.3.4"
        msg = parse_syslog_message(_raw(raw_str), "10.0.0.1", 514)
        assert msg.raw == raw_str


# ── RFC 5424 parsing ──────────────────────────────────────────────────────────

class TestRfc5424:
    def test_version_1_detected(self):
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15.003Z mymachine.example.com evntslog - ID47 - An application event"),
            "10.0.0.1", 514,
        )
        assert msg.raw_error == ""

    def test_hostname_extracted(self):
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15Z mymachine evntslog - ID47 - payload"),
            "10.0.0.1", 514,
        )
        assert msg.hostname == "mymachine"

    def test_app_name_extracted(self):
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15Z mymachine evntslog 42 ID47 - payload"),
            "10.0.0.1", 514,
        )
        assert msg.app_name == "evntslog"

    def test_procid_extracted(self):
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15Z mymachine evntslog 42 ID47 - payload"),
            "10.0.0.1", 514,
        )
        assert msg.procid == "42"

    def test_message_extracted(self):
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15Z mymachine evntslog - ID47 - An application event"),
            "10.0.0.1", 514,
        )
        assert "application event" in msg.message

    def test_facility_severity_correct(self):
        # PRI 165 = facility 20 (local4), severity 5 (NOTICE)
        msg = parse_syslog_message(
            _raw("<165>1 2003-10-11T22:14:15Z mymachine evntslog - ID47 - payload"),
            "10.0.0.1", 514,
        )
        assert msg.facility == 20
        assert msg.severity == 5


# ── Malformed / edge cases ────────────────────────────────────────────────────

class TestMalformed:
    def test_empty_bytes_returns_message(self):
        msg = parse_syslog_message(b"", "1.2.3.4", 514)
        assert isinstance(msg, SyslogMessage)
        assert msg.raw_error != ""

    def test_no_pri_field(self):
        msg = parse_syslog_message(_raw("plain text without priority"), "1.2.3.4", 514)
        assert isinstance(msg, SyslogMessage)
        assert msg.raw_error != ""

    def test_src_ip_always_set(self):
        msg = parse_syslog_message(b"\xff\xfe", "9.9.9.9", 999)
        assert msg.src_ip == "9.9.9.9"

    def test_bare_pri_only(self):
        """<PRI> with no timestamp/hostname — should still return a usable message."""
        msg = parse_syslog_message(_raw("<13>just a bare message"), "1.2.3.4", 514)
        assert isinstance(msg, SyslogMessage)
        # either parsed successfully or error flagged — must not crash
        assert msg.src_ip == "1.2.3.4"


# ── SyslogReceiver lifecycle ──────────────────────────────────────────────────

class TestSyslogReceiver:
    def test_open_and_close(self):
        r = SyslogReceiver(port=0)
        port = r.open()
        assert port > 0
        r.close()

    def test_listen_port_set_after_open(self):
        r = SyslogReceiver(port=0)
        r.open()
        assert r.listen_port > 0
        r.close()

    def test_receive_one_returns_message(self):
        """Send a syslog UDP packet and verify it is decoded."""
        r = SyslogReceiver(port=0)
        r.open()
        port = r.listen_port

        raw = b"<13>Oct 11 22:14:15 myhost sshd[1234]: hello from test"

        def _send():
            time.sleep(0.05)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(raw, ("127.0.0.1", port))
            s.close()

        threading.Thread(target=_send, daemon=True).start()
        msg = r.receive_one()
        r.close()
        assert msg is not None
        assert "hello from test" in msg.message

    def test_receive_one_returns_none_on_timeout(self):
        r = SyslogReceiver(port=0)
        r.open()
        result = r.receive_one()
        r.close()
        assert result is None

    def test_on_message_callback_called(self):
        received = []
        r = SyslogReceiver(port=0, on_message=received.append)
        r.open()
        port = r.listen_port

        raw = b"<13>Oct 11 22:14:15 myhost sshd[1234]: callback test"

        def _send():
            time.sleep(0.05)
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.sendto(raw, ("127.0.0.1", port))
            s.close()

        threading.Thread(target=_send, daemon=True).start()
        r.receive_one()
        r.close()
        assert len(received) == 1
        assert "callback test" in received[0].message

    def test_close_twice_no_error(self):
        r = SyslogReceiver(port=0)
        r.open()
        r.close()
        r.close()


# ── SyslogMessage dataclass ───────────────────────────────────────────────────

class TestSyslogMessageDataclass:
    def test_raw_error_defaults_empty(self):
        m = SyslogMessage(
            ts=0, src_ip="", src_port=0,
            facility=0, facility_name="kern",
            severity=6, severity_name="INFO",
            hostname="", app_name="", procid="",
            message="", raw="",
        )
        assert m.raw_error == ""

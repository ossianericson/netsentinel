"""RULE-WIN25 — a WSAECONNRESET must not end a long-lived UDP listen loop.

Mechanism. On Windows a UDP ``recvfrom()`` raises ``ConnectionResetError``
(WSAECONNRESET) when a *previously sent* datagram drew an ICMP port-unreachable back.
The socket is untouched and still perfectly usable — this is routine traffic noise,
and it is far more common on networks with aggressive ISP CPE (the norm on Indian and
Bolivian consumer connections) than on a quiet developer LAN.

Two shapes turned that routine event into a permanently dead listener:

1. ``receive_one()`` caught only ``socket.timeout``, so the reset propagated out.
2. ``workers/syslog_worker.py`` and ``workers/snmp_trap_worker.py`` wrap the ``while``
   loop in a single ``try/except Exception`` with ``finally: receiver.close()`` — so
   one escaping reset exits the loop, closes the socket and ends the thread. Nothing
   restarts it. The page just stops updating, silently, for the rest of the session.

The same reasoning covers ``passive_observer``'s SSDP/mDNS daemon threads, whose
``except OSError: break`` catches ``ConnectionResetError`` because it *is* an
``OSError``.
"""
from __future__ import annotations

import socket

import pytest

from modules.snmp_trap_receiver import SnmpTrapReceiver
from modules.syslog_receiver import SyslogReceiver


class _ResetThenDataSocket:
    """A socket whose first ``recvfrom`` resets, then behaves normally.

    Models the real sequence: an ICMP port-unreachable for an earlier datagram arrives
    first, and a genuine message follows. A correct loop must see the second one.
    """

    def __init__(self, payload: bytes, src=("192.0.2.10", 514)):
        self._calls = 0
        self._payload = payload
        self._src = src
        self.closed = False

    def recvfrom(self, _bufsize):
        self._calls += 1
        if self._calls == 1:
            raise ConnectionResetError(10054, "WSAECONNRESET")
        return self._payload, self._src

    def close(self):
        self.closed = True

    @property
    def call_count(self) -> int:
        return self._calls


def test_syslog_receive_one_treats_a_reset_as_a_non_event():
    """RED before the fix: ``ConnectionResetError`` escapes ``except socket.timeout``."""
    recv = SyslogReceiver(port=0)
    recv._sock = _ResetThenDataSocket(b"<34>Oct 11 22:14:15 host su: failed")

    # Must return None (same contract as a timeout) rather than raising — the worker's
    # loop-level handler would otherwise close the socket and end the thread.
    assert recv.receive_one() is None

    # And the very next call must still work: the socket was never actually broken.
    msg = recv.receive_one()
    assert msg is not None
    assert msg.src_ip == "192.0.2.10"


def test_snmp_receive_one_treats_a_reset_as_a_non_event():
    """Same defect, same shape, in the SNMP trap receiver."""
    recv = SnmpTrapReceiver(port=0)
    recv._sock = _ResetThenDataSocket(b"\x30\x0c\x02\x01\x00\x04\x06public", ("192.0.2.11", 162))

    assert recv.receive_one() is None
    # A malformed/undecodable trap may still yield None, but it must not RAISE —
    # raising is what kills the listener thread.
    recv.receive_one()


def test_a_real_timeout_is_still_reported_as_a_timeout():
    """The reset fix must not swallow the timeout contract the loop depends on."""
    class _AlwaysTimeout:
        def recvfrom(self, _n):
            raise socket.timeout()

    recv = SyslogReceiver(port=0)
    recv._sock = _AlwaysTimeout()
    assert recv.receive_one() is None


def test_a_genuine_socket_error_still_propagates():
    """Only the reset is downgraded — a real failure must still reach the worker.

    Without this, the fix would hide the socket-closed error that ``stop()`` relies on
    to unblock the thread, and shutdown would hang instead of crashing.
    """
    class _Broken:
        def recvfrom(self, _n):
            raise OSError(9, "Bad file descriptor")

    recv = SyslogReceiver(port=0)
    recv._sock = _Broken()
    with pytest.raises(OSError):
        recv.receive_one()


# ── passive_observer SSDP / mDNS daemon threads ──────────────────────────────
# Same mechanism, third shape: `except OSError: break`. ConnectionResetError IS an
# OSError, so the identical stray ICMP silently ends both discovery threads. Nothing
# restarts them and nothing surfaces the failure — device classification just degrades.

class _ResetThenStopSocket:
    """First recvfrom resets; the second sets the stop event and times out."""

    def __init__(self, stop_event):
        self._calls = 0
        self._stop = stop_event
        self.closed = False

    def recvfrom(self, _n):
        self._calls += 1
        if self._calls == 1:
            raise ConnectionResetError(10054, "WSAECONNRESET")
        self._stop.set()
        raise socket.timeout()

    def settimeout(self, _t): pass
    def setsockopt(self, *a): pass
    def bind(self, _a): pass
    def close(self): self.closed = True

    @property
    def call_count(self) -> int:
        return self._calls


@pytest.mark.parametrize("fn_name", ["_ssdp_listener", "_mdns_listener"])
def test_passive_listener_survives_a_reset(monkeypatch, fn_name):
    """RED before the fix: `except OSError: break` ends the thread on call 1.

    A surviving loop reaches the second recvfrom (call_count == 2); a broken one stops
    at 1. Asserting the call count rather than "it didn't raise" is what separates
    "kept listening" from "exited quietly", which is the actual defect.
    """
    import threading

    import modules.passive_observer as po

    stop = threading.Event()
    sock = _ResetThenStopSocket(stop)

    monkeypatch.setattr(po, "_stop_event", stop)
    monkeypatch.setattr(po.socket, "socket", lambda *a, **k: sock)
    monkeypatch.setattr(po.socket, "inet_aton", lambda _a: b"\x00\x00\x00\x00")

    getattr(po, fn_name)(lambda *a, **k: None)

    assert sock.call_count == 2, (
        "the listener exited on the ConnectionResetError instead of continuing — "
        "one stray ICMP port-unreachable silently ends passive discovery for the session"
    )

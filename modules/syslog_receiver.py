"""
Syslog Receiver — passive UDP listener for RFC 3164 and RFC 5424 syslog (T3#14).

Uses only the Python standard library — no external dependencies.

Supports:
  • RFC 3164 (BSD syslog): <PRI>Mmm dd hh:mm:ss HOSTNAME TAG: MSG
  • RFC 5424 (IETF syslog): <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG

Port 514 requires administrator/root on most OSes.  When not elevated the
receiver falls back to port 5140 and records that in `listen_port`.

Architecture rules:
  • Pure Python — zero PyQt imports (ARCH RULE 3)
  • No blocking I/O outside the worker thread
"""

from __future__ import annotations

import re
import socket
import time
from dataclasses import dataclass
from typing import Callable, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

SYSLOG_PORT   = 514
FALLBACK_PORT = 5140      # used when not admin
SOCKET_TIMEOUT = 1.0      # seconds — allows clean shutdown

MAX_PACKET = 65535

# Facility names (RFC 5424 table 1)
_FACILITY_NAMES = {
    0:  "kern",     1:  "user",    2:  "mail",      3:  "daemon",
    4:  "auth",     5:  "syslog",  6:  "lpr",       7:  "news",
    8:  "uucp",     9:  "cron",    10: "authpriv",  11: "ftp",
    12: "ntp",      13: "audit",   14: "alert",     15: "clock",
    16: "local0",   17: "local1",  18: "local2",    19: "local3",
    20: "local4",   21: "local5",  22: "local6",    23: "local7",
}

# Severity names (RFC 5424 table 2)
_SEVERITY_NAMES = {
    0: "EMERG",
    1: "ALERT",
    2: "CRIT",
    3: "ERR",
    4: "WARNING",
    5: "NOTICE",
    6: "INFO",
    7: "DEBUG",
}

# RFC 3164 month abbreviations
_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,  "May": 5,  "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Pre-compiled patterns
_PRI_RE      = re.compile(r"^<(\d{1,3})>")
_RFC5424_VER = re.compile(r"^<\d{1,3}>(\d+) ")
_RFC3164_HDR = re.compile(
    r"^<\d{1,3}>([A-Za-z]{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}) (\S+) (.*)$"
)
_RFC5424_HDR = re.compile(
    r"^<\d{1,3}>1 (\S+) (\S+) (\S+) (\S+) (\S+) (\S+|-) (.*)$",
    re.DOTALL,
)


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class SyslogMessage:
    ts:            int       # Unix timestamp (best effort from header or recv time)
    src_ip:        str
    src_port:      int
    facility:      int       # 0-23
    facility_name: str
    severity:      int       # 0-7
    severity_name: str
    hostname:      str
    app_name:      str
    procid:        str
    message:       str
    raw:           str       # original decoded string
    raw_error:     str = ""  # non-empty if parse failed


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_syslog_message(
    data: bytes,
    src_ip: str,
    src_port: int,
) -> SyslogMessage:
    """
    Parse a raw UDP syslog payload into a SyslogMessage.

    Tries RFC 5424 first (has explicit version=1 after PRI), then RFC 3164.
    On any parse error returns a SyslogMessage with raw_error set.
    """
    now = int(time.time())
    raw = ""
    try:
        raw = data.decode("utf-8", errors="replace").rstrip("\x00\n\r")
    except Exception:
        raw = repr(data)

    try:
        return _parse(raw, src_ip, src_port, now)
    except Exception as exc:
        return SyslogMessage(
            ts=now, src_ip=src_ip, src_port=src_port,
            facility=0, facility_name="kern",
            severity=6, severity_name="INFO",
            hostname=src_ip, app_name="", procid="",
            message=raw, raw=raw,
            raw_error=str(exc),
        )


def _parse(raw: str, src_ip: str, src_port: int, now: int) -> SyslogMessage:
    pri_m = _PRI_RE.match(raw)
    if not pri_m:
        raise ValueError("No PRI field found")

    pri       = int(pri_m.group(1))
    facility  = pri >> 3
    severity  = pri & 0x07

    facility_name = _FACILITY_NAMES.get(facility, f"local{facility - 16}" if facility >= 16 else str(facility))
    severity_name = _SEVERITY_NAMES.get(severity, str(severity))

    # Detect version
    ver_m = _RFC5424_VER.match(raw)
    if ver_m and ver_m.group(1) == "1":
        return _parse_rfc5424(raw, src_ip, src_port, now, facility, facility_name, severity, severity_name)
    else:
        return _parse_rfc3164(raw, src_ip, src_port, now, facility, facility_name, severity, severity_name)


def _parse_rfc5424(
    raw: str, src_ip: str, src_port: int, now: int,
    facility: int, facility_name: str, severity: int, severity_name: str,
) -> SyslogMessage:
    m = _RFC5424_HDR.match(raw)
    if not m:
        raise ValueError("Could not match RFC 5424 header")

    timestamp_str, hostname, app_name, procid, _msgid, _sd, message = m.groups()

    ts = _parse_iso_timestamp(timestamp_str, now)

    # Strip structured data from message if it leads with '[...]'
    message = message.lstrip()

    return SyslogMessage(
        ts=ts, src_ip=src_ip, src_port=src_port,
        facility=facility, facility_name=facility_name,
        severity=severity, severity_name=severity_name,
        hostname="-" if hostname == "-" else hostname,
        app_name="-" if app_name == "-" else app_name,
        procid="-" if procid == "-" else procid,
        message=message,
        raw=raw,
    )


def _parse_rfc3164(
    raw: str, src_ip: str, src_port: int, now: int,
    facility: int, facility_name: str, severity: int, severity_name: str,
) -> SyslogMessage:
    m = _RFC3164_HDR.match(raw)
    if not m:
        # Bare message with only PRI
        message = raw[raw.index(">") + 1:].lstrip()
        return SyslogMessage(
            ts=now, src_ip=src_ip, src_port=src_port,
            facility=facility, facility_name=facility_name,
            severity=severity, severity_name=severity_name,
            hostname=src_ip, app_name="", procid="",
            message=message, raw=raw,
        )

    timestamp_str, hostname, rest = m.groups()

    ts = _parse_bsd_timestamp(timestamp_str, now)

    # Split tag (process) from message: "sshd[1234]: text"
    tag_m = re.match(r"^(\S+?)(?:\[(\d+)\])?: ?(.*)", rest, re.DOTALL)
    if tag_m:
        app_name, procid, message = tag_m.groups()
        procid = procid or "-"
    else:
        app_name = ""
        procid   = "-"
        message  = rest

    return SyslogMessage(
        ts=ts, src_ip=src_ip, src_port=src_port,
        facility=facility, facility_name=facility_name,
        severity=severity, severity_name=severity_name,
        hostname=hostname, app_name=app_name, procid=procid,
        message=message, raw=raw,
    )


def _parse_iso_timestamp(ts_str: str, fallback: int) -> int:
    """Parse RFC 5424 ISO 8601 timestamp to Unix time (best effort)."""
    try:
        import datetime
        # Handle optional sub-seconds and timezone
        ts_str = ts_str.rstrip("Z")
        if "." in ts_str:
            ts_str = ts_str.split(".")[0]
        if "+" in ts_str:
            ts_str = ts_str.split("+")[0]
        if "-" in ts_str[10:]:   # timezone offset in date part is the date separator
            ts_str = ts_str[:19]
        dt = datetime.datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
        return int(dt.timestamp())
    except Exception:
        return fallback


def _parse_bsd_timestamp(ts_str: str, fallback: int) -> int:
    """Parse RFC 3164 BSD timestamp (no year) to Unix time (best effort)."""
    try:
        import datetime
        year = datetime.datetime.now(datetime.timezone.utc).year
        dt = datetime.datetime.strptime(f"{year} {ts_str.strip()}", "%Y %b %d %H:%M:%S")
        return int(dt.timestamp())
    except Exception:
        return fallback


# ── Receiver ──────────────────────────────────────────────────────────────────

class SyslogReceiver:
    """
    UDP syslog receiver.

    Parameters
    ----------
    port : int
        Preferred listen port (default 514).  Automatically falls back to
        FALLBACK_PORT if the OS refuses the bind (permission denied).
    bind_address : str
        Interface to bind to.  Empty string = all interfaces.
    on_message : callable | None
        Called with each SyslogMessage immediately after receive_one() decodes it.
    """

    def __init__(
        self,
        port: int = SYSLOG_PORT,
        bind_address: str = "",
        on_message: Optional[Callable[[SyslogMessage], None]] = None,
    ):
        self._port         = port
        self._bind_address = bind_address
        self._on_message   = on_message
        self._sock: Optional[socket.socket] = None
        self.listen_port: int = 0

    def open(self) -> int:
        """
        Bind the UDP socket.  Returns the actual port bound.
        Raises OSError if both the preferred port and fallback fail.
        """
        for attempt_port in (self._port, FALLBACK_PORT, 0):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(SOCKET_TIMEOUT)
                sock.bind((self._bind_address, attempt_port))  # lgtm[py/bind-socket-all-network-interfaces] — syslog receiver intentionally listens on all interfaces
                actual_port = sock.getsockname()[1]
                self._sock = sock
                self.listen_port = actual_port
                return actual_port
            except OSError:
                try:
                    sock.close()
                except Exception:
                    pass  # non-fatal
                continue
        raise OSError(f"Could not bind syslog UDP socket on port {self._port} or fallback {FALLBACK_PORT}")

    def receive_one(self) -> Optional[SyslogMessage]:
        """
        Block up to SOCKET_TIMEOUT seconds for one message.
        Returns None on timeout.  Calls on_message callback if set.
        """
        if self._sock is None:
            return None
        try:
            data, addr = self._sock.recvfrom(MAX_PACKET)
            src_ip, src_port = addr[0], addr[1]
            msg = parse_syslog_message(data, src_ip, src_port)
            if self._on_message:
                self._on_message(msg)
            return msg
        except socket.timeout:
            return None

    def close(self) -> None:
        """Close the UDP socket (idempotent)."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass  # non-fatal
            self._sock = None

"""S7 — detection modules: a probe that never ran must not read as a clean result.

Behavioural counterparts to the (b) verdicts of the S7.1 triage
(``docs/internal/error-surfacing-audit-2026-09-15.md`` §6 S7). Each failure is injected as the
exception the real environment raises — a refused or timed-out TCP connection, scapy's
no-Npcap ``RuntimeError`` / not-elevated ``OSError``, ``net use`` exiting non-zero — and the
tests read the result object and the real UI handler, never a hand-built verdict.

  * B1  — ``dns_zone_scanner``: an unreachable AXFR server read as "no zone data — try providing
    a server", and a complete zone from a server that keeps the TCP connection open was
    discarded (the recv loop read to EOF, the timeout skipped the parse).
  * B3  — ``combined_discovery``: ARP sweep / TCP SYN that cannot run vanished from a
    "Found N device(s)" verdict.
  * B4  — ``smb_enumerator``: a failed ``net use`` login was swallowed, so every later ``net``
    command ran as the scanner's own Windows account and was reported as the target's.
  * B4a — ``SMBEnumResult.plain_verdict`` ignored ``not_testable`` and ``_on_smb_result``
    painted an untested host GREEN.

AXFR's port 53 is hard-coded, so these tests script the socket; the live verification matrix
(``docs/spikes/error-surfacing-matrix.py`` rows B1-UNREACH / B1-HOLD) drives a real loopback
server instead.
"""
from __future__ import annotations

import ast
import errno
import logging
import socket
import struct
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QWidget  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RAW_SV = "Det gick inte att ansluta eftersom måldatorn aktivt nekade det"

_widgets: list = []


@pytest.fixture(autouse=True)
def _cleanup(qt_app):
    """RULE-WIN4: deleteLater() + pump, never plain refcount GC."""
    yield
    for w in _widgets:
        try:
            w.deleteLater()
        except RuntimeError:
            pass  # C++ object already destroyed
    _widgets.clear()
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _keep(widget):
    _widgets.append(widget)
    return widget


def _debug_records(caplog, logger: str) -> list:
    return [r for r in caplog.records if r.name == logger and r.levelno == logging.DEBUG]


# ── B1 — DNS zone AXFR ────────────────────────────────────────────────────────

def _name(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"


_SOA = _name("ns1.lab.test") + _name("admin.lab.test") + struct.pack(">IIIII", 1, 3600, 600, 86400, 300)


def _rr(rtype: int, rdata: bytes) -> bytes:
    return _name("lab.test") + struct.pack(">HHIH", rtype, 1, 300, len(rdata)) + rdata


SOA_RR = _rr(6, _SOA)
A_RR = _rr(1, socket.inet_aton("192.0.2.10"))


def _message(*rrs: bytes, rcode: int = 0) -> bytes:
    """One length-prefixed DNS-over-TCP response to an AXFR query for lab.test."""
    body = (struct.pack(">HHHHHH", 1, 0x8400 | rcode, 1, len(rrs), 0, 0)
            + _name("lab.test") + struct.pack(">HH", 252, 1) + b"".join(rrs))
    return struct.pack(">H", len(body)) + body


class _ScriptedSocket:
    """``socket.socket`` stand-in: ``connect()`` may raise; ``recv()`` plays *chunks*, then either
    returns ``b""`` (the server closed) or raises ``socket.timeout`` (it held the connection open)."""

    def __init__(self, chunks=(), *, connect_exc=None, then="close"):
        self._chunks = list(chunks)
        self._connect_exc = connect_exc
        self._then = then
        self.closed = False

    def settimeout(self, _t):
        pass

    def connect(self, _addr):
        if self._connect_exc is not None:
            raise self._connect_exc

    def sendall(self, _msg):
        pass

    def recv(self, _n):
        if self._chunks:
            return self._chunks.pop(0)
        if self._then == "hold":
            raise socket.timeout("timed out")
        return b""

    def close(self):
        self.closed = True


def _axfr_scan(monkeypatch, fake, services=()):
    from modules import dns_zone_scanner as m

    monkeypatch.setattr(m.socket, "socket", lambda *a, **k: fake)
    monkeypatch.setattr(m, "mdns_enumerate", lambda timeout, progress_cb=None: list(services))
    return m.scan(axfr_server="127.0.0.3", axfr_domain="lab.test", mdns_timeout=0.0)


@pytest.mark.parametrize("exc, reason", [
    (ConnectionRefusedError(errno.ECONNREFUSED, RAW_SV), "refused"),
    (socket.timeout("timed out"), "timeout"),
    (TimeoutError(10060, RAW_SV), "timeout"),
    (OSError(errno.EHOSTUNREACH, RAW_SV), "unreachable"),
    (OSError(errno.ENETUNREACH, RAW_SV), "unreachable"),
    (socket.gaierror(11001, RAW_SV), "unreachable"),
    (ConnectionResetError(errno.ECONNRESET, RAW_SV), "failed"),
])
def test_an_axfr_server_that_cannot_be_reached_is_not_reported_as_no_data(monkeypatch, exc, reason):
    result = _axfr_scan(monkeypatch, _ScriptedSocket(connect_exc=exc))

    assert result.verdict.startswith("Could not reach 127.0.0.3 for AXFR"), result.verdict
    assert "Try providing a DNS server" not in result.verdict
    assert result.level == "UNKNOWN"
    assert result.axfr_error == reason
    assert RAW_SV not in result.verdict, "the reason must be fixed text, never str(exc) (RULE-A2)"
    assert result.records == [] and result.axfr_ok is False


def test_an_unreachable_axfr_server_keeps_that_runs_mdns_results(monkeypatch):
    from modules.dns_zone_scanner import MdnsService

    svc = MdnsService(service_type="_ipp._tcp.local", instance="Printer._ipp._tcp.local")
    result = _axfr_scan(monkeypatch, _ScriptedSocket(connect_exc=ConnectionRefusedError()), services=[svc])

    assert result.verdict.startswith("Could not reach 127.0.0.3 for AXFR"), result.verdict
    assert result.services == [svc], "the mDNS results of the same run are real and must stay"


def test_a_complete_zone_from_a_server_that_holds_the_connection_open_is_kept(monkeypatch):
    """RFC 7766 lets a server keep the TCP connection open after the transfer. Reading to EOF
    then timed out, and the timeout skipped the parse: an open zone transfer read as no data."""
    fake = _ScriptedSocket([_message(SOA_RR, A_RR, SOA_RR)], then="hold")
    result = _axfr_scan(monkeypatch, fake)

    assert [r.rtype for r in result.records] == ["SOA", "A"]
    assert result.axfr_ok is True
    assert result.axfr_error == ""
    assert result.verdict.startswith("2 DNS record(s) via AXFR"), result.verdict
    assert fake.closed


def test_a_zone_cut_off_before_its_closing_soa_is_kept_and_called_partial(monkeypatch):
    fake = _ScriptedSocket([_message(SOA_RR, A_RR)], then="hold")
    result = _axfr_scan(monkeypatch, fake)

    assert [r.rtype for r in result.records] == ["SOA", "A"], "records that arrived must be kept"
    assert result.axfr_error == "timeout"
    assert "partial" in result.verdict, result.verdict
    assert not result.verdict.startswith("Could not reach")


def test_a_server_that_answers_refused_and_holds_the_connection_reads_as_refused(monkeypatch):
    """A REFUSED answer is the server's decision, not a failure to reach it — and the AXFR
    button (mDNS off) used to answer it with "Try providing a DNS server for AXFR"."""
    fake = _ScriptedSocket([_message(rcode=5)], then="hold")
    result = _axfr_scan(monkeypatch, fake)

    assert result.verdict.startswith("AXFR refused by 127.0.0.3"), result.verdict
    assert result.axfr_error == ""
    assert result.level == "LOW"


def test_a_zone_that_arrives_in_small_chunks_across_messages_is_reassembled(monkeypatch):
    """Guard for the incremental parse: messages split across recv() calls and a zone spread
    over two messages still yield every record up to the closing SOA."""
    stream = _message(SOA_RR, A_RR) + _message(A_RR, SOA_RR)
    fake = _ScriptedSocket([stream[i:i + 7] for i in range(0, len(stream), 7)], then="hold")
    result = _axfr_scan(monkeypatch, fake)

    assert [r.rtype for r in result.records] == ["SOA", "A", "A"]
    assert result.axfr_error == ""


def test_a_failed_axfr_is_logged_at_debug_with_the_exception(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="modules.dns_zone_scanner")
    _axfr_scan(monkeypatch, _ScriptedSocket(connect_exc=ConnectionRefusedError(errno.ECONNREFUSED, RAW_SV)))

    records = _debug_records(caplog, "modules.dns_zone_scanner")
    assert records and records[0].exc_info is not None


def test_axfr_transfer_returns_the_records_that_arrived_with_the_reason(monkeypatch):
    """``scan()``'s one AXFR call: a cut-off zone comes back as (partial records, reason)."""
    from modules import dns_zone_scanner as m

    monkeypatch.setattr(m.socket, "socket", lambda *a, **k: _ScriptedSocket([_message(SOA_RR, A_RR)], then="hold"))
    records, error = m.axfr_transfer("127.0.0.3", "lab.test", timeout=1.0)

    assert [r.rtype for r in records] == ["SOA", "A"]
    assert error == "timeout"


def _dns_page_signals(result):
    from ui.pages.dns_zone_page import DnsZonePage

    page = _keep(DnsZonePage(parent=None))
    fired: list = []
    page.scan_complete.connect(lambda v: fired.append(("scan_complete", v)))
    page.scan_failed.connect(lambda v: fired.append(("scan_failed", v)))
    signal = getattr(page, "scan_not_testable", None)
    if signal is not None:
        signal.connect(lambda v: fired.append(("scan_not_testable", v)))
    page._on_result(result)
    return fired, page


def test_the_dns_zone_page_reports_an_unreachable_axfr_as_not_testable():
    from modules.dns_zone_scanner import DnsZoneResult

    result = DnsZoneResult(verdict="Could not reach 127.0.0.3 for AXFR — x.", level="UNKNOWN")
    result.axfr_error = "refused"
    fired, page = _dns_page_signals(result)

    assert [k for k, _v in fired] == ["scan_not_testable"], fired
    assert page._status_lbl.text() == result.verdict


def test_the_dns_zone_page_reports_a_partial_zone_as_complete():
    from modules.dns_zone_scanner import DnsRecord, DnsZoneResult

    result = DnsZoneResult(records=[DnsRecord("lab.test", "SOA", "ns1 admin", 300)],
                           verdict="1 DNS record(s) via AXFR … partial", axfr_ok=True)
    result.axfr_error = "timeout"
    fired, _page = _dns_page_signals(result)

    assert [k for k, _v in fired] == ["scan_complete"], "the records are real — registry stays fresh"


def test_the_dashboard_maps_dns_zone_not_testable_onto_the_registry():
    """The page's new signal reaches ``_nav_set_scan_state(L.DNS_ZONE_MAP, "not_testable")``."""
    from ui.nav.labels import NavLabel as L
    from ui.tabs import TabBuilderMixin

    states: list = []

    class _Host:
        def _nav_set_scan_state(self, label, state, **kw):
            states.append((label, state, kw.get("error")))

    TabBuilderMixin._on_dns_zone_not_testable(_Host(), "Could not reach 127.0.0.3 for AXFR — x.")
    assert states == [(L.DNS_ZONE_MAP, "not_testable", "Could not reach 127.0.0.3 for AXFR — x.")]

    tree = ast.parse((REPO / "ui" / "tabs.py").read_text(encoding="utf-8"))
    wired = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
        and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "scan_not_testable"
        and any(isinstance(a, ast.Attribute) and a.attr == "_on_dns_zone_not_testable" for a in n.args)
    ]
    assert wired, "DnsZonePage.scan_not_testable is not connected to _on_dns_zone_not_testable"


# ── B3 — Full Device Discovery ────────────────────────────────────────────────

_NO_NPCAP = ("Sniffing and sending packets is not available at layer 2: winpcap is not installed. "
             "You may use conf.L3socket or conf.L3socket6 to access layer 3")
_NOT_ELEVATED = "Windows native L3 Raw sockets are only usable as administrator ! Please install Npcap to workaround !"


def _discover(monkeypatch, *, cache, srp_exc=None, sr_exc_for=lambda ip: None):
    """The real ``discover()`` with scapy's ``srp``/``sr`` raising what a box without Npcap raises.

    The ARP cache, ICMP and mDNS methods are stubbed so the test stays offline; the ARP sweep
    and the TCP SYN sweep are the real functions."""
    from modules import combined_discovery as m
    from modules.combined_discovery import DiscoveredDevice

    def _srp(*_a, **_k):
        if srp_exc is not None:
            raise srp_exc
        return [], []

    def _sr(pkt, *_a, **_k):
        exc = sr_exc_for(pkt.dst)
        if exc is not None:
            raise exc
        return [], []

    monkeypatch.setattr(m, "SCAPY_AVAILABLE", True)
    monkeypatch.setattr(m, "srp", _srp)
    monkeypatch.setattr(m, "sr", _sr)
    monkeypatch.setattr(m, "_arp_cache_scan", lambda: {
        ip: DiscoveredDevice(ip=ip, discovery_methods=["arp-cache"]) for ip in cache
    })
    monkeypatch.setattr(m, "_icmp_sweep", lambda hosts, timeout: {})
    monkeypatch.setattr(m, "_mdns_query", lambda timeout: {})
    return m.discover(cidr="192.168.250.0/29", resolve_hostnames=False, timeout=0.01)


def test_discovery_names_the_methods_that_could_not_run(monkeypatch):
    res = _discover(monkeypatch, cache=["192.168.250.1"],
                    srp_exc=RuntimeError(_NO_NPCAP), sr_exc_for=lambda ip: OSError(_NOT_ELEVATED))

    assert "ARP sweep and TCP SYN could not run" in res.plain_verdict, res.plain_verdict
    assert getattr(res, "methods_failed", None) == ["arp-sweep", "tcp-syn"]
    assert res.not_testable is False, "devices were still found — the result is real, just partial"
    assert res.count == 1
    assert _NO_NPCAP not in res.plain_verdict and _NOT_ELEVATED not in res.plain_verdict


def test_discovery_with_no_devices_also_names_the_methods_that_could_not_run(monkeypatch):
    res = _discover(monkeypatch, cache=[],
                    srp_exc=RuntimeError(_NO_NPCAP), sr_exc_for=lambda ip: OSError(_NOT_ELEVATED))

    assert res.not_testable is True
    assert "could not run" in res.plain_verdict, res.plain_verdict


def test_a_syn_probe_that_fails_for_some_hosts_only_is_not_a_failed_method(monkeypatch):
    res = _discover(monkeypatch, cache=["192.168.250.1"],
                    sr_exc_for=lambda ip: OSError("transient") if ip.endswith(".3") else None)

    assert "tcp-syn" not in (getattr(res, "methods_failed", None) or [])
    assert "could not run" not in res.plain_verdict


def test_a_method_that_could_not_run_is_logged_at_debug_with_the_exception(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="modules.combined_discovery")
    _discover(monkeypatch, cache=["192.168.250.1"],
              srp_exc=RuntimeError(_NO_NPCAP), sr_exc_for=lambda ip: OSError(_NOT_ELEVATED))

    records = _debug_records(caplog, "modules.combined_discovery")
    assert len(records) >= 2 and all(r.exc_info is not None for r in records)


def _enrichment_host(**widgets):
    from ui.scan_enrichment import ScanEnrichmentMixin

    class _Host(ScanEnrichmentMixin, QWidget):
        pass

    host = _keep(_Host())
    for name, widget in widgets.items():
        widget.setParent(host)
        setattr(host, name, widget)
    host.states = []
    host._nav_set_scan_state = lambda label, state, **kw: host.states.append((label, state))
    return host


def test_the_discovery_page_shows_the_failed_methods_and_stays_fresh():
    from modules.combined_discovery import DiscoveredDevice, DiscoveryResult
    from ui.nav.labels import NavLabel as L

    res = DiscoveryResult(devices=[DiscoveredDevice(ip="192.168.250.1", discovery_methods=["arp-cache"])],
                          cidr="192.168.250.0/29", methods_used=["arp-cache"],
                          methods_failed=["arp-sweep", "tcp-syn"])
    host = _enrichment_host(_disc_status=QLabel(), _recon_disc_table=QTableWidget(0, 5))
    host._on_discovery_result(res)

    assert "could not run" in host._disc_status.text()
    assert host.states == [(L.FULL_DEVICE_DISCOVERY, "fresh")]


# ── B4 / B4a — SMB enumeration ────────────────────────────────────────────────

_NET_VIEW = (
    "Shared resources at \\\\192.0.2.20\n\n"
    "Share name  Type  Used as  Comment\n\n"
    "-------------------------------------------------------------------------------\n"
    "Public      Disk\n"
    "The command completed successfully.\n\n"
)
_PASSWORD = "s3cret-Pa55"


def _smb_enum(monkeypatch, net_use_exc):
    from modules import smb_enumerator as m
    from modules.smb_enumerator import NetBIOSInfo

    calls: list = []

    def _check_output(cmd, **_kw):
        calls.append([c for c in cmd if c != _PASSWORD])
        if cmd[:2] == ["net", "use"] and "/delete" not in cmd:
            if net_use_exc is None:
                return "The command completed successfully.\n"
            raise net_use_exc
        if cmd[:2] == ["net", "view"]:
            return _NET_VIEW
        if cmd[:2] == ["net", "localgroup"]:
            return "----\n*Administrators\nThe command completed successfully.\n"
        return ""

    monkeypatch.setattr(m, "IMPACKET_AVAILABLE", False)
    monkeypatch.setattr(m.platform, "system", lambda: "Windows")
    monkeypatch.setattr(m.subprocess, "check_output", _check_output)
    monkeypatch.setattr(m, "_netbios_name_query", lambda host, timeout: NetBIOSInfo(machine_name="NAS01", workgroup="LAB"))
    monkeypatch.setattr(m, "_smb_anonymous_banner", lambda host, timeout: ("SMB2 dialect 0x0210", False))
    res = m.enumerate_smb("192.0.2.20", username="auditor", password=_PASSWORD, timeout=1.0)
    return res, calls


def test_a_failed_net_use_login_marks_the_result_not_testable(monkeypatch):
    res, calls = _smb_enum(monkeypatch, subprocess.CalledProcessError(2, ["net", "use"], output="Systemfel 1326"))

    assert res.not_testable is True
    assert "exit code 2" in res.not_testable_reason
    assert "Systemfel" not in res.not_testable_reason, "key on the exit code, never net.exe's text (RULE-WIN23)"
    assert res.shares == [] and res.local_groups == [], "nothing may be read as the scanner's own account"
    assert [c[:2] for c in calls] == [["net", "use"]], f"net commands ran after the failed login: {calls}"


def test_a_failed_net_use_login_keeps_the_tier_1_data(monkeypatch):
    res, _calls = _smb_enum(monkeypatch, subprocess.CalledProcessError(2, ["net", "use"]))

    assert res.netbios.machine_name == "NAS01"
    assert res.os_version == "SMB2 dialect 0x0210"


@pytest.mark.parametrize("exc", [
    subprocess.TimeoutExpired(["net", "use"], 20),
    FileNotFoundError(2, "net"),
])
def test_a_net_use_that_cannot_run_marks_the_result_not_testable(monkeypatch, exc):
    res, _calls = _smb_enum(monkeypatch, exc)

    assert res.not_testable is True
    assert res.not_testable_reason


def test_a_successful_net_use_still_enumerates(monkeypatch):
    """Guard: the fix stops enumeration only when the login fails."""
    res, calls = _smb_enum(monkeypatch, None)

    assert res.not_testable is False
    assert [s.name for s in res.shares] == ["Public"]
    assert ["net", "localgroup"] in [c[:2] for c in calls]


def test_the_failed_login_is_logged_at_debug_without_the_password(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="modules.smb_enumerator")
    exc = subprocess.CalledProcessError(2, ["net", "use", "\\\\192.0.2.20\\IPC$", _PASSWORD, "/user:auditor"])
    _smb_enum(monkeypatch, exc)

    records = _debug_records(caplog, "modules.smb_enumerator")
    assert records and records[0].exc_info is not None
    formatted = "\n".join(logging.Formatter("%(message)s").format(r) for r in records)
    assert _PASSWORD not in formatted


def test_an_smb_host_that_could_not_be_tested_says_so():
    from modules.smb_enumerator import SMBEnumResult

    res = SMBEnumResult(host="192.0.2.1", not_testable=True, not_testable_reason="SMB could not be reached.")

    assert "Could not test 192.0.2.1" in res.plain_verdict, res.plain_verdict
    assert "SMB could not be reached." in res.plain_verdict


def test_the_smb_page_does_not_paint_an_untested_host_green():
    from modules.smb_enumerator import SMBEnumResult
    from ui import styles as _s
    from ui.nav.labels import NavLabel as L

    res = SMBEnumResult(host="192.0.2.1", not_testable=True, not_testable_reason="SMB could not be reached.")
    host = _enrichment_host(_smb_verdict=QLabel(), _smb_status=QLabel(),
                            _recon_smb_shares_table=QTableWidget(0, 4), _recon_smb_users_table=QTableWidget(0, 4))
    host._on_smb_result(res)
    sheet = host._smb_verdict.styleSheet()

    assert f"color:{_s.GREEN}" not in sheet
    assert f"color:{_s.VIOLET}" in sheet
    assert "Could not test" in host._smb_verdict.text()
    assert host.states == [(L.WINDOWS_SHARES_SMB, "not_testable")]

"""Locale-independent parsing of Windows console output (RULE-WIN23).

Windows translates the *labels* in `ping`, `ipconfig`, `netsh` and `net` output,
but not their structure: `ms`, `%`, `=`, `<`, `TTL=` and the `SSID N :` block
headers stay English on every locale. Parsers that match translated labels return
empty or default values on a Swedish or Spanish install — and because every call
site swallows the miss with `except Exception`, the failure is completely silent.
It produces no telemetry, which is why it survived undetected.

The sharpest case is ICMP: `IcmpProbeResult` defaults to `loss_pct=100.0`, and the
reset guard was `elif result.avg_ms >= 0`. When the English-only summary regex
missed, `avg_ms` stayed `-1.0`, so the guard never fired and every reachable host
was reported as **100% packet loss with no error message** — indistinguishable
from a total network outage.
"""
from __future__ import annotations

import pytest

from modules.service_diagnostics_probes import IcmpProbeResult, _parse_ping_output

# ── Real `ping -n 2` output, three locales ───────────────────────────────────

_PING_EN = """
Pinging 192.168.1.1 with 32 bytes of data:
Reply from 192.168.1.1: bytes=32 time=3ms TTL=64
Reply from 192.168.1.1: bytes=32 time=5ms TTL=64

Ping statistics for 192.168.1.1:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 3ms, Maximum = 5ms, Average = 4ms
"""

_PING_SV = """
Ping skickas till 192.168.1.1 med 32 byte data:
Svar fran 192.168.1.1: byte=32 tid=3ms TTL=64
Svar fran 192.168.1.1: byte=32 tid=5ms TTL=64

Ping-statistik for 192.168.1.1:
    Paket: Skickade = 2, Mottagna = 2, Forlorade = 0 (0% forlust),
Ungefarlig overforingstid i millisekunder:
    Kortast = 3ms, Langst = 5ms, Medel = 4ms
"""

_PING_ES = """
Haciendo ping a 192.168.1.1 con 32 bytes de datos:
Respuesta desde 192.168.1.1: bytes=32 tiempo=3ms TTL=64
Respuesta desde 192.168.1.1: bytes=32 tiempo=5ms TTL=64

Estadisticas de ping para 192.168.1.1:
    Paquetes: enviados = 2, recibidos = 2, perdidos = 0 (0% perdidos),
Tiempos aproximados de ida y vuelta en milisegundos:
    Minimo = 3ms, Maximo = 5ms, Media = 4ms
"""

_PING_SV_TOTAL_LOSS = """
Ping skickas till 10.0.0.9 med 32 byte data:
Begaran overskred tidsgransen.
Begaran overskred tidsgransen.

Ping-statistik for 10.0.0.9:
    Paket: Skickade = 2, Mottagna = 0, Forlorade = 2 (100% forlust),
"""


@pytest.mark.parametrize("output,locale", [
    (_PING_EN, "en"), (_PING_SV, "sv"), (_PING_ES, "es"),
])
def test_reachable_host_is_never_reported_as_total_loss(output, locale):
    """A reachable host must read 0% loss on every locale, not 100%."""
    result = IcmpProbeResult(host="192.168.1.1")
    _parse_ping_output(output, result, "Windows")
    assert result.loss_pct == 0.0, (
        f"{locale}: a host that answered every ping was reported as "
        f"{result.loss_pct}% loss — this reads as a total outage in Service Diagnostics"
    )


@pytest.mark.parametrize("output,locale", [
    (_PING_EN, "en"), (_PING_SV, "sv"), (_PING_ES, "es"),
])
def test_rtt_is_extracted_on_every_locale(output, locale):
    """`ms` and `=`/`<` are untranslated, so RTT is always recoverable."""
    result = IcmpProbeResult(host="192.168.1.1")
    _parse_ping_output(output, result, "Windows")
    assert result.min_ms == 3.0, f"{locale}: min"
    assert result.max_ms == 5.0, f"{locale}: max"
    assert result.avg_ms == 4.0, f"{locale}: avg"
    assert result.jitter_ms == 2.0, f"{locale}: jitter"


def test_genuine_total_loss_is_still_reported_as_total_loss():
    """The fix must not turn a real outage into a false clean result."""
    result = IcmpProbeResult(host="10.0.0.9")
    _parse_ping_output(_PING_SV_TOTAL_LOSS, result, "Windows")
    assert result.loss_pct == 100.0
    assert result.avg_ms < 0, "no replies means no RTT to report"


def test_partial_loss_is_read_from_the_untranslated_percentage():
    output = _PING_SV.replace("(0% forlust)", "(50% forlust)")
    result = IcmpProbeResult(host="192.168.1.1")
    _parse_ping_output(output, result, "Windows")
    assert result.loss_pct == 50.0


def test_sub_millisecond_reply_is_counted_as_a_reply():
    """`time<1ms` / `tid<1ms` uses `<`, not `=` — it is still a successful reply."""
    output = _PING_SV.replace("tid=3ms", "tid<1ms").replace("tid=5ms", "tid<1ms")
    result = IcmpProbeResult(host="192.168.1.1")
    _parse_ping_output(output, result, "Windows")
    assert result.loss_pct == 0.0
    assert result.avg_ms >= 0


# ── icmp_ping (modules/utils_net) — same defect, different consumer ──────────

def _run_icmp_ping(monkeypatch, stdout: str) -> float:
    """Drive the real icmp_ping() with canned Windows ping output.

    ``fake_windows`` (conftest) supplies ``platform.system()`` *and* the Windows-only
    subprocess constants the Windows branch dereferences — without the latter this
    raises AttributeError on Linux/macOS, which is how it broke the v2.2.8 release CI.
    """
    import subprocess

    import modules.utils_net as un

    class _R:
        def __init__(self, out):
            self.stdout = out
            self.returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R(stdout))
    return un.icmp_ping("192.168.1.1")


@pytest.mark.parametrize("output,locale", [
    (_PING_EN, "en"), (_PING_SV, "sv"), (_PING_ES, "es"),
])
def test_icmp_ping_returns_rtt_on_every_locale(monkeypatch, fake_windows, output, locale):
    """-1.0 means 'unreachable' to every caller; a reachable host must never get it."""
    rtt = _run_icmp_ping(monkeypatch, output)
    assert rtt == 3.0, f"{locale}: reachable host reported rtt={rtt}"


def test_icmp_ping_keeps_the_sub_millisecond_contract(monkeypatch, fake_windows):
    """"tid<1ms" must yield 1.0, matching the long-standing en-US behaviour.

    The original code had a 0.5 branch for this case, but it sat after a regex
    that already matched "<", so it was unreachable — 1.0 is what has always
    shipped, and tests/test_utils_net.py pins it. Locale-independence must not
    quietly change the value.
    """
    out = _PING_SV.replace("tid=3ms", "tid<1ms").replace("tid=5ms", "tid<1ms")
    assert _run_icmp_ping(monkeypatch, out) == 1.0


def test_icmp_ping_still_reports_unreachable_for_a_real_timeout(monkeypatch, fake_windows):
    assert _run_icmp_ping(monkeypatch, _PING_SV_TOTAL_LOSS) == -1.0


# ── netsh wlan show networks (modules/wifi_scanner) ──────────────────────────

_WLAN_EN = """
Interface name : Wi-Fi
There are 1 networks currently visible.

SSID 1 : HomeNet
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 72%
         Radio type         : 802.11n
         Channel            : 6
"""

_WLAN_ES = """
Nombre de la interfaz : Wi-Fi
Hay 1 redes visibles actualmente.

SSID 1 : HomeNet
    Tipo de red             : Infraestructura
    Autenticacion           : WPA2-Personal
    Cifrado                 : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Senal              : 72%
         Tipo de radio      : 802.11n
         Canal              : 6
"""


@pytest.mark.parametrize("raw,locale", [(_WLAN_EN, "en"), (_WLAN_ES, "es")])
def test_wifi_channel_and_signal_survive_localization(monkeypatch, fake_windows, raw, locale):
    """channel=0 + fallback 50% silently disables co-channel interference detection."""
    import subprocess

    import modules.wifi_scanner as ws

    monkeypatch.setattr(subprocess, "check_output", lambda *a, **k: raw)
    nets, _my_ssid, _my_ch = ws._scan_windows()
    assert len(nets) == 1, f"{locale}: expected one network, got {len(nets)}"
    net = nets[0]
    assert net.ssid == "HomeNet"
    assert net.channel == 6, f"{locale}: channel not parsed (co-channel detection dies)"
    # 72% -> int(72/2) - 100 = -64 dBm
    assert net.signal_dbm == -64, f"{locale}: signal fell back to the 50% default"


# ── net view share table (modules/smb_enumerator) ────────────────────────────

_NET_VIEW_EN = """Shared resources at \\SERVER

Share name  Type   Used as  Comment

-------------------------------------------------------------------------------
ADMIN$      Disk            Remote Admin
C$          Disk            Default share
Public      Disk            Team files
The command completed successfully.
"""

_NET_VIEW_ES = """Recursos compartidos en \\SERVER

Nombre de recurso  Tipo   Usado como  Comentario

-------------------------------------------------------------------------------
ADMIN$      Disco           Admin remota
C$          Disco           Recurso predeterminado
Public      Disco           Archivos del equipo
Se ha completado el comando correctamente.
"""


@pytest.mark.parametrize("raw,locale", [(_NET_VIEW_EN, "en"), (_NET_VIEW_ES, "es")])
def test_net_view_shares_parse_on_every_locale(raw, locale):
    """Requiring the English "Disk" token returned zero shares outside en-US."""
    from modules.smb_enumerator import _parse_net_view

    rows = _parse_net_view(raw)
    names = [r[0] for r in rows]
    assert names == ["ADMIN$", "C$", "Public"], f"{locale}: got {names}"


def test_net_view_ignores_the_header_and_trailing_status_line():
    from modules.smb_enumerator import _parse_net_view

    rows = _parse_net_view(_NET_VIEW_EN)
    assert all(not r[0].startswith("-") for r in rows)
    assert "The" not in [r[0] for r in rows], "trailing status line leaked in as a share"


# ── netsh interface ipv6 show addresses (modules/utils_platform) ─────────────

def test_ipv6_interface_header_is_matched_by_shape_not_by_word():
    """"Interface" is "Interfaz"/"Gränssnitt"; the "<word> <n>:" shape is not."""
    import re
    pattern = re.compile(r"^\s*\S+\s+\d+:\s+(.+)$")
    for line, locale in [
        ("Interface 12: Ethernet", "en"),
        ("Interfaz 12: Ethernet", "es"),
        ("Granssnitt 12: Ethernet", "sv"),
    ]:
        m = pattern.search(line)
        assert m is not None, f"{locale}: interface header not matched"
        assert m.group(1).strip() == "Ethernet"


# ── netsh wlan show hostednetwork — connected stations (RULE-WIN23) ───────────
# The station rows were gated behind `"Number of clients" in line or "Stations" in line`,
# both English, so the connected-client list came back EMPTY on every localized Windows.
# The structure is untranslated: a station row's first token IS the MAC, while the hosted
# network's own BSSID sits after a `label :` separator — so matching at start-of-line
# separates them without reading a single word.

_HOSTED_EN = """
Hosted network status
---------------------
    Status                 : Started
    BSSID                  : 02:1a:2b:3c:4d:5e
    Radio type             : 802.11n
    Channel                : 11
    Number of clients      : 2

         aa:bb:cc:dd:ee:01     Authenticated
         aa:bb:cc:dd:ee:02     Authenticated
"""

_HOSTED_SV = """
Status för värdbaserat nätverk
------------------------------------
    Status                 : Startad
    BSSID                  : 02:1a:2b:3c:4d:5e
    Radiotyp               : 802.11n
    Kanal                  : 11
    Antal klienter         : 2

         aa:bb:cc:dd:ee:01     Autentiserad
         aa:bb:cc:dd:ee:02     Autentiserad
"""

_HOSTED_HI = """
होस्ट नेटवर्क
------------------------------------
    स्थिति            : प्रारंभ
    BSSID                  : 02:1a:2b:3c:4d:5e
    चैनल                 : 11
    क्लाइंट की संख्या   : 2

         aa:bb:cc:dd:ee:01     प्रमाणित
         aa:bb:cc:dd:ee:02     प्रमाणित
"""


@pytest.mark.parametrize("raw,locale", [
    (_HOSTED_EN, "en-US"),
    (_HOSTED_SV, "sv-SE"),
    (_HOSTED_HI, "hi-IN"),
], ids=["en-US", "sv-SE", "hi-IN"])
def test_hosted_network_clients_are_found_on_every_locale(
    monkeypatch, fake_windows, raw, locale
):
    """Both station MACs must be found regardless of the label language."""
    import modules.wifi_scanner as ws

    monkeypatch.setattr(ws.subprocess, "check_output", lambda *a, **k: raw)
    monkeypatch.setattr(ws, "get_arp_snapshot", lambda: {}, raising=False)

    clients = ws._get_connected_clients()
    macs = sorted(c.mac for c in clients)

    assert macs == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"], (
        f"{locale}: station list came back as {macs!r}"
    )


def test_the_hosted_network_own_bssid_is_not_reported_as_a_client(
    monkeypatch, fake_windows
):
    """The AP's own BSSID must never appear in the client list.

    This is the failure mode a naive "grab every MAC-shaped token" fix would introduce,
    so it is pinned separately: the BSSID line has a label before the value, a station
    row does not.
    """
    import modules.wifi_scanner as ws

    monkeypatch.setattr(ws.subprocess, "check_output", lambda *a, **k: _HOSTED_SV)
    monkeypatch.setattr(ws, "get_arp_snapshot", lambda: {}, raising=False)

    macs = {c.mac for c in ws._get_connected_clients()}
    assert "02:1a:2b:3c:4d:5e" not in macs

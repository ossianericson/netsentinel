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


# ── netsh interface ipv6 show neighbors — the rogue-router flag (RULE-WIN23) ──
# `_get_ipv6_routers()` gated on the English word "Router", so on any localized Windows
# the router set came back EMPTY and the rogue-IPv6-router check reported CLEAN
# unconditionally — a security check that always passes. The structure is untranslated:
# the router flag is the only PARENTHESISED annotation in the table, and it always
# follows a MAC in the physical-address column.

_NBR_EN = """
Interface 13: WiFi


Internet Address                              Physical Address   Type
--------------------------------------------  -----------------  -----------
fe80::92:656c:3602:a02f                       b8-7b-d4-ef-62-02  Stale
fe80::3e64:cfff:fee0:261c                     3c-64-cf-e0-26-1c  Stale (Router)
fe80::6283:e7ff:fe88:a0b1                     60-83-e7-88-a0-b1  Reachable (Router)
ff02::1                                       33-33-00-00-00-01  Permanent
"""

_NBR_FR = """
Interface 13: Wi-Fi


Adresse Internet                              Adresse physique   Type
--------------------------------------------  -----------------  -----------
fe80::92:656c:3602:a02f                       b8-7b-d4-ef-62-02  Périmé
fe80::3e64:cfff:fee0:261c                     3c-64-cf-e0-26-1c  Périmé (Routeur)
fe80::6283:e7ff:fe88:a0b1                     60-83-e7-88-a0-b1  Accessible (Routeur)
ff02::1                                       33-33-00-00-00-01  Permanent
"""

# German is the case that hid this defect from an English-only reader: "Router" is
# also the German word, so this fixture passed even before the fix.
_NBR_DE = """
Schnittstelle 13: WLAN


Internetadresse                               Physische Adresse  Typ
--------------------------------------------  -----------------  -----------
fe80::92:656c:3602:a02f                       b8-7b-d4-ef-62-02  Veraltet
fe80::3e64:cfff:fee0:261c                     3c-64-cf-e0-26-1c  Veraltet (Router)
fe80::6283:e7ff:fe88:a0b1                     60-83-e7-88-a0-b1  Erreichbar (Router)
ff02::1                                       33-33-00-00-00-01  Permanent
"""

_NBR_RU = """
Интерфейс 13: Беспроводная сеть


Адрес в Интернете                             Физический адрес   Тип
--------------------------------------------  -----------------  -----------
fe80::92:656c:3602:a02f                       b8-7b-d4-ef-62-02  Устаревший
fe80::3e64:cfff:fee0:261c                     3c-64-cf-e0-26-1c  Устаревший (Маршрутизатор)
fe80::6283:e7ff:fe88:a0b1                     60-83-e7-88-a0-b1  Достижимый (Маршрутизатор)
ff02::1                                       33-33-00-00-00-01  Постоянный
"""

# zh-CN also localizes the PUNCTUATION — full-width brackets, not ASCII ones.
_NBR_ZH = """
接口 13: WLAN


Internet 地址                                 物理地址           类型
--------------------------------------------  -----------------  -----------
fe80::92:656c:3602:a02f                       b8-7b-d4-ef-62-02  过时
fe80::3e64:cfff:fee0:261c                     3c-64-cf-e0-26-1c  过时（路由器）
fe80::6283:e7ff:fe88:a0b1                     60-83-e7-88-a0-b1  可达（路由器）
ff02::1                                       33-33-00-00-00-01  永久
"""


@pytest.mark.parametrize("raw,locale", [
    (_NBR_EN, "en-US"),
    (_NBR_FR, "fr-FR"),
    (_NBR_DE, "de-DE"),
    (_NBR_RU, "ru-RU"),
    (_NBR_ZH, "zh-CN"),
], ids=["en-US", "fr-FR", "de-DE", "ru-RU", "zh-CN"])
def test_ipv6_routers_are_found_on_every_locale(monkeypatch, fake_windows, raw, locale):
    """An empty router set makes the rogue-router check silently report CLEAN."""
    import modules.rogue_device as rd

    monkeypatch.setattr(rd.subprocess, "check_output", lambda *a, **k: raw)

    routers = rd._get_ipv6_routers()
    assert routers == {"3c:64:cf:e0:26:1c", "60:83:e7:88:a0:b1"}, (
        f"{locale}: router set came back as {sorted(routers)!r} — an empty or short "
        f"set means the rogue-IPv6-router check passes unconditionally"
    )


@pytest.mark.parametrize("raw,locale", [
    (_NBR_EN, "en-US"), (_NBR_RU, "ru-RU"), (_NBR_ZH, "zh-CN"),
], ids=["en-US", "ru-RU", "zh-CN"])
def test_a_neighbour_without_the_router_flag_is_never_reported_as_a_router(
    monkeypatch, fake_windows, raw, locale
):
    """The failure mode a loose structural matcher would introduce: a false HIGH.

    ``scan()`` promotes a matching MAC to ``risk_level="HIGH"`` with a "ROGUE ROUTER
    DETECTED" verdict, so over-matching the header row or a plain Stale entry puts a
    fabricated critical finding in a security report.
    """
    import modules.rogue_device as rd

    monkeypatch.setattr(rd.subprocess, "check_output", lambda *a, **k: raw)

    routers = rd._get_ipv6_routers()
    assert "b8:7b:d4:ef:62:02" not in routers, f"{locale}: plain neighbour flagged"
    assert "33:33:00:00:00:01" not in routers, f"{locale}: multicast entry flagged"


def test_the_neighbour_table_header_and_rule_lines_are_not_matched(
    monkeypatch, fake_windows
):
    """Header/separator rows carry no MAC, so a MAC-anchored matcher cannot see them."""
    import modules.rogue_device as rd

    monkeypatch.setattr(
        rd.subprocess, "check_output",
        lambda *a, **k: _NBR_EN.replace("Type", "Type (Router)"),
    )
    assert rd._get_ipv6_routers() == {"3c:64:cf:e0:26:1c", "60:83:e7:88:a0:b1"}


# ── netsh wlan show interfaces / show networks — channel (RULE-WIN23) ─────────
# Two defects in one file, both silently disabling co-channel interference analysis:
#
#  * `show interfaces` matched the English label "Channel", so `my_channel` stayed 0
#    on every localized Windows and every AP was compared against channel 0.
#  * `show networks mode=bssid` matched the bare-integer field SHAPE but paired the
#    matches to BSSIDs by list index — and Windows 11 emits "QoS MSCS Supported : 0"
#    and "QoS Map Supported : 0" inside each BSSID section, which share that shape.
#    Three matches per BSSID against one BSSID per index mis-assigns from the second
#    radio onward. Measured on a real en-US machine: 7 of 10 BSSIDs read channel 0.

_IFACE_EN = """
There is 1 interface on the system:

    Name                   : WiFi
    Description            : Realtek 8852BE Wireless LAN WiFi 6 PCI-E NIC
    GUID                   : b944999c-e7b2-43bb-8074-01bba5527af1
    Physical address       : 1c:ce:51:98:dd:1c
    Interface type         : Primary
    State                  : connected
    SSID                   : HomeNet
    AP BSSID               : aa:bb:cc:dd:ee:01
    Band                   : 5 GHz
    Channel                : 36
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto Connect
    Receive rate (Mbps)    : 1201
    Transmit rate (Mbps)   : 1201
    Signal                 : 100%
    Rssi                   : -59
    Profile                : HomeNet
    QoS MSCS Configured         : 0
    QoS Map Configured          : 0
"""

_IFACE_DE = """
Es ist 1 Schnittstelle im System vorhanden:

    Name                   : WLAN
    Beschreibung           : Realtek 8852BE Wireless LAN WiFi 6 PCI-E NIC
    GUID                   : b944999c-e7b2-43bb-8074-01bba5527af1
    Physische Adresse      : 1c:ce:51:98:dd:1c
    Schnittstellentyp      : Primär
    Status                 : Verbunden
    SSID                   : HomeNet
    AP-BSSID               : aa:bb:cc:dd:ee:01
    Band                   : 5 GHz
    Kanal                  : 36
    Netzwerktyp            : Infrastruktur
    Funktyp                : 802.11ax
    Authentifizierung      : WPA2-Personal
    Verschlüsselung        : CCMP
    Verbindungsmodus       : Automatisch verbinden
    Empfangsrate (MBit/s)  : 1201
    Übertragungsrate       : 1201
    Signal                 : 100%
    Profil                 : HomeNet
    QoS MSCS konfiguriert       : 0
    QoS Map konfiguriert        : 0
"""

_IFACE_RU = """
В системе есть 1 интерфейс:

    Имя                    : Беспроводная сеть
    Физический адрес       : 1c:ce:51:98:dd:1c
    Состояние              : подключено
    SSID                   : HomeNet
    BSSID точки доступа    : aa:bb:cc:dd:ee:01
    Диапазон               : 5 ГГц
    Канал                  : 36
    Тип сети               : Инфраструктура
    Проверка подлинности   : WPA2-Personal
    Скорость приема (Мбит/с) : 1201
    Сигнал                 : 100%
    QoS MSCS настроен           : 0
"""

_IFACE_ZH = """
系统上有 1 个接口:

    名称                   : WLAN
    物理地址               : 1c:ce:51:98:dd:1c
    状态                   : 已连接
    SSID                   : HomeNet
    AP BSSID               : aa:bb:cc:dd:ee:01
    频段                   : 5 GHz
    通道                   : 36
    网络类型               : 基础结构
    身份验证               : WPA2-Personal
    接收速率(Mbps)          : 1201
    信号                   : 100%
    QoS MSCS 已配置          : 0
"""

# Windows 11's real per-BSSID shape: a QoS pair inside every section, plus the
# multi-value "Basic rates" line the bare-integer matcher must also leave alone.
_NETWORKS_W11_EN = """
Interface name : WiFi
There are 1 networks currently visible.

SSID 1 : HomeNet
    Network type            : Infrastructure
    Authentication          : WPA2-Personal
    Encryption              : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 100%
         Radio type         : 802.11ax
         Band               : 5 GHz
         Channel            : 36
         QoS MSCS Supported    : 0
         QoS Map Supported     : 0
         Basic rates (Mbps) : 6 12 24
         Other rates (Mbps) : 9 18 36 48 54
    BSSID 2                 : aa:bb:cc:dd:ee:02
         Signal             : 40%
         Radio type         : 802.11n
         Band               : 2.4 GHz
         Channel            : 11
         QoS MSCS Supported    : 0
         QoS Map Supported     : 0
    BSSID 3                 : aa:bb:cc:dd:ee:03
         Signal             : 70%
         Radio type         : 802.11n
         Band               : 2.4 GHz
         Channel            : 6
         QoS MSCS Supported    : 0
         QoS Map Supported     : 0
"""

_NETWORKS_W11_RU = (
    _NETWORKS_W11_EN
    .replace("Network type", "Тип сети")
    .replace("Authentication", "Проверка подлинности")
    .replace("Encryption", "Шифрование")
    .replace("Signal", "Сигнал")
    .replace("Radio type", "Тип радио")
    .replace("Channel", "Канал")
    .replace("Basic rates", "Основные скорости")
    .replace("Other rates", "Другие скорости")
)


def _drive_scan_windows(monkeypatch, networks_raw: str, iface_raw: str):
    """Run the real _scan_windows() with a different blob per netsh subcommand."""
    import modules.wifi_scanner as ws

    def _fake(cmd, *a, **k):
        return iface_raw if "interfaces" in cmd else networks_raw

    monkeypatch.setattr(ws.subprocess, "check_output", _fake)
    return ws._scan_windows()


@pytest.mark.parametrize("iface,locale", [
    (_IFACE_EN, "en-US"),
    (_IFACE_DE, "de-DE"),
    (_IFACE_RU, "ru-RU"),
    (_IFACE_ZH, "zh-CN"),
], ids=["en-US", "de-DE", "ru-RU", "zh-CN"])
def test_my_channel_survives_localization(monkeypatch, fake_windows, iface, locale):
    """my_channel=0 makes co-channel analysis compare every AP against channel 0."""
    _nets, my_ssid, my_channel = _drive_scan_windows(
        monkeypatch, _NETWORKS_W11_EN, iface
    )
    assert my_ssid == "HomeNet", f"{locale}: SSID"
    assert my_channel == 36, f"{locale}: my_channel came back as {my_channel}"


def test_my_channel_is_never_taken_from_a_rate_or_qos_field(monkeypatch, fake_windows):
    """"<label> : <bare integer>" is not a unique shape in `show interfaces`.

    Receive/transmit rate and the QoS pair share it, so a structural matcher must
    reject implausible channel numbers as well as take the first match.
    """
    without_channel = _IFACE_EN.replace("    Channel                : 36\n", "")
    assert "Channel" not in without_channel

    _nets, _ssid, my_channel = _drive_scan_windows(
        monkeypatch, _NETWORKS_W11_EN, without_channel
    )
    assert my_channel == 0, (
        f"no Channel field is present, so the parser must report 0 — it read "
        f"{my_channel}, which can only have come from a rate or QoS field"
    )


@pytest.mark.parametrize("raw,locale", [
    (_NETWORKS_W11_EN, "en-US"), (_NETWORKS_W11_RU, "ru-RU"),
], ids=["en-US", "ru-RU"])
def test_every_bssid_gets_its_own_channel(monkeypatch, fake_windows, raw, locale):
    """Real Windows 11 output, where a QoS pair sits inside every BSSID section."""
    nets, _ssid, _ch = _drive_scan_windows(monkeypatch, raw, _IFACE_EN)

    got = {n.bssid: n.channel for n in nets}
    assert got == {
        "aa:bb:cc:dd:ee:01": 36,
        "aa:bb:cc:dd:ee:02": 11,
        "aa:bb:cc:dd:ee:03": 6,
    }, f"{locale}: channels mis-paired — {got}"


def test_every_bssid_keeps_its_own_signal(monkeypatch, fake_windows):
    """Signal is paired the same way and must not drift when channels are fixed."""
    nets, _ssid, _ch = _drive_scan_windows(monkeypatch, _NETWORKS_W11_EN, _IFACE_EN)

    # int(pct / 2) - 100:  100% -> -50, 40% -> -80, 70% -> -65
    got = {n.bssid: n.signal_dbm for n in nets}
    assert got == {
        "aa:bb:cc:dd:ee:01": -50,
        "aa:bb:cc:dd:ee:02": -80,
        "aa:bb:cc:dd:ee:03": -65,
    }, f"signals mis-paired — {got}"


def test_the_band_is_derived_from_each_bssid_own_channel(monkeypatch, fake_windows):
    """A channel of 0 also destroys the band label, which the UI groups on."""
    nets, _ssid, _ch = _drive_scan_windows(monkeypatch, _NETWORKS_W11_EN, _IFACE_EN)
    bands = [n.band for n in nets]
    assert bands == ["5GHz", "2.4GHz", "2.4GHz"], bands


# ── Non-Latin scripts through the already-structural parsers (C3) ─────────────
# Every fixture above this point is Latin-script, and the non-English ones are
# ASCII-transliterated on top of that (`Senal`, `Autenticacion`, `Kortast`). That is
# the gap the rogue-IPv6-router and WiFi-channel defects survived in: a matcher that
# happens to work on `Kanal` and `Canal` gives a reviewer no reason to doubt it, and
# the two scripts that break the most assumptions — a different alphabet, and a script
# with no inter-word spaces at all — were never exercised anywhere in this file.
#
# These drive the same parsers with Cyrillic and CJK. They are expected to pass: the
# point is to pin that the *structure* really is what is being matched, so the next
# English literal to creep back in fails here rather than in a Store failure row.

_NET_VIEW_RU = """Общие ресурсы на \\\\SERVER

Имя ресурса   Тип     Используется как  Комментарий

-------------------------------------------------------------------------------
ADMIN$        Диск            Удаленный Admin
C$            Диск            Стандартный общий ресурс
Общая папка   Диск            Файлы команды
Команда выполнена успешно.
"""

_NET_VIEW_ZH = """在 \\\\SERVER 的共享资源

共享名        类型    用作              注释

-------------------------------------------------------------------------------
ADMIN$        磁盘            远程管理
C$            磁盘            默认共享
共享文件夹    磁盘            团队文件
命令成功完成。
"""


@pytest.mark.parametrize("raw,expected,locale", [
    (_NET_VIEW_RU, ["ADMIN$", "C$", "Общая папка"], "ru-RU"),
    (_NET_VIEW_ZH, ["ADMIN$", "C$", "共享文件夹"], "zh-CN"),
], ids=["ru-RU", "zh-CN"])
def test_net_view_shares_parse_in_cyrillic_and_cjk(raw, expected, locale):
    """Non-Latin share NAMES, not only non-Latin column headers.

    A share whose own name is Cyrillic or CJK is what an `[A-Za-z]`-shaped field
    matcher drops silently — the same defect class as D6's `net user` username regex.
    The Russian fixture's third share also carries an internal space, so it pins that
    columns are separated by RUNS of whitespace rather than by any single space.
    """
    from modules.smb_enumerator import _parse_net_view

    names = [r[0] for r in _parse_net_view(raw)]
    assert names == expected, f"{locale}: got {names}"


@pytest.mark.parametrize("raw,marker,locale", [
    (_NET_VIEW_RU, "Команда", "ru-RU"),
    (_NET_VIEW_ZH, "命令", "zh-CN"),
], ids=["ru-RU", "zh-CN"])
def test_net_view_trailing_status_prose_is_not_read_as_a_share(raw, marker, locale):
    """The closing sentence is single-spaced; a row is column-aligned.

    CJK is the sharp case — `命令成功完成。` contains no spaces at all, so a matcher
    keyed on word boundaries rather than column runs would take the whole sentence as
    a share name and put a fabricated share in a security report.
    """
    from modules.smb_enumerator import _parse_net_view

    names = [r[0] for r in _parse_net_view(raw)]
    assert all(marker not in n for n in names), (
        f"{locale}: status prose leaked in as a share — {names}"
    )


def test_ipv6_interface_header_is_matched_in_cyrillic_and_cjk():
    """The `<word> <n>:` shape holds in any script; the word never does."""
    import re
    pattern = re.compile(r"^\s*\S+\s+\d+:\s+(.+)$")
    for line, locale in [
        ("Интерфейс 12: Ethernet", "ru-RU"),
        ("接口 12: Ethernet", "zh-CN"),
        ("Schnittstelle 12: Ethernet", "de-DE"),
    ]:
        m = pattern.search(line)
        assert m is not None, f"{locale}: interface header not matched"
        assert m.group(1).strip() == "Ethernet", locale


_HOSTED_RU = """
Состояние размещенной сети
------------------------------------
    Состояние              : Запущено
    BSSID                  : 02:1a:2b:3c:4d:5e
    Тип радиомодуля        : 802.11n
    Канал                  : 11
    Число клиентов         : 2

         aa:bb:cc:dd:ee:01     Проверено
         aa:bb:cc:dd:ee:02     Проверено
"""

_HOSTED_ZH = """
承载网络状态
------------------------------------
    状态                   : 已启动
    BSSID                  : 02:1a:2b:3c:4d:5e
    无线电类型             : 802.11n
    通道                   : 11
    客户端数               : 2

         aa:bb:cc:dd:ee:01     已验证
         aa:bb:cc:dd:ee:02     已验证
"""


@pytest.mark.parametrize("raw,locale", [
    (_HOSTED_RU, "ru-RU"), (_HOSTED_ZH, "zh-CN"),
], ids=["ru-RU", "zh-CN"])
def test_hosted_network_clients_are_found_in_cyrillic_and_cjk(
    monkeypatch, fake_windows, raw, locale
):
    """The station matcher keys on a MAC at start-of-line, so the script is inert."""
    import modules.wifi_scanner as ws

    monkeypatch.setattr(ws.subprocess, "check_output", lambda *a, **k: raw)
    monkeypatch.setattr(ws, "get_arp_snapshot", lambda: {}, raising=False)

    clients = ws._get_connected_clients()
    macs = sorted(c.mac for c in clients)
    assert macs == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"], (
        f"{locale}: station list came back as {macs!r}"
    )
    assert "02:1a:2b:3c:4d:5e" not in macs, f"{locale}: the AP's own BSSID leaked in"


# ── ping: the `ms` unit itself is translated on Cyrillic locales (D4) ─────────
# Every fixture above assumes the comment that used to sit on `_REPLY_RTT_RE`:
# "Windows translates every ping label, but never TTL=, ms, or the =/< separator".
# The first half is true; the second is false one alphabet over. ru/uk/bg emit
# `мс` (Cyrillic ем + эс), so the reply line carries no ASCII `ms` at all and
# `reply_rtts()` returns [] — which reaches the user as `icmp_ping() == -1.0`,
# i.e. "unreachable", for every host that answered.
#
# C3 deliberately did not add this fixture, because an honest one fails. It is
# D4's RED test.

_PING_RU = """
Обмен пакетами с 192.168.1.1 по с 32 байтами данных:
Ответ от 192.168.1.1: число байт=32 время=3мс TTL=64
Ответ от 192.168.1.1: число байт=32 время=5мс TTL=64

Статистика Ping для 192.168.1.1:
    Пакетов: отправлено = 2, получено = 2, потеряно = 0 (0% потерь)
Приблизительное время приема-передачи в мс:
    Минимальное = 3мсек, Максимальное = 5мсек, Среднее = 4мсек
"""

_PING_RU_TOTAL_LOSS = """
Обмен пакетами с 10.0.0.9 по с 32 байтами данных:
Превышен интервал ожидания для запроса.
Превышен интервал ожидания для запроса.

Статистика Ping для 10.0.0.9:
    Пакетов: отправлено = 2, получено = 0, потеряно = 2 (100% потерь)
"""


def test_reply_rtts_reads_the_cyrillic_millisecond_unit():
    """`время=3мс` is a successful reply; an empty list reads as "no replies"."""
    import modules.utils_net as un

    assert un.reply_rtts(_PING_RU) == [3.0, 5.0]


def test_icmp_ping_returns_rtt_on_a_cyrillic_locale(monkeypatch, fake_windows):
    """-1.0 is the "unreachable" sentinel — a host that answered must never get it."""
    assert _run_icmp_ping(monkeypatch, _PING_RU) == 3.0


def test_icmp_ping_still_reports_unreachable_for_a_cyrillic_timeout(
    monkeypatch, fake_windows
):
    """Widening the unit must not turn a real outage into a fabricated RTT.

    The Russian statistics block contains `отправлено = 2` and `потеряно = 2`;
    a matcher loose enough to read a bare `= 2` as a latency would report this
    dead host as reachable.
    """
    assert _run_icmp_ping(monkeypatch, _PING_RU_TOTAL_LOSS) == -1.0


def test_cyrillic_reachable_host_is_never_reported_as_total_loss():
    """Same defect one consumer over: the Service Diagnostics ICMP probe."""
    result = IcmpProbeResult(host="192.168.1.1")
    _parse_ping_output(_PING_RU, result, "Windows")
    assert result.loss_pct == 0.0, (
        f"a host that answered every ping read {result.loss_pct}% loss"
    )
    assert result.min_ms == 3.0
    assert result.max_ms == 5.0
    assert result.avg_ms == 4.0


# ── tracert: the same `ms` literal, three more parsers (D4) ──────────────────
# `_TRACERT_EN` is this machine's REAL `tracert -d -h 8 -w 1000 1.1.1.1` output,
# captured verbatim — including the trailing space after each IP, which the
# `\s*$`-anchored parser in service_diagnostics_probes depends on. The Cyrillic
# fixture is the same bytes with only the translated tokens swapped, so any
# difference in result is attributable to the unit and nothing else.

_TRACERT_EN = """
Tracing route to 1.1.1.1 over a maximum of 8 hops

  1     4 ms     5 ms   133 ms  192.168.68.1
  2     5 ms     9 ms     3 ms  100.114.42.137
  3     *        *        *     Request timed out.
  4    22 ms    14 ms     9 ms  62.119.249.21

Trace complete.
"""

_TRACERT_RU = """
Трассировка маршрута к 1.1.1.1 с максимальным числом прыжков 8

  1     4 мс     5 мс   133 мс  192.168.68.1
  2     5 мс     9 мс     3 мс  100.114.42.137
  3     *        *        *     Превышен интервал ожидания для запроса.
  4    22 мс    14 мс     9 мс  62.119.249.21

Трассировка завершена.
"""

_TRACERT_EXPECTED_IPS = ["192.168.68.1", "100.114.42.137", "62.119.249.21"]


def _fake_tracert(monkeypatch, module, blob: str):
    """Point one module's `subprocess.run` at canned tracert output."""
    class _R:
        stdout = blob
        stderr = ""
        returncode = 0

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _R())


@pytest.mark.parametrize("raw,locale", [
    (_TRACERT_EN, "en-US"), (_TRACERT_RU, "ru-RU"),
], ids=["en-US", "ru-RU"])
def test_network_diagnostics_traceroute_hops_survive_localization(
    monkeypatch, fake_windows, raw, locale
):
    """An empty hop list renders the Health Check path section blank, not wrong.

    The en-US case is the regression half: this fixture is real captured output,
    so a unit matcher loosened far enough to read `мс` must still pick the first
    RTT column here and not some other number on the line.
    """
    import modules.network_diagnostics as nd

    _fake_tracert(monkeypatch, nd, raw)
    hops = nd._traceroute("1.1.1.1", max_hops=8)

    assert [h.ip for h in hops] == _TRACERT_EXPECTED_IPS, f"{locale}: {hops}"
    assert [h.hop for h in hops] == [1, 2, 4], f"{locale}: hop numbers"
    assert [h.rtt_ms for h in hops] == [4.0, 5.0, 22.0], f"{locale}: rtt"


@pytest.mark.parametrize("raw,locale", [
    (_TRACERT_EN, "en-US"), (_TRACERT_RU, "ru-RU"),
], ids=["en-US", "ru-RU"])
def test_service_diagnostics_traceroute_hops_survive_localization(raw, locale):
    """Service Diagnostics' own tracert parser, same defect, different regex shape.

    Here the `ms` sits inside an *optional* non-capturing group, so a reader could
    reasonably assume a missing unit just skips that part. It does not: the
    pattern is `$`-anchored, so with the RTT columns unconsumed the whole line
    fails to match and the hop vanishes.
    """
    from modules.service_diagnostics_probes import TracerouteResult, _parse_traceroute

    result = TracerouteResult(host="1.1.1.1")
    _parse_traceroute(raw, result, "Windows")

    assert [h.ip for h in result.hops] == _TRACERT_EXPECTED_IPS, f"{locale}: {result.hops}"
    assert [h.hop for h in result.hops] == [1, 2, 4], f"{locale}: hop numbers"


def test_service_diagnostics_traceroute_reports_a_real_windows_rtt():
    """Not a locale bug — this one is live on en-US and always has been.

    The Windows pattern's `ms` group is non-capturing, and the consumer below it
    reads a latency only when `system != "Windows"`, so every hop came back with
    the dataclass default of -1.0. `service_diagnostics_page.py` renders anything
    negative as `*`, so the RTT column of the Service Diagnostics traceroute
    table is a full column of asterisks on every Windows machine, in every
    locale, today. The fixture is this machine's real captured `tracert` output.
    """
    from modules.service_diagnostics_probes import TracerouteResult, _parse_traceroute

    result = TracerouteResult(host="1.1.1.1")
    _parse_traceroute(_TRACERT_EN, result, "Windows")

    assert [h.rtt_ms for h in result.hops] == [4.0, 5.0, 22.0], (
        f"first RTT column not read: {[(h.ip, h.rtt_ms) for h in result.hops]}"
    )


def test_service_diagnostics_traceroute_keeps_the_sub_millisecond_contract():
    """`<1 ms` must read as 1.0, matching icmp_ping's long-standing behaviour."""
    from modules.service_diagnostics_probes import TracerouteResult, _parse_traceroute

    raw = "  1    <1 ms    <1 ms    <1 ms  192.168.68.1 \n"
    result = TracerouteResult(host="192.168.68.1")
    _parse_traceroute(raw, result, "Windows")

    assert [(h.ip, h.rtt_ms) for h in result.hops] == [("192.168.68.1", 1.0)]


# Real `traceroute -n -w 2 -m 5 1.1.1.1` (iputils), the exact command
# service_diagnostics_probes issues on macOS and Linux.
_TRACEROUTE_POSIX = """traceroute to 1.1.1.1 (1.1.1.1), 5 hops max, 60 byte packets
 1  192.168.68.1  4.201 ms  4.105 ms  4.052 ms
 2  100.114.42.137  5.310 ms  5.201 ms  5.150 ms
 3  * * *
 4  62.119.249.21  22.400 ms  14.100 ms  9.900 ms
"""


def test_service_diagnostics_traceroute_parses_real_posix_output():
    """The POSIX pattern was written in the WINDOWS field order.

    `traceroute` prints the address first and the three latencies after it;
    `tracert` prints the latencies first and the address last. The POSIX branch
    expected `(rtt) ms (ip)`, so its optional RTT group never matched a real
    line and the address landed in whichever group the index arithmetic picked.
    Not a locale defect at all — it is wrong in the C locale on a stock Linux box.
    """
    from modules.service_diagnostics_probes import TracerouteResult, _parse_traceroute

    result = TracerouteResult(host="1.1.1.1")
    _parse_traceroute(_TRACEROUTE_POSIX, result, "Linux")

    assert [(h.hop, h.ip, h.rtt_ms) for h in result.hops] == [
        (1, "192.168.68.1", 4.201),
        (2, "100.114.42.137", 5.310),
        (3, "*", -1.0),
        (4, "62.119.249.21", 22.400),
    ], [(h.hop, h.ip, h.rtt_ms) for h in result.hops]


@pytest.mark.parametrize("raw,locale", [
    (_TRACERT_EN, "en-US"), (_TRACERT_RU, "ru-RU"),
], ids=["en-US", "ru-RU"])
def test_mtr_worker_hops_survive_localization(monkeypatch, fake_windows, raw, locale):
    """The Hop-by-Hop Trace (MTR) page accumulates per-hop loss from these emits.

    With no hop emitted at all the page is not merely blank — every hop reads as
    100% loss to a user watching the table fill in, which is the RULE-WIN23
    "a parse miss lands on a pessimistic default" shape.
    """
    import subprocess

    from workers.scan_worker import MTRWorker

    class _R:
        stdout = raw
        stderr = ""
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())

    worker = MTRWorker("1.1.1.1", max_hops=8, interval_s=0)
    got: list = []
    worker.hop_result.connect(lambda h, ip, rtt: got.append((h, ip, rtt)))
    worker.cycle_done.connect(lambda _c: worker.stop())
    worker.run()   # drive the loop body directly; one cycle, then stop()

    assert got == [
        (1, "192.168.68.1", 4.0),
        (2, "100.114.42.137", 5.0),
        (4, "62.119.249.21", 22.0),
    ], f"{locale}: {got}"


# ── The decimal separator (D4, forward coverage only) ────────────────────────
# No sampled Windows ping emits a fractional RTT at all — every real fixture in
# this file is an integer count of milliseconds — so this half has no observed
# trigger on any locale. It is written to the safe side of one specific
# ambiguity: `1,234` is a decimal separator in de/fr/ru and a THOUSANDS
# separator in en-US. Reading a grouped `1,234ms` as 1.234 would report a
# badly-latent link as excellent — a silent 1000x under-report, strictly worse
# than the current miss, which at least surfaces as -1.0 / "unreachable".
# So the comma is accepted only with a 1-2 digit fraction, which no thousands
# grouping produces; a 3-digit group falls through to no match.

def test_a_comma_decimal_rtt_is_read_as_a_fraction():
    import modules.utils_net as un

    assert un.reply_rtts("Ответ от 10.0.0.1: время=1,5мс TTL=64") == [1.5]
    assert un.reply_rtts("Antwort von 10.0.0.1: Zeit=12,25ms TTL=64") == [12.25]


def test_a_thousands_grouped_rtt_is_never_read_as_a_fraction():
    """1,234 ms must not become 1.234 ms — refuse rather than under-report 1000x."""
    import modules.utils_net as un

    got = un.reply_rtts("Reply from 10.0.0.1: bytes=32 time=1,234ms TTL=64")
    assert 1.234 not in got, f"grouped thousands read as a fraction: {got}"
    assert got in ([], [1234.0]), f"unexpected reading of a grouped RTT: {got}"


# ── `net user` — the account list in an SMB security report ───────────────────
#
# Verbatim `net user` from the development machine (sv-SE Windows 11), captured
# with subprocess and decoded "oem" — trailing column padding included, because
# the column grid is the only untranslated structure in the block.
_NET_USER_SV = (
    "\r\nAnvändarkonton för \\\\DESKTOP-LN2HAJV\r\n\r\n"
    "----------------------------------------"
    "---------------------------------------\r\n"
    "Administrator            DefaultAccount           Guest                    \r\n"
    "ossia                    WDAGUtilityAccount       \r\n"
    "Kommandot har utförts.\r\n\r\n"
)

_NET_USER_EN = (
    "\r\nUser accounts for \\\\DESKTOP-LN2HAJV\r\n\r\n"
    "----------------------------------------"
    "---------------------------------------\r\n"
    "Administrator            DefaultAccount           Guest                    \r\n"
    "ossia                    WDAGUtilityAccount       \r\n"
    "The command completed successfully.\r\n\r\n"
)

_NET_USER_DE = (
    "\r\nBenutzerkonten für \\\\DESKTOP-LN2HAJV\r\n\r\n"
    "----------------------------------------"
    "---------------------------------------\r\n"
    "Administrator            DefaultAccount           Gast                     \r\n"
    "ossia                    WDAGUtilityAccount       \r\n"
    "Der Befehl wurde erfolgreich ausgeführt.\r\n\r\n"
)

# ru-RU matters twice: the prose is translated AND two account names are Cyrillic,
# which the [A-Za-z]-anchored regex cannot represent at all.
_NET_USER_RU = (
    "\r\nУчетные записи "
    "для \\\\DESKTOP-LN2HAJV\r\n\r\n"
    "----------------------------------------"
    "---------------------------------------\r\n"
    "Administrator            Гость                    "
    "Петров                  \r\n"
    "ossia                    WDAGUtilityAccount       \r\n"
    "Команда выполнен"
    "а успешно.\r\n\r\n"
)

# ja-JP is the case that kills the obvious "prose has spaces in it" shortcut:
# Japanese writes without inter-word spaces, so the status line is a single
# whitespace-free token, indistinguishable in shape from a one-account row.
_NET_USER_JA = (
    "\r\n\\\\DESKTOP-LN2HAJV のユーザー アカウント\r\n\r\n"
    "----------------------------------------"
    "---------------------------------------\r\n"
    "Administrator            DefaultAccount           Guest                    \r\n"
    "ossia                    WDAGUtilityAccount       \r\n"
    "コマンドは正常に終了しました。\r\n\r\n"
)

_SV_EXPECTED = ["Administrator", "DefaultAccount", "Guest", "ossia", "WDAGUtilityAccount"]
_DE_EXPECTED = ["Administrator", "DefaultAccount", "Gast", "ossia", "WDAGUtilityAccount"]


class TestNetUserAccountRows:
    """A fabricated row here is a fabricated user account in a security report.

    The shipped extractor ran ``re.findall(r"\\b([A-Za-z][A-Za-z0-9_$-]{1,19})\\b")``
    over every line and dropped four English words. Measured against this machine's
    real ``net user``, that yields eight "accounts" for five real ones: the host name
    out of the header, plus ``Kommandot`` and ``har`` out of the Swedish status line.
    On en-US it is no better — the denylist does not cover ``for``, ``completed`` or
    ``successfully``. And ``[A-Za-z]`` cannot represent a Cyrillic or CJK account name
    at all, so those vanish silently.
    """

    @pytest.mark.parametrize("label,raw,expected", [
        ("sv-SE (verbatim capture)", _NET_USER_SV, _SV_EXPECTED),
        ("en-US", _NET_USER_EN, _SV_EXPECTED),
        # The built-in guest account is itself renamed per locale, which is
        # precisely why no denylist of account names could ever have worked.
        ("de-DE", _NET_USER_DE, _DE_EXPECTED),
        ("ja-JP", _NET_USER_JA, _SV_EXPECTED),
    ])
    def test_only_real_account_rows_are_returned(self, label, raw, expected):
        from modules.smb_enumerator import _parse_net_user_names

        assert _parse_net_user_names(raw) == expected, label

    def test_a_cyrillic_account_name_survives(self):
        """``[A-Za-z]`` dropped these; the account list is not an ASCII structure."""
        from modules.smb_enumerator import _parse_net_user_names

        names = _parse_net_user_names(_NET_USER_RU)
        assert names == ["Administrator", "Гость",
                         "Петров", "ossia",
                         "WDAGUtilityAccount"]

    def test_output_with_no_table_yields_nothing(self):
        """A usage banner or an error must produce no accounts, never a guess."""
        from modules.smb_enumerator import _parse_net_user_names

        assert _parse_net_user_names("") == []
        assert _parse_net_user_names(
            "The syntax of this command is:\r\n\r\nNET USER\r\n"
            "[username [password | *] [options]] [/DOMAIN]\r\n"
        ) == []


class TestNetUserIsOnlyRunWhenItCanAnswer:
    """``net user`` has no remote-target syntax — it always describes the machine
    it runs on.

    This machine's own usage banner is the evidence: ``NET USER [username
    [password | *] [options]] [/DOMAIN]`` — no ``\\\\computer`` form exists. So after
    ``net use \\\\host\\IPC$`` it still enumerates the *scanner's* accounts, not the
    target's, and only ``/domain`` asks a question about anything else.

    The shipped call passed ``""`` as a positional argument whenever no domain was
    given (``f"/domain" if domain else ""``). Windows reads that as a username, exits
    1 with the usage banner, and ``_run`` swallows it — so the Users table has been
    empty on the no-domain path on every locale, en-US included. Fixing only the
    argument would have started reporting the scanner's own accounts as the target's,
    which is a worse answer than none.
    """

    @staticmethod
    def _record_argv(monkeypatch):
        from modules import smb_enumerator as smb

        calls: list = []

        def _fake(cmd, *a, **kw):
            calls.append(list(cmd))
            return ""

        monkeypatch.setattr(smb.subprocess, "check_output", _fake)
        monkeypatch.setattr(smb.platform, "system", lambda: "Windows")
        return smb, calls

    def test_no_empty_string_argument_is_ever_passed_to_net(self, monkeypatch):
        smb, calls = self._record_argv(monkeypatch)

        smb._net_exe_enum("10.0.0.5", "admin", "pw", "", None)

        offenders = [c for c in calls if "" in c]
        assert not offenders, "an empty argv element makes net exit 1: %r" % offenders

    def test_net_user_is_skipped_when_no_domain_is_given(self, monkeypatch):
        smb, calls = self._record_argv(monkeypatch)

        smb._net_exe_enum("10.0.0.5", "admin", "pw", "", None)

        assert not [c for c in calls if c[:2] == ["net", "user"]], (
            "without a domain, `net user` describes the scanner, not the target"
        )

    def test_net_user_runs_against_the_domain_when_one_is_given(self, monkeypatch):
        smb, calls = self._record_argv(monkeypatch)

        smb._net_exe_enum("10.0.0.5", "admin", "pw", "CORP", None)

        assert ["net", "user", "/domain"] in calls, calls

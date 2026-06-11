"""Tests for modules/service_mapper.py — device-to-service mapping engine."""
from modules.service_mapper import ServiceInfo, get_services


# ── ServiceInfo dataclass ─────────────────────────────────────────────────────

def test_service_info_is_dataclass():
    svc = ServiceInfo(id="psn", name="PlayStation Network", category="gaming")
    assert svc.id == "psn"
    assert svc.name == "PlayStation Network"
    assert svc.category == "gaming"
    assert svc.icon == ""


def test_service_info_with_icon():
    svc = ServiceInfo(id="netflix", name="Netflix", category="streaming", icon="▶")
    assert svc.icon == "▶"


# ── get_services — Games Console ─────────────────────────────────────────────

def test_games_console_sony_returns_psn():
    result = get_services(device_type="Games Console", vendor="Sony Interactive Entertainment")
    names = [s.name for s in result]
    assert "PlayStation Network" in names


def test_games_console_microsoft_returns_xbox_live():
    result = get_services(device_type="Games Console", vendor="Microsoft Corporation")
    names = [s.name for s in result]
    assert "Xbox Live" in names


def test_games_console_nintendo_returns_nintendo_online():
    result = get_services(device_type="Games Console", vendor="Nintendo Co., Ltd.")
    names = [s.name for s in result]
    assert "Nintendo Online" in names


def test_games_console_sony_also_returns_streaming():
    result = get_services(device_type="Games Console", vendor="Sony Interactive Entertainment")
    names = [s.name for s in result]
    # PS4/PS5 also supports Netflix, YouTube, etc.
    assert "Netflix" in names
    assert "YouTube" in names


def test_games_console_microsoft_returns_no_psn():
    result = get_services(device_type="Games Console", vendor="Microsoft Corporation")
    names = [s.name for s in result]
    assert "PlayStation Network" not in names


def test_games_console_sony_returns_no_xbox_live():
    result = get_services(device_type="Games Console", vendor="Sony Interactive Entertainment")
    names = [s.name for s in result]
    assert "Xbox Live" not in names


# ── get_services — Smart TV ───────────────────────────────────────────────────

def test_smart_tv_returns_netflix():
    result = get_services(device_type="Smart TV")
    names = [s.name for s in result]
    assert "Netflix" in names


def test_smart_tv_returns_youtube():
    result = get_services(device_type="Smart TV")
    names = [s.name for s in result]
    assert "YouTube" in names


def test_smart_tv_returns_spotify():
    result = get_services(device_type="Smart TV")
    names = [s.name for s in result]
    assert "Spotify" in names


def test_smart_tv_apple_vendor_returns_apple_tv_plus():
    result = get_services(device_type="Smart TV", vendor="Apple Inc.")
    names = [s.name for s in result]
    assert "Apple TV+" in names


def test_smart_tv_non_apple_no_apple_tv_plus():
    result = get_services(device_type="Smart TV", vendor="Samsung Electronics")
    names = [s.name for s in result]
    assert "Apple TV+" not in names


# ── get_services — Streaming Device ──────────────────────────────────────────

def test_streaming_device_returns_netflix():
    result = get_services(device_type="Streaming Device")
    names = [s.name for s in result]
    assert "Netflix" in names


def test_streaming_device_returns_disney_plus():
    result = get_services(device_type="Streaming Device")
    names = [s.name for s in result]
    assert "Disney+" in names


# ── get_services — Android Device ────────────────────────────────────────────

def test_android_device_returns_google_services():
    result = get_services(device_type="Android Device")
    names = [s.name for s in result]
    assert "Google services" in names


def test_android_device_returns_youtube():
    result = get_services(device_type="Android Device")
    names = [s.name for s in result]
    assert "YouTube" in names


# ── get_services — NAS ────────────────────────────────────────────────────────

def test_nas_returns_plex():
    result = get_services(device_type="NAS / File Server")
    names = [s.name for s in result]
    assert "Plex Media Server" in names


def test_nas_synology_returns_samba():
    result = get_services(device_type="NAS / File Server", vendor="Synology Inc.")
    names = [s.name for s in result]
    assert "Samba / SMB shares" in names


# ── get_services — Home Assistant hostname detection ─────────────────────────

def test_sbc_homeassistant_hostname_returns_home_assistant():
    result = get_services(device_type="Single Board Computer", hostname="homeassistant")
    names = [s.name for s in result]
    assert "Home Assistant" in names


def test_sbc_hassio_hostname_returns_home_assistant():
    result = get_services(device_type="Single Board Computer", hostname="hassio")
    names = [s.name for s in result]
    assert "Home Assistant" in names


def test_sbc_generic_hostname_no_home_assistant():
    result = get_services(device_type="Single Board Computer", hostname="raspberrypi")
    names = [s.name for s in result]
    assert "Home Assistant" not in names


# ── get_services — edge cases ─────────────────────────────────────────────────

def test_unknown_device_returns_empty():
    result = get_services(device_type="Unknown Device")
    assert result == []


def test_empty_args_returns_empty():
    result = get_services()
    assert result == []


def test_returns_list_type():
    result = get_services(device_type="Smart TV")
    assert isinstance(result, list)


def test_no_duplicate_service_names():
    result = get_services(device_type="Smart TV", vendor="Amazon Technologies")
    names = [s.name for s in result]
    # Amazon Prime Video should appear only once despite matching two rules
    assert names.count("Amazon Prime Video") <= 1


def test_return_values_are_service_info_instances():
    result = get_services(device_type="Smart TV")
    assert all(isinstance(s, ServiceInfo) for s in result)


def test_service_info_category_populated():
    result = get_services(device_type="Smart TV")
    assert all(s.category != "" for s in result)


# ── get_services — Apple Mobile device ───────────────────────────────────────

def test_mobile_phone_apple_returns_icloud():
    result = get_services(device_type="Mobile Phone", vendor="Apple Inc.")
    names = [s.name for s in result]
    assert "iCloud" in names


def test_mobile_phone_non_apple_no_icloud():
    result = get_services(device_type="Mobile Phone", vendor="Samsung Electronics")
    names = [s.name for s in result]
    assert "iCloud" not in names

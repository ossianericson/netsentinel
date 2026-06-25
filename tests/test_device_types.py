"""Tests for modules/device_types.py — canonical label constants."""
from modules.device_types import (
    TYPE_ANDROID_DEVICE,
    TYPE_GAMES_CONSOLE,
    TYPE_INDUSTRIAL_ICS,
    TYPE_IOT_DEVICE,
    TYPE_IP_CAMERA,
    TYPE_IPHONE_IPAD,
    TYPE_LINUX_HOST,
    TYPE_MACOS_DEVICE,
    TYPE_MATTER_DEVICE,
    TYPE_MESH_NODE,
    TYPE_NETWORK_DEVICE,
    TYPE_NETWORK_SWITCH,
    TYPE_ROUTER_FIREWALL,
    TYPE_ROUTER_GATEWAY,
    TYPE_SBC,
    TYPE_SMART_BULB,
    TYPE_SMART_HOME_HUB,
    TYPE_SMART_HOME_HUB_DISPLAY,
    TYPE_SMART_PLUG,
    TYPE_SMART_SPEAKER,
    TYPE_SMART_SPEAKER_AUDIO,
    TYPE_SMART_THERMOSTAT,
    TYPE_SMART_TV,
    TYPE_STREAMING_STICK,
    TYPE_TABLET,
    TYPE_UNKNOWN,
    TYPE_VIDEO_DOORBELL,
    TYPE_VOIP_PHONE,
    TYPE_WEARABLE,
    TYPE_WINDOWS_PC,
    TYPE_WIRELESS_AP,
)


def test_all_constants_are_non_empty_strings():
    constants = [
        TYPE_ROUTER_FIREWALL, TYPE_ROUTER_GATEWAY, TYPE_NETWORK_SWITCH,
        TYPE_WIRELESS_AP, TYPE_MESH_NODE, TYPE_IP_CAMERA, TYPE_VIDEO_DOORBELL,
        TYPE_SMART_HOME_HUB, TYPE_SMART_HOME_HUB_DISPLAY, TYPE_IOT_DEVICE,
        TYPE_SMART_PLUG, TYPE_SMART_BULB, TYPE_SMART_THERMOSTAT, TYPE_MATTER_DEVICE,
        TYPE_SMART_SPEAKER, TYPE_SMART_SPEAKER_AUDIO, TYPE_SMART_TV,
        TYPE_STREAMING_STICK, TYPE_GAMES_CONSOLE, TYPE_WINDOWS_PC, TYPE_MACOS_DEVICE,
        TYPE_LINUX_HOST, TYPE_IPHONE_IPAD, TYPE_ANDROID_DEVICE, TYPE_TABLET,
        TYPE_WEARABLE, TYPE_VOIP_PHONE, TYPE_INDUSTRIAL_ICS, TYPE_SBC,
        TYPE_NETWORK_DEVICE, TYPE_UNKNOWN,
    ]
    for c in constants:
        assert isinstance(c, str) and c, f"Expected non-empty string, got {c!r}"


def test_smart_speaker_vs_audio_are_distinct():
    assert TYPE_SMART_SPEAKER != TYPE_SMART_SPEAKER_AUDIO


def test_smart_plug_canonical_label():
    assert TYPE_SMART_PLUG == "Smart Plug"


def test_smart_bulb_canonical_label():
    assert TYPE_SMART_BULB == "Smart Bulb"


def test_smart_thermostat_canonical_label():
    assert TYPE_SMART_THERMOSTAT == "Smart Thermostat"


def test_matter_device_canonical_label():
    assert TYPE_MATTER_DEVICE == "Matter/Thread Device"


def test_smart_speaker_canonical_label():
    assert TYPE_SMART_SPEAKER == "Smart Speaker"


def test_no_smart_speaker_display_constant():
    # "Smart Speaker / Display" was the old wrong label; it must not exist as a constant.
    import modules.device_types as dt
    assert not hasattr(dt, "TYPE_SMART_SPEAKER_DISPLAY"), (
        "TYPE_SMART_SPEAKER_DISPLAY must not exist — use TYPE_SMART_SPEAKER instead"
    )

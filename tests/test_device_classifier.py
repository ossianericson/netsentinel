"""Tests for device_classifier module."""
from modules.device_classifier import (
    ClassificationResult,
    classify,
    classify_registry_first,
    classify_with_evidence,
    is_randomized_mac,
)


def test_classify_ip_camera_by_vendor():
    assert classify(vendor="Hikvision Digital Technology", hostname="", open_ports=set()) == "IP Camera"


def test_classify_ip_camera_by_hostname():
    assert classify(vendor="", hostname="ipcam-01", open_ports=set()) == "IP Camera"


def test_classify_nas_by_vendor():
    result = classify(vendor="Synology Incorporated", hostname="", open_ports=set())
    assert "NAS" in result or "File" in result


def test_classify_nas_by_ports():
    result = classify(vendor="Unknown", hostname="", open_ports={445, 548})
    assert "NAS" in result or "File" in result


def test_classify_domain_controller_by_ports():
    result = classify(vendor="Microsoft", hostname="dc01", open_ports={389, 445, 88})
    assert "Domain Controller" in result


def test_classify_printer():
    result = classify(vendor="HP", hostname="printer", open_ports={631, 9100})
    assert "Print" in result


def test_classify_smart_tv_by_hostname():
    result = classify(vendor="Samsung Electronics", hostname="samsung-tv", open_ports=set())
    assert "TV" in result or "Smart" in result


def test_classify_router_by_vendor():
    result = classify(vendor="Cisco Systems", hostname="", open_ports=set())
    assert "Router" in result or "Firewall" in result or "Switch" in result


def test_classify_unknown_returns_string():
    result = classify(vendor="", hostname="", open_ports=set())
    assert isinstance(result, str)
    assert len(result) > 0


def test_classify_accepts_list_ports():
    # open_ports can be a list or set
    result = classify(vendor="Hikvision Digital Technology", hostname="", open_ports=[])
    assert isinstance(result, str)


# ── is_randomized_mac ────────────────────────────────────────────────────────

def test_randomized_mac_detected():
    # U/L bit (0x02) set in first octet → locally administered
    assert is_randomized_mac("02:00:00:00:00:01") is True


def test_randomized_mac_dash_format():
    assert is_randomized_mac("02-00-00-00-00-01") is True


def test_unicast_mac_not_randomized():
    # Real Google OUI — U/L bit clear
    assert is_randomized_mac("f4:f5:d8:aa:bb:cc") is False


def test_randomized_mac_empty_string():
    assert is_randomized_mac("") is False


def test_randomized_mac_condensed_format():
    # 020000000001 — no separators
    assert is_randomized_mac("020000000001") is True


# ── New hostname rules ───────────────────────────────────────────────────────

def test_samsung_galaxy_phone_hostname():
    # SM-G = Galaxy S series phone; no vendor info (unknown OUI)
    result = classify(vendor="", hostname="SM-G991B", open_ports=set())
    assert result == "Android Device"


def test_samsung_galaxy_phone_lowercase():
    result = classify(vendor="", hostname="sm-a525f", open_ports=set())
    assert result == "Android Device"


def test_samsung_galaxy_tab_hostname():
    # SM-T = Galaxy Tab; should be Tablet, not Android Device
    result = classify(vendor="", hostname="SM-T510", open_ports=set())
    assert result == "Tablet"


def test_lg_webos_hostname():
    result = classify(vendor="", hostname="lgwebos-12345", open_ports=set())
    assert result == "Smart TV"


def test_bravia_hostname():
    result = classify(vendor="", hostname="BRAVIA-KD-55X9000", open_ports=set())
    assert result == "Smart TV"


def test_raspberry_pi_hostname():
    result = classify(vendor="", hostname="raspberrypi", open_ports=set())
    assert result == "Single Board Computer"


def test_libreelec_hostname():
    result = classify(vendor="", hostname="LibreELEC-12", open_ports=set())
    assert result == "Single Board Computer"


def test_raspberry_pi_vendor():
    result = classify(vendor="Raspberry Pi Foundation", hostname="", open_ports=set())
    assert result == "Single Board Computer"


def test_ps5_standalone_hostname():
    # Without trailing separator — previously fell through to Unknown Device
    result = classify(vendor="", hostname="PS5", open_ports=set())
    assert result == "Games Console"


def test_google_tv_hostname():
    result = classify(vendor="", hostname="google-tv-living-room", open_ports=set())
    assert result == "Smart TV"


# ── ClassificationResult and classify_with_evidence ─────────────────────────

def test_classification_result_is_dataclass():
    result = classify_with_evidence(vendor="Synology", hostname="diskstation")
    assert isinstance(result, ClassificationResult)


def test_classification_result_has_required_fields():
    result = classify_with_evidence()
    assert hasattr(result, "device_type")
    assert hasattr(result, "vendor")
    assert hasattr(result, "confidence")
    assert hasattr(result, "evidence")
    assert hasattr(result, "mac_randomized")


def test_classification_result_vendor_boosts_confidence():
    # Known vendor match alone should push confidence above 0
    result = classify_with_evidence(vendor="Hikvision Digital Technology")
    assert result.confidence > 0.0
    assert result.device_type == "IP Camera"


def test_classification_result_hostname_evidence_populated():
    result = classify_with_evidence(hostname="raspberrypi")
    assert result.device_type == "Single Board Computer"
    assert any("hostname" in e for e in result.evidence)


def test_classification_result_randomized_mac_flag():
    result = classify_with_evidence(
        vendor="Some Vendor",
        hostname="some-device",
        mac="02:00:00:00:00:01",
    )
    assert result.mac_randomized is True
    assert any("randomized-mac" in e for e in result.evidence)


def test_classification_result_randomized_mac_reduces_confidence():
    normal = classify_with_evidence(vendor="Cisco Systems", hostname="")
    penalised = classify_with_evidence(
        vendor="Cisco Systems", hostname="", mac="02:00:00:00:00:01"
    )
    assert penalised.confidence < normal.confidence


def test_classification_result_unknown_device_zero_confidence():
    result = classify_with_evidence(vendor="", hostname="", open_ports=set())
    assert result.device_type == "Unknown Device"
    assert result.confidence == 0.0


def test_classify_with_evidence_matches_classify():
    # classify_with_evidence must always agree with classify() on device_type
    cases = [
        {"vendor": "Hikvision Digital Technology", "hostname": "", "open_ports": set()},
        {"vendor": "", "hostname": "raspberrypi", "open_ports": set()},
        {"vendor": "Synology Incorporated", "hostname": "", "open_ports": set()},
        {"vendor": "", "hostname": "SM-T510", "open_ports": set()},
    ]
    for kwargs in cases:
        plain = classify(**kwargs)
        rich = classify_with_evidence(**kwargs)
        assert rich.device_type == plain, f"Mismatch for {kwargs}: {rich.device_type!r} != {plain!r}"


# ── is_gateway behaviour ─────────────────────────────────────────────────────

def test_is_gateway_returns_router():
    # Gateway with no recognisable hostname → generic router label
    result = classify(vendor="Liteon Technology Corporation", hostname="", is_gateway=True)
    assert result == "Router / Gateway"


def test_is_gateway_with_ps4_hostname_returns_router():
    # The exact bug: Liteon OUI + "Playstation 4" hostname must not produce "Games Console"
    result = classify(
        vendor="Liteon Technology Corporation",
        hostname="Playstation 4",
        is_gateway=True,
    )
    assert result == "Router / Gateway"


def test_is_gateway_with_deco_hostname_returns_mesh_node():
    # Mesh routers with recognisable hostname should get the mesh label
    result = classify(vendor="TP-Link", hostname="deco-main", is_gateway=True)
    assert result == "Mesh Network Node"


def test_is_gateway_eero_hostname():
    result = classify(vendor="", hostname="eero-kitchen", is_gateway=True)
    assert result == "Mesh Network Node"


def test_is_gateway_orbi_hostname():
    result = classify(vendor="Netgear", hostname="orbi-router", is_gateway=True)
    assert result == "Mesh Network Node"


def test_is_gateway_false_does_not_force_router():
    # is_gateway=False (default) must not bypass normal rules
    result = classify(vendor="", hostname="PS5", is_gateway=False)
    assert result == "Games Console"


def test_classify_with_evidence_is_gateway_confidence_one():
    r = classify_with_evidence(vendor="Liteon Technology Corporation", hostname="", is_gateway=True)
    assert r.device_type == "Router / Gateway"
    assert r.confidence == 1.0
    assert "is_gateway" in r.evidence


def test_classify_with_evidence_is_gateway_mesh():
    r = classify_with_evidence(vendor="", hostname="deco-floor2", is_gateway=True)
    assert r.device_type == "Mesh Network Node"
    assert r.confidence == 1.0


# ── Chip-maker OUI + web-port rule ──────────────────────────────────────────

def test_liteon_with_web_port_returns_router():
    # Liteon OUI + port 80 → should be classified as a router, not Unknown
    result = classify(vendor="Liteon Technology Corporation", hostname="", open_ports={80})
    assert result == "Router / Gateway"


def test_realtek_with_https_port_returns_router():
    result = classify(vendor="Realtek Semiconductor Corp.", hostname="", open_ports={443})
    assert result == "Router / Gateway"


def test_azurewave_with_admin_port_returns_router():
    result = classify(vendor="AzureWave Technology Inc.", hostname="", open_ports={8080})
    assert result == "Router / Gateway"


def test_liteon_without_web_port_not_forced_router():
    # Liteon with NO web ports should fall through (no rule forces it to Router)
    result = classify(vendor="Liteon Technology Corporation", hostname="", open_ports=set())
    assert result != "Router / Gateway"


# ── vendor_re must be corroboration, not a hard gate, for rules that also ──
# ── carry hostname_re/os_re (RULE-T3 regression) ────────────────────────────
#
# device_classifier.py made vendor_re an unconditional final gate in both
# classify() and classify_with_evidence(), contradicting the comment 25 lines
# above it ("only skip if there are no other discriminators") and making that
# earlier block dead code. iOS/Android randomise the MAC by default, so
# vendor lookup returns "" on exactly the device classes whose hostname rules
# exist -- a hostname that literally reads "iPhone" classified as
# Unknown Device. any_ports-only rules must stay vendor-gated: ports alone
# are too broad a signal to stand in for vendor evidence.

def test_hostname_iphone_no_vendor_classifies_as_iphone():
    # The exact live defect: 92:ac:4a:bf:8d:10, vendor="" (randomised MAC,
    # vendor lookup fails), hostname="Ossians-iPhone-2022".
    result = classify(vendor="", hostname="Ossians-iPhone-2022", open_ports=set())
    assert result == "iPhone / iPad"


def test_hostname_ipad_no_vendor_classifies_as_iphone():
    result = classify(vendor="", hostname="my-ipad", open_ports=set())
    assert result == "iPhone / iPad"


def test_hostname_echo_no_vendor_classifies_as_smart_speaker():
    from modules.device_types import TYPE_SMART_SPEAKER
    result = classify(vendor="", hostname="kitchen-echo", open_ports=set())
    assert result == TYPE_SMART_SPEAKER


def test_hostname_firestick_no_vendor_classifies_as_streaming_stick():
    result = classify(vendor="", hostname="bedroom-firestick", open_ports=set())
    assert result == "Streaming Stick"


def test_hostname_iphone_no_vendor_confidence_is_hostname_only():
    # classify_with_evidence() must still agree with classify() (existing
    # invariant, test_classify_with_evidence_matches_classify), and score
    # this as a hostname-only match: 0.30, not the 0.70 a vendor-corroborated
    # match would earn.
    result = classify_with_evidence(vendor="", hostname="Ossians-iPhone-2022")
    assert result.device_type == "iPhone / iPad"
    assert result.confidence == 0.30
    assert any("hostname" in e for e in result.evidence)
    assert not any(e.startswith("vendor") for e in result.evidence)


def test_hostname_iphone_with_vendor_confidence_is_higher():
    # A vendor-corroborated match must still score higher than the
    # hostname-only case above -- vendor is a bonus, not a no-op.
    hostname_only = classify_with_evidence(vendor="", hostname="Ossians-iPhone-2022")
    with_vendor = classify_with_evidence(vendor="Apple, Inc.", hostname="Ossians-iPhone-2022")
    assert with_vendor.device_type == "iPhone / iPad"
    assert with_vendor.confidence > hostname_only.confidence


def test_no_vendor_with_web_ports_does_not_become_router():
    # any_ports-only discriminators must stay vendor-gated after the fix --
    # a bare host with 80/443 open and no vendor evidence is not a router.
    result = classify(vendor="", hostname="", open_ports={80, 443})
    assert result != "Router / Gateway"


def test_no_vendor_with_kasa_port_does_not_become_smart_plug():
    from modules.device_types import TYPE_SMART_PLUG
    result = classify(vendor="", hostname="", open_ports={9999})
    assert result != TYPE_SMART_PLUG


# ── Golden-set regression: live reference network (vendor, hostname) pairs ──
#
# Snapshotted from the reference home network's known_device table
# (docs/spikes/device-identity-baseline.md) before this fix. Every pair
# except Ossians-iPhone-2022 must classify identically before and after the
# vendor_re gate change -- _RULES is first-match-wins, so a newly-reachable
# broad hostname rule could shadow a later, more specific one (e.g. "Tablet"
# vs "iPhone / iPad" both matching "ipad"). This is the real risk in the
# change, not the targeted fix itself.
_GOLDEN_SET = [
    ("Lexmark International, Inc.", "ET0021B7A3091A", "Print Server"),
    ("Sonos", "Barnens-rum", "Smart Speaker / Audio"),
    ("Unknown", "", "Unknown Device"),
    ("AzureWave Technology Inc.", "", "Unknown Device"),
    ("TP-Link (Deco mesh / RE series extenders)", "", "Unknown Device"),
    ("Amazon Technologies Inc.", "", "Unknown Device"),
    ("Samsung", "Samsung", "Unknown Device"),
    ("Google Chromecast / Google Home / Cast Audio", "", "Unknown Device"),
    ("Liteon Technology Corporation", "PS4-C8208A", "Games Console"),
    # Was "Unknown Device" at confidence 0.0 -- one of the reference network's
    # zero-confidence rows, and an ordinary work laptop. Intel puts its OUI on
    # client NICs and sells no consumer routers, so the vendor is real evidence.
    ("Intel Corporate", "CWR-5CG6051CD0", "Computer / Workstation"),
    ("Samsung Electronics Co.,Ltd", "", "Unknown Device"),
    ("Sony Interactive Entertainment", "PS5-D79FFE", "Games Console"),
    ("Google", "", "Unknown Device"),
    # Was pinned here as "Domain Controller" with the note 'pre-existing "ad-"
    # substring bug ... unrelated to this fix, unaffected'. The bug was real and
    # live: this exact row rendered as a Domain Controller in the reference
    # network's Devices page. Fixed by anchoring the rule; see
    # test_a_device_named_after_a_person_is_not_classified_as_infrastructure.
    ("Unknown", "iPad-2", "iPhone / iPad"),
    ("Unknown", "Ossians-iPhone-2022", "iPhone / iPad"),  # THE fix.
    ("Apple, Inc.", "", "iPhone / iPad"),  # vendor-only rule, already worked.
    # Deliberate, accepted loss from anchoring "nas". "PINAS" and "Jonas" are
    # structurally identical -- both end in "nas" preceded by a letter -- so no
    # pattern accepts one and rejects the other, and a person's PC mislabelled a
    # NAS server is the worse error. Not harmed in practice: this row's real
    # IEEE vendor is Raspberry Pi (the "Microsoft" here is the stale stored
    # value), and both the vendor rule and the MAC registry answer
    # "Single Board Computer" -- which is what the user actually sees.
    ("Microsoft", "PINAS", "Unknown Device"),
    ("Raspberry Pi", "PINAS", "Single Board Computer"),
    ("Raspberry Pi", "LIBREELEC", "Single Board Computer"),
    ("Google Nest / Nest Wifi / Google Wifi Router", "", "Unknown Device"),
    ("Intel Corporate", "FractalMSI", "Computer / Workstation"),  # a desktop
    ("Arcadyan Corporation", "LGwebOSTV-EAg4-1", "Smart TV"),
    ("Apple, Inc.", "Lovisas-ny-iphone", "iPhone / iPad"),  # already worked
    # pre-fix (vendor AND hostname both matched the gated rule).
]


def test_golden_set_reference_network_classifications():
    for vendor, hostname, expected in _GOLDEN_SET:
        result = classify(vendor=vendor, hostname=hostname, open_ports=set())
        assert result == expected, (
            f"vendor={vendor!r} hostname={hostname!r}: "
            f"got {result!r}, expected {expected!r}"
        )


# ── get_all_device_types() tests (Sprint 6) ──────────────────────────────────

def test_get_all_device_types_returns_list():
    from modules.device_classifier import get_all_device_types
    result = get_all_device_types()
    assert isinstance(result, list)
    assert len(result) > 0


def test_get_all_device_types_is_sorted():
    from modules.device_classifier import get_all_device_types
    result = get_all_device_types()
    assert result == sorted(result)


def test_get_all_device_types_contains_required_labels():
    from modules.device_classifier import get_all_device_types
    result = get_all_device_types()
    for required in ("Router / Gateway", "Mesh Network Node", "Unknown Device"):
        assert required in result, f"Expected '{required}' in get_all_device_types()"


def test_get_all_device_types_contains_classifier_labels():
    from modules.device_classifier import get_all_device_types, _RULES
    result = get_all_device_types()
    rule_labels = {r["label"] for r in _RULES}
    for label in rule_labels:
        assert label in result, f"Rule label '{label}' missing from get_all_device_types()"


def test_get_all_device_types_all_strings():
    from modules.device_classifier import get_all_device_types
    result = get_all_device_types()
    for item in result:
        assert isinstance(item, str) and item, f"Non-string or empty item: {item!r}"


# ── P0-1: Nest vendor regex collision fix ────────────────────────────────────

def test_nest_without_video_port_not_doorbell():
    # Nest Hub / Thermostat with no video-streaming port must NOT become a doorbell.
    result = classify(vendor="Nest Labs", hostname="", open_ports=set())
    assert result != "Video Doorbell / Intercom"


def test_nest_without_video_port_not_doorbell_443_only():
    # Port 443 is cloud-only for Nest — not enough to confirm a doorbell.
    result = classify(vendor="Nest Labs", hostname="", open_ports={443})
    assert result != "Video Doorbell / Intercom"


def test_nest_hub_by_hostname():
    result = classify(vendor="Nest Labs", hostname="nest-hub-living", open_ports=set())
    assert result == "Smart Home Hub / Display"


def test_nest_hub_mini_by_hostname():
    result = classify(vendor="Nest Labs", hostname="nestmini-abc123", open_ports=set())
    assert result == "Smart Home Hub / Display"


def test_nest_audio_by_hostname():
    result = classify(vendor="Nest Labs", hostname="nest-audio-kitchen", open_ports=set())
    assert result == "Smart Home Hub / Display"


def test_nest_thermostat_by_local_api_port():
    # Port 9543 is the Nest thermostat local API — conclusive evidence.
    result = classify(vendor="Nest Labs", hostname="", open_ports={9543})
    assert result == "Smart Thermostat"


def test_nest_thermostat_by_hostname():
    result = classify(vendor="Nest Labs", hostname="nest-thermostat-a1b2", open_ports=set())
    assert result == "Smart Thermostat"


def test_nest_doorbell_with_rtsp_port():
    # Port 554 (RTSP) is a video-streaming port — confirms Nest doorbell / cam.
    # Note: the IP Camera port rule fires before the Nest doorbell rule when port
    # 554 is open, so "IP Camera" is also an acceptable result here.
    result = classify(vendor="Nest Labs", hostname="", open_ports={554})
    assert result in ("Video Doorbell / Intercom", "IP Camera")


def test_nest_doorbell_with_8443_port():
    # Port 8443 is Nest's video-stream port — confirms doorbell, not caught by
    # the generic IP Camera port rule (which only matches 554/8554).
    result = classify(vendor="Nest Labs", hostname="", open_ports={8443})
    assert result == "Video Doorbell / Intercom"


def test_ring_doorbell_still_works():
    # Removing nest from the shared vendor_re must not break Ring.
    result = classify(vendor="Ring Inc.", hostname="", open_ports=set())
    assert result == "Video Doorbell / Intercom"


def test_arlo_doorbell_still_works():
    result = classify(vendor="Arlo Technologies", hostname="", open_ports=set())
    assert result == "Video Doorbell / Intercom"


# ── P0-2: Wearable classification ───────────────────────────────────────────

def test_garmin_classified_as_wearable():
    result = classify(vendor="Garmin International Inc.", hostname="", open_ports=set())
    assert result == "Wearable"


def test_fitbit_classified_as_wearable():
    result = classify(vendor="Fitbit Inc.", hostname="", open_ports=set())
    assert result == "Wearable"


def test_suunto_classified_as_wearable():
    result = classify(vendor="Suunto Oy", hostname="", open_ports=set())
    assert result == "Wearable"


def test_wearable_label_in_get_all_device_types():
    from modules.device_classifier import get_all_device_types
    assert "Wearable" in get_all_device_types()


# ── P1-1: Smart Speaker label canonical fix ──────────────────────────────────

def test_smart_speaker_canonical_label_not_display():
    # "Smart Speaker / Display" was the old label; canonical is now "Smart Speaker"
    result = classify(vendor="Amazon", hostname="echo-dot", open_ports=set())
    assert result == "Smart Speaker"
    assert result != "Smart Speaker / Display"


def test_smart_speaker_google_home():
    result = classify(vendor="Google", hostname="google-home-mini", open_ports=set())
    assert result == "Smart Speaker"
    assert result != "Smart Speaker / Display"


def test_sonos_not_captured_by_smart_speaker_rule():
    # Sonos should fall through to "Smart Speaker / Audio", not "Smart Speaker"
    result = classify(vendor="Sonos", hostname="sonos-living-room", open_ports=set())
    assert result == "Smart Speaker / Audio"
    assert result != "Smart Speaker"


def test_smart_speaker_label_in_get_all_device_types():
    from modules.device_classifier import get_all_device_types
    types = get_all_device_types()
    assert "Smart Speaker" in types
    assert "Smart Speaker / Display" not in types


# ── P1-2: Smart Plug rules ────────────────────────────────────────────────────

def test_shelly_vendor_classified_as_smart_plug():
    result = classify(vendor="Allterco Robotics", hostname="", open_ports=set())
    assert result == "Smart Plug"
    assert result != "IoT Device"


def test_shelly_hostname_classified_as_smart_plug():
    result = classify(vendor="", hostname="shellyplug-s-abc123", open_ports=set())
    assert result == "Smart Plug"
    assert result != "IoT Device"


def test_shelly_1pm_hostname_classified_as_smart_plug():
    result = classify(vendor="Allterco Robotics", hostname="shelly1pm-abc", open_ports=set())
    assert result == "Smart Plug"
    assert result != "IoT Device"


def test_tplink_kasa_port_9999_classified_as_smart_plug():
    # TP-Link with Kasa local-control API port → Smart Plug, not Router
    result = classify(vendor="TP-Link", hostname="", open_ports={9999})
    assert result == "Smart Plug"
    assert result != "Router / Gateway"


def test_tplink_router_without_port_9999_not_smart_plug():
    # TP-Link with standard web ports → still Router / Gateway
    result = classify(vendor="TP-Link", hostname="", open_ports={80, 443})
    assert result == "Router / Gateway"
    assert result != "Smart Plug"


def test_kasa_hostname_classified_as_smart_plug():
    result = classify(vendor="", hostname="kasa-plug-kitchen", open_ports=set())
    assert result == "Smart Plug"
    assert result != "IoT Device"


def test_hs110_kasa_model_hostname():
    result = classify(vendor="", hostname="hs110-living-room", open_ports=set())
    assert result == "Smart Plug"
    assert result != "IoT Device"


# ── P1-2: Smart Bulb rules ────────────────────────────────────────────────────

def test_lifx_vendor_classified_as_smart_bulb():
    result = classify(vendor="LIFX Inc.", hostname="", open_ports=set())
    assert result == "Smart Bulb"
    assert result != "IoT Device"


def test_govee_vendor_classified_as_smart_bulb():
    result = classify(vendor="Govee", hostname="", open_ports=set())
    assert result == "Smart Bulb"
    assert result != "IoT Device"


def test_shelly_dimmer_hostname_classified_as_smart_bulb():
    result = classify(vendor="", hostname="shellydimmer-abc123", open_ports=set())
    assert result == "Smart Bulb"
    assert result != "Smart Plug"
    assert result != "IoT Device"


def test_shellyrgbw_hostname_classified_as_smart_bulb():
    result = classify(vendor="", hostname="shellyrgbw2-kitchen", open_ports=set())
    assert result == "Smart Bulb"
    assert result != "IoT Device"


# ── P1-3: Thermostat rules ────────────────────────────────────────────────────

def test_ecobee_vendor_classified_as_thermostat():
    result = classify(vendor="Ecobee Technologies", hostname="", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "IoT Device"


def test_ecobee_hostname_classified_as_thermostat():
    result = classify(vendor="", hostname="ecobee-thermostat-hall", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "IoT Device"


def test_tado_vendor_classified_as_thermostat():
    result = classify(vendor="Tado GmbH", hostname="", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "IoT Device"


def test_tado_hostname_classified_as_thermostat():
    result = classify(vendor="", hostname="tado-thermostat-01.local", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "IoT Device"


def test_honeywell_thermostat_not_ics():
    # Honeywell T-series thermostat hostname must NOT fall to Industrial / ICS.
    result = classify(vendor="Honeywell International", hostname="lyric-thermostat", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "Industrial / ICS Device"


def test_honeywell_evohome_not_ics():
    result = classify(vendor="Honeywell", hostname="evohome-controller", open_ports=set())
    assert result == "Smart Thermostat"
    assert result != "Industrial / ICS Device"


def test_honeywell_plc_without_thermostat_hostname_is_ics():
    # Honeywell with no thermostat-specific hostname must still reach ICS rule.
    result = classify(vendor="Honeywell", hostname="", open_ports=set())
    assert result == "Industrial / ICS Device"
    assert result != "Smart Thermostat"


def test_smart_plug_label_in_get_all_device_types():
    from modules.device_classifier import get_all_device_types
    assert "Smart Plug" in get_all_device_types()


def test_smart_bulb_label_in_get_all_device_types():
    from modules.device_classifier import get_all_device_types
    assert "Smart Bulb" in get_all_device_types()


def test_smart_thermostat_label_in_get_all_device_types():
    from modules.device_classifier import get_all_device_types
    assert "Smart Thermostat" in get_all_device_types()


# ── classify_registry_first (Phase 2c — unified registry-first entry point) ──

def test_classify_registry_first_uses_mac_registry_device_type():
    # 54:60:09 is a Google Chromecast OUI mapped to "Streaming Stick" in mac_registry.
    result = classify_registry_first(
        mac="54:60:09:aa:bb:cc", vendor="", hostname="", open_ports=set(),
    )
    assert result == "Streaming Stick"


def test_classify_registry_first_falls_back_to_classify_when_mac_unknown():
    result = classify_registry_first(
        mac="", vendor="Hikvision Digital Technology", hostname="", open_ports=set(),
    )
    assert result == "IP Camera"


def test_classify_registry_first_falls_back_when_mac_not_in_registry():
    result = classify_registry_first(
        mac="00:00:00:00:00:00", vendor="Hikvision Digital Technology",
        hostname="", open_ports=set(),
    )
    assert result == "IP Camera"


def test_classify_registry_first_respects_is_gateway():
    assert classify_registry_first(mac="", is_gateway=True) == "Router / Gateway"


# ---------------------------------------------------------------------------
# Hostname rules must not match inside an unrelated word
# ---------------------------------------------------------------------------
#
# Every hostname_re is applied with a bare re.search(), so a short alternative
# matches anywhere inside the name -- including inside a person's name. Measured
# live before the fix, against the real shipped classifier:
#
#   iPad-2           -> Domain Controller   ("iPAD-2" contains "ad-")
#   Jonas-PC         -> File / NAS Server   ("joNAS")
#   Camilla-iPhone   -> IP Camera           ("CAMilla")
#   Vlad-PC          -> Domain Controller
#   BRAD-WORKSTATION -> Domain Controller
#   natverk-printer  -> Smart TV            ("naTVerk", Swedish for "network")
#
# `iPad-2` was live in the reference network's inventory, shown to the user as a
# Domain Controller. Rules are first-match-wins, so one over-broad alternative
# early in the list also pre-empts every correct rule after it.

_PERSONAL_NAMES = [
    # English
    "Adam", "Brad", "Brian", "Camilla", "Chad", "Daniel", "David", "Edward",
    "Emma", "Grace", "Hannah", "Ian", "Jonas", "Jonathan", "Laura", "Madeline",
    "Nathan", "Oliver", "Rachel", "Thomas", "Vlad", "William",
    # Swedish / Nordic
    "Anders", "Annika", "Bengt", "Birgitta", "Bjorn", "Elin", "Erik", "Gunnar",
    "Hakan", "Ingrid", "Johan", "Karin", "Lars", "Lovisa", "Magnus", "Nils",
    "Ossian", "Per", "Sigrid", "Sven", "Ulrika", "Viktor",
    # Other common given names
    "Ahmed", "Aisha", "Chen", "Fatima", "Hassan", "Ivan", "Nasrin", "Priya",
    "Sofia", "Yusuf",
]

# Labels a device named after a person must never be given. Deliberately a
# denylist of infrastructure/appliance types rather than an exact-match on
# "Unknown Device": a personal machine legitimately classifying as a computer
# is correct, and this test must not have to change when that becomes possible.
_NOT_A_PERSONAL_DEVICE = {
    "Domain Controller", "File / NAS Server", "IP Camera", "Print Server",
    "Smart TV", "Streaming Stick", "Mesh Network Node", "Router / Gateway",
    "Network Switch", "Wireless Access Point", "Mail Server", "Web / App Server",
    "Video Doorbell / Intercom", "Smart Thermostat", "Smart Plug", "Smart Bulb",
    "Smart Speaker / Audio", "Games Console", "Smart Home Hub",
}


def test_a_device_named_after_a_person_is_not_classified_as_infrastructure():
    """The invariant: a hostname rule must not fire on a substring of a name."""
    offenders = []
    for name in _PERSONAL_NAMES:
        for hostname in (name, f"{name}-PC", f"{name}s-Laptop", f"{name}-Desktop"):
            result = classify_with_evidence(vendor="", hostname=hostname)
            if result.device_type in _NOT_A_PERSONAL_DEVICE:
                offenders.append(f"{hostname} -> {result.device_type}")

    assert not offenders, (
        f"{len(offenders)} hostname(s) built from a person's name matched a "
        f"device rule as a substring:\n  " + "\n  ".join(offenders)
    )


def test_ipad_hostname_is_not_a_domain_controller():
    """The exact row that was live in the reference inventory.

    'iPad-2' contains 'ad-', an alternative of the Domain Controller rule.
    """
    result = classify_with_evidence(vendor="", hostname="iPad-2")
    assert result.device_type != "Domain Controller"
    assert result.device_type == "iPhone / iPad"


def test_a_real_device_word_wins_over_a_substring_match_elsewhere_in_the_name():
    """Rules are first-match-wins, so an over-broad alternative early in the
    list silently pre-empts the correct rule later in it."""
    assert classify_with_evidence(
        vendor="", hostname="natverk-printer"
    ).device_type == "Print Server"
    assert classify_with_evidence(
        vendor="", hostname="natverk-nas"
    ).device_type == "File / NAS Server"


def test_genuine_device_hostnames_still_classify():
    """The other half of the invariant: anchoring must not stop real matches.

    Every one of these is the kind of name the loosened alternatives exist for.
    """
    cases = {
        "nas-01":            "File / NAS Server",
        "diskstation":       "File / NAS Server",
        "cam-frontdoor":     "IP Camera",
        "ipcam-01":          "IP Camera",
        "nvr-basement":      "IP Camera",
        "tv-livingroom":     "Smart TV",
        "roku-bedroom":      "Smart TV",
        "dc01":              "Domain Controller",
        "ad-server":         "Domain Controller",
        "domaincontroller1": "Domain Controller",
    }
    wrong = {
        h: classify_with_evidence(vendor="", hostname=h).device_type
        for h, expected in cases.items()
        if classify_with_evidence(vendor="", hostname=h).device_type != expected
    }
    assert not wrong, f"anchoring broke genuine matches: {wrong}"


# ---------------------------------------------------------------------------
# Ordinary computers had no classification path at all
# ---------------------------------------------------------------------------
#
# Measured before this rule: Intel Corporate, Dell, Lenovo, ASUSTek and
# Micro-Star all classified as Unknown Device at confidence 0.0, evidence
# "no-rule-matched" -- the single most common device class on any network. The
# existing "Windows PC" rule requires os_re "windows" AND ports {445,3389,5900},
# none of which a passive scan has. On the reference network this was most of
# the rows blocking the identity program's >=90% confidence-coverage target.

def test_a_pc_nic_vendor_classifies_as_a_computer():
    """These vendors put their OUI on client NICs and do not sell consumer
    routers, so the vendor alone is real evidence of a computer."""
    for vendor in ("Intel Corporate", "Dell Inc.", "LENOVO", "Micro-Star INTL",
                   "GIGA-BYTE TECHNOLOGY CO.,LTD."):
        result = classify_with_evidence(vendor=vendor, hostname="")
        assert result.device_type == "Computer / Workstation", (
            f"{vendor!r} -> {result.device_type!r}"
        )
        assert 0.0 < result.confidence <= 0.4, (
            "a NIC vendor is weak evidence and must not outrank a hostname or "
            "registry match"
        )


def test_a_vendor_that_also_makes_routers_is_not_called_a_computer():
    """The invariant behind the rule, not the rule's membership list.

    ASUSTek sells motherboards AND some of the most common consumer routers on
    the same OUIs, so the vendor alone proves nothing about which it is. The
    reference network has exactly such a device and its owner could not say
    which it was either -- that is the signal to leave it unclassified.
    """
    result = classify_with_evidence(vendor="ASUSTek COMPUTER INC.", hostname="")
    assert result.device_type != "Computer / Workstation"


def test_a_specific_hostname_still_beats_the_generic_computer_rule():
    """The rule sits last, so it fills a gap rather than pre-empting anything."""
    assert classify_with_evidence(
        vendor="Intel Corporate", hostname="nas-01"
    ).device_type == "File / NAS Server"
    assert classify_with_evidence(
        vendor="Intel Corporate", hostname="office-printer"
    ).device_type == "Print Server"


# ---------------------------------------------------------------------------
# HP sells laptops, printers and servers on the same vendor string
# ---------------------------------------------------------------------------

def test_hp_alone_is_not_a_print_server():
    """Measured: "Hewlett Packard" -> Print Server at 0.4, so every HP laptop
    on the network was a printer. Unlike Brother or Lexmark, HP's LAN presence
    is mostly not printers."""
    result = classify_with_evidence(vendor="Hewlett Packard", hostname="")
    assert result.device_type != "Print Server"


def test_hp_with_corroboration_is_a_print_server():
    """The claim is fine once something else supports it."""
    assert classify_with_evidence(
        vendor="Hewlett Packard", hostname="", open_ports={9100}
    ).device_type == "Print Server"
    assert classify_with_evidence(
        vendor="Hewlett Packard", hostname="hp-officejet-pro"
    ).device_type == "Print Server"


def test_unambiguous_printer_vendors_still_match_on_vendor_alone():
    """Brother and Lexmark are printer companies; the HP fix must not
    over-correct into them."""
    for vendor in ("Brother Industries", "Lexmark International"):
        assert classify_with_evidence(
            vendor=vendor, hostname=""
        ).device_type == "Print Server", vendor

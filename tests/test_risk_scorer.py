"""
Tests for modules/risk_scorer.py — pure logic, no network calls.
"""
from modules.risk_scorer import (
    score_device, score_devices, RiskAssessment, _band, CRITICAL, HIGH, MEDIUM, LOW, INFO,
)


# ── Band function ──────────────────────────────────────────────────────────────

class TestBand:
    def test_critical(self):
        assert _band(80) == CRITICAL
        assert _band(100) == CRITICAL
        assert _band(99) == CRITICAL

    def test_high(self):
        assert _band(60) == HIGH
        assert _band(79) == HIGH

    def test_medium(self):
        assert _band(35) == MEDIUM
        assert _band(59) == MEDIUM

    def test_low(self):
        assert _band(10) == LOW
        assert _band(34) == LOW

    def test_info(self):
        assert _band(0) == INFO
        assert _band(9) == INFO


# ── score_device — clean device ────────────────────────────────────────────────

class TestScoreDeviceClean:
    def test_returns_risk_assessment(self):
        result = score_device("192.168.1.1")
        assert isinstance(result, RiskAssessment)

    def test_clean_device_low_score(self):
        result = score_device("192.168.1.1", mac="aa:bb:cc:dd:ee:ff", vendor="Unknown")
        assert result.total_score >= 0
        assert result.total_score <= 100

    def test_no_ports_no_findings(self):
        result = score_device("192.168.1.1", open_ports=[])
        # No port-based findings
        port_findings = [f for f in result.findings if f.title.startswith("Port")]
        assert len(port_findings) == 0

    def test_ip_preserved(self):
        result = score_device("10.0.0.5", mac="11:22:33:44:55:66")
        assert result.ip == "10.0.0.5"
        assert result.mac == "11:22:33:44:55:66"


# ── score_device — dangerous ports ─────────────────────────────────────────────

class TestScoreDevicePorts:
    def test_telnet_adds_score(self):
        result = score_device("192.168.1.1", open_ports=[23])
        assert result.total_score >= 25
        titles = [f.title for f in result.findings]
        assert any("23" in t for t in titles)

    def test_rdp_adds_score(self):
        result = score_device("192.168.1.1", open_ports=[3389])
        assert result.total_score >= 25

    def test_smb_adds_score(self):
        result = score_device("192.168.1.1", open_ports=[445])
        assert result.total_score >= 25

    def test_multiple_dangerous_ports_accumulate(self):
        clean = score_device("192.168.1.1", open_ports=[])
        risky = score_device("192.168.1.1", open_ports=[23, 445, 3389])
        assert risky.total_score > clean.total_score

    def test_benign_port_no_score(self):
        result = score_device("192.168.1.1", open_ports=[80])
        port_findings = [f for f in result.findings if "Port" in f.title]
        assert len(port_findings) == 0

    def test_score_capped_at_100(self):
        result = score_device(
            "192.168.1.1",
            open_ports=[23, 445, 3389, 5900, 7547, 1883, 21],
            m1_risk_level="HIGH",
            device_type="IP Camera",
        )
        assert result.total_score <= 100

    def test_mqtt_finding_text(self):
        result = score_device("192.168.1.1", open_ports=[1883])
        mqtt_findings = [f for f in result.findings if "1883" in f.title]
        assert len(mqtt_findings) == 1
        assert "MQTT" in mqtt_findings[0].title


# ── score_device — device type ─────────────────────────────────────────────────

class TestScoreDeviceType:
    def test_ip_camera_adds_score(self):
        base = score_device("192.168.1.1")
        with_type = score_device("192.168.1.1", device_type="IP Camera")
        assert with_type.total_score > base.total_score

    def test_ics_device_high_modifier(self):
        result = score_device("192.168.1.1", device_type="Industrial / ICS Device")
        type_findings = [f for f in result.findings if "Device type" in f.title]
        assert len(type_findings) == 1
        assert type_findings[0].score_contribution == 20

    def test_unknown_type_no_modifier(self):
        result = score_device("192.168.1.1", device_type="Toaster")
        type_findings = [f for f in result.findings if "Device type" in f.title]
        assert len(type_findings) == 0


# ── score_device — OUI risk level ─────────────────────────────────────────────

class TestScoreDeviceOUI:
    def test_high_oui_adds_20(self):
        clean = score_device("192.168.1.1")
        flagged = score_device("192.168.1.1", m1_risk_level="HIGH", vendor="BadVendor")
        assert flagged.total_score - clean.total_score == 20

    def test_medium_oui_adds_10(self):
        clean = score_device("192.168.1.1")
        flagged = score_device("192.168.1.1", m1_risk_level="MEDIUM")
        assert flagged.total_score - clean.total_score == 10

    def test_clean_oui_no_addition(self):
        clean = score_device("192.168.1.1")
        also_clean = score_device("192.168.1.1", m1_risk_level="CLEAN")
        assert clean.total_score == also_clean.total_score

    def test_known_issues_appear_in_finding(self):
        result = score_device(
            "192.168.1.1",
            m1_risk_level="HIGH",
            vendor="FlaggedCo",
            known_issues=["Backdoor in firmware", "Default creds"],
        )
        vendor_findings = [f for f in result.findings if "Vendor risk" in f.title]
        assert len(vendor_findings) == 1
        assert "Backdoor" in vendor_findings[0].impact


# ── score_device — link-local ─────────────────────────────────────────────────

class TestScoreDeviceLinkLocal:
    def test_link_local_adds_15(self):
        ll = score_device("169.254.10.5")
        assert ll.total_score >= 15

    def test_link_local_finding_present(self):
        result = score_device("169.254.1.1")
        ll_findings = [f for f in result.findings if "Link-local" in f.title]
        assert len(ll_findings) == 1


# ── score_device — severity bands ─────────────────────────────────────────────

class TestScoreDeviceSeverity:
    def test_severity_matches_score(self):
        result = score_device("192.168.1.1", open_ports=[23, 445, 3389])
        assert result.severity == _band(result.total_score)

    def test_info_severity_clean_device(self):
        result = score_device("192.168.1.1")
        assert result.severity in (INFO, LOW, MEDIUM)

    def test_fields_populated(self):
        result = score_device(
            "192.168.1.100",
            mac="de:ad:be:ef:00:01",
            hostname="evil-cam",
            vendor="AcmeCam",
            device_type="IP Camera",
            os_family="Linux",
            open_ports=[23, 5900],
        )
        assert result.hostname == "evil-cam"
        assert result.vendor == "AcmeCam"
        assert result.os_family == "Linux"
        assert result.device_type == "IP Camera"
        assert len(result.findings) >= 2  # port + device type


# ── score_device — credential_access (F-46: Login Test -> Device Risk Score) ──

class TestScoreDeviceCredentialAccess:
    def test_default_no_credential_finding(self):
        result = score_device("192.168.1.1")
        cred_findings = [f for f in result.findings if "credentials" in f.title.lower()]
        assert cred_findings == []

    def test_credential_access_adds_finding_and_score(self):
        clean = score_device("192.168.1.1")
        flagged = score_device("192.168.1.1", credential_access=True)
        assert flagged.total_score > clean.total_score
        cred_findings = [f for f in flagged.findings if "credentials" in f.title.lower()]
        assert len(cred_findings) == 1
        assert cred_findings[0].score_contribution == 35

    def test_credential_access_pushes_severity_up(self):
        result = score_device("192.168.1.1", credential_access=True)
        assert result.severity in (MEDIUM, HIGH, CRITICAL)


# ── score_devices — credential_hosts wiring ────────────────────────────────────

class TestScoreDevicesCredentialHosts:
    def test_matching_ip_gets_credential_finding(self):
        devices = [{"ip": "192.168.1.50"}, {"ip": "192.168.1.51"}]
        results = {a.ip: a for a in score_devices(devices, credential_hosts={"192.168.1.50"})}
        cred_findings_50 = [f for f in results["192.168.1.50"].findings if "credentials" in f.title.lower()]
        cred_findings_51 = [f for f in results["192.168.1.51"].findings if "credentials" in f.title.lower()]
        assert len(cred_findings_50) == 1
        assert len(cred_findings_51) == 0

    def test_no_credential_hosts_no_findings(self):
        devices = [{"ip": "192.168.1.50"}]
        results = score_devices(devices)
        cred_findings = [f for f in results[0].findings if "credentials" in f.title.lower()]
        assert cred_findings == []

    def test_object_style_devices_also_matched(self):
        class _Dev:
            def __init__(self, ip):
                self.ip = ip
                self.mac = self.hostname = self.vendor = self.device_type = self.os_family = ""
                self.open_ports = []
                self.risk_level = ""
                self.known_issues = []

        results = {a.ip: a for a in score_devices([_Dev("10.0.0.5")], credential_hosts={"10.0.0.5"})}
        cred_findings = [f for f in results["10.0.0.5"].findings if "credentials" in f.title.lower()]
        assert len(cred_findings) == 1

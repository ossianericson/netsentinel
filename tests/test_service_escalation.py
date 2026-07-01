"""Tests for modules/service_escalation.py — SERVICE_DOWN root-cause escalation.

Covers: per-host/port cooldown (RULE-T1), failure_layer -> plain-English
message + canonical UI severity mapping (RULE-A3), and the host:port key
parser used by app.py to recover the original ServiceDiagnosticsWorker target.
"""


def test_import():
    from modules.service_escalation import (
        ServiceEscalationTracker, layer_to_message, parse_service_key,
        to_alert_severity,
    )
    assert ServiceEscalationTracker is not None
    assert layer_to_message is not None
    assert parse_service_key is not None
    assert to_alert_severity is not None


# ── ServiceEscalationTracker — per-host/port cooldown ──────────────────────────

def test_tracker_allows_first_escalation():
    from modules.service_escalation import ServiceEscalationTracker
    tracker = ServiceEscalationTracker(cooldown_s=600)
    assert tracker.should_escalate("192.168.1.1", 80, now=1000.0) is True


def test_tracker_blocks_within_cooldown():
    """A flapping service must not be re-diagnosed more than once per window."""
    from modules.service_escalation import ServiceEscalationTracker
    tracker = ServiceEscalationTracker(cooldown_s=600)
    tracker.mark_escalated("192.168.1.1", 80, now=1000.0)
    assert tracker.should_escalate("192.168.1.1", 80, now=1300.0) is False


def test_tracker_allows_after_cooldown_elapsed():
    from modules.service_escalation import ServiceEscalationTracker
    tracker = ServiceEscalationTracker(cooldown_s=600)
    tracker.mark_escalated("192.168.1.1", 80, now=1000.0)
    assert tracker.should_escalate("192.168.1.1", 80, now=1601.0) is True


def test_tracker_cooldown_is_per_host_port():
    """A different host or port is an independent cooldown window."""
    from modules.service_escalation import ServiceEscalationTracker
    tracker = ServiceEscalationTracker(cooldown_s=600)
    tracker.mark_escalated("192.168.1.1", 80, now=1000.0)
    assert tracker.should_escalate("192.168.1.1", 443, now=1000.0) is True
    assert tracker.should_escalate("192.168.1.2", 80, now=1000.0) is True


# ── parse_service_key ───────────────────────────────────────────────────────────

def test_parse_service_key_splits_host_and_port():
    from modules.service_escalation import parse_service_key
    host, port = parse_service_key("192.168.1.1:80")
    assert host == "192.168.1.1"
    assert port == 80


def test_parse_service_key_hostname():
    from modules.service_escalation import parse_service_key
    host, port = parse_service_key("plex.example.com:32400")
    assert host == "plex.example.com"
    assert port == 32400


def test_parse_service_key_malformed_returns_empty_host():
    from modules.service_escalation import parse_service_key
    host, port = parse_service_key("not-a-valid-key")
    assert host == ""
    assert port == 0


# ── layer_to_message — failure_layer -> plain English + UI severity ────────────

def test_layer_to_message_filtered_is_warning_not_outage():
    """The core Sprint 1 incident: filtered != a real outage."""
    from modules.service_escalation import layer_to_message
    severity, message = layer_to_message("filtered", "192.168.1.1", 443)
    assert severity == "Warning"
    assert "firewall" in message.lower() or "block" in message.lower()
    assert "not a real outage" in message.lower()


def test_layer_to_message_remote_outage_is_critical():
    from modules.service_escalation import layer_to_message
    severity, message = layer_to_message("remote_outage", "plex.example.com", 32400)
    assert severity == "Critical"
    assert "down" in message.lower()


def test_layer_to_message_uses_label_when_given():
    from modules.service_escalation import layer_to_message
    _, message = layer_to_message("filtered", "192.168.1.1", 443, label="Plex")
    assert message.startswith("Plex")


def test_layer_to_message_unknown_layer_falls_back_to_info():
    from modules.service_escalation import layer_to_message
    severity, message = layer_to_message("some_future_layer", "host", 1)
    assert severity == "Info"
    assert message


def test_layer_to_message_severity_is_canonical_ui_set():
    """RULE-A3: only Info/Warning/High/Critical are valid severity labels."""
    from modules.service_escalation import layer_to_message, _LAYER_INFO
    for layer in _LAYER_INFO:
        severity, _ = layer_to_message(layer, "host", 1)
        assert severity in ("Info", "Warning", "High", "Critical")


# ── to_alert_severity — UI label -> internal AlertFired.severity ───────────────

def test_to_alert_severity_maps_all_canonical_labels():
    from modules.service_escalation import to_alert_severity
    assert to_alert_severity("Info") == "INFO"
    assert to_alert_severity("Warning") == "WARNING"
    assert to_alert_severity("High") == "CRITICAL"
    assert to_alert_severity("Critical") == "CRITICAL"


def test_to_alert_severity_unknown_defaults_to_warning():
    from modules.service_escalation import to_alert_severity
    assert to_alert_severity("Nonsense") == "WARNING"


# ── is_filtered_message — Sprint 4 digest bullet support ────────────────────────

def test_is_filtered_message_true_for_filtered_layer_message():
    from modules.service_escalation import is_filtered_message, layer_to_message
    _, message = layer_to_message("filtered", "example.com", 443)
    assert is_filtered_message(message) is True


def test_is_filtered_message_false_for_other_layers():
    from modules.service_escalation import is_filtered_message, layer_to_message
    _, message = layer_to_message("remote_outage", "example.com", 443)
    assert is_filtered_message(message) is False


def test_is_filtered_message_false_for_unrelated_text():
    from modules.service_escalation import is_filtered_message
    assert is_filtered_message("some unrelated message") is False

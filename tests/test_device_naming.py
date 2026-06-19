"""Tests for modules/device_naming.py (S5-1)."""

from modules.device_naming import suggest_device_name


def test_prefers_real_hostname():
    assert suggest_device_name("kitchen-tv", "Sony", "Smart TV") == "kitchen-tv"


def test_falls_back_to_vendor_and_type():
    assert suggest_device_name("", "Sony", "Smart TV") == "Sony Smart TV"


def test_unknown_hostname_treated_as_missing():
    assert suggest_device_name("unknown", "Apple", "Smart Speaker") == "Apple Smart Speaker"


def test_falls_back_to_vendor_only():
    assert suggest_device_name("", "Apple", "") == "Apple"


def test_falls_back_to_type_only():
    assert suggest_device_name("", "", "Smart TV") == "Smart TV"


def test_unknown_device_type_not_used_alone():
    assert suggest_device_name("", "", "Unknown Device") == "Unnamed Device"


def test_generic_fallback_when_nothing_useful():
    assert suggest_device_name("", "", "") == "Unnamed Device"


def test_strips_whitespace():
    assert suggest_device_name("  my-laptop  ", "", "") == "my-laptop"

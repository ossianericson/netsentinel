"""modules/device_classifier_rules.py — the _RULES table (RULE-T1).

Split out of device_classifier.py to keep that module inside the RULE-AH1 budget.
These tests guard the split itself: that the table still imports, still carries the
shape device_classifier.py's evaluation loop assumes, and did not lose entries on
the way across.
"""
from modules.device_classifier_rules import _RULES

# Every key the evaluation loop in device_classifier.classify_with_evidence()
# branches on. A rule carrying anything else is a typo that would silently never
# match -- the loop only ever *skips* on a key it knows.
_KNOWN_KEYS = {
    "label", "vendor_re", "hostname_re", "os_re", "ports", "any_ports", "any_ports_b",
}


def test_rules_table_imports_and_is_non_empty():
    """79 is the count carried across the split, verified against the pre-split
    file. A ratchet, not a ceiling: adding a device signature should raise it."""
    assert isinstance(_RULES, list)
    assert len(_RULES) >= 79, "the table lost entries"


def test_every_rule_has_a_label():
    for i, rule in enumerate(_RULES):
        assert rule.get("label"), f"_RULES[{i}] has no label: {rule!r}"


def test_every_rule_has_at_least_one_discriminator():
    """A rule with only a label matches everything and would shadow the whole
    rest of the table from wherever it sits."""
    for i, rule in enumerate(_RULES):
        discriminators = set(rule) - {"label"}
        assert discriminators, f"_RULES[{i}] has no discriminator: {rule!r}"


def test_no_rule_carries_an_unrecognised_key():
    for i, rule in enumerate(_RULES):
        unknown = set(rule) - _KNOWN_KEYS
        assert not unknown, f"_RULES[{i}] has unrecognised key(s) {unknown}: {rule!r}"


def test_port_fields_are_sets_of_ints():
    """`ports` is used with .issubset() and `any_ports` with .intersection();
    a list would raise, a set of strings would silently never match."""
    for i, rule in enumerate(_RULES):
        for key in ("ports", "any_ports", "any_ports_b"):
            if key not in rule:
                continue
            assert isinstance(rule[key], set), f"_RULES[{i}][{key!r}] is not a set"
            assert all(isinstance(p, int) for p in rule[key]), \
                f"_RULES[{i}][{key!r}] holds a non-int port"


def test_regex_fields_compile():
    import re

    for i, rule in enumerate(_RULES):
        for key in ("vendor_re", "hostname_re", "os_re"):
            if key in rule:
                re.compile(rule[key])  # raises re.error on a malformed pattern


def test_device_classifier_uses_this_table():
    """The split must not leave a second copy behind in the original module."""
    from modules import device_classifier

    assert device_classifier._RULES is _RULES

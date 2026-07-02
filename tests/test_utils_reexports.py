"""
Guards RULE (Phase 1 of the duplicate-collection remediation): modules/utils.py
must re-export the canonical lookup/resolver/classifier helpers as the *same*
objects as their source modules — not copies — so callers importing from
either location get identical behaviour and the import graph stays acyclic.
"""
from modules import utils
from modules import mac_lookup
from modules import name_resolver
from modules import device_classifier


def test_lookup_vendor_is_canonical():
    assert utils.lookup_vendor is mac_lookup.lookup_vendor


def test_resolved_name_is_canonical():
    assert utils.ResolvedName is name_resolver.ResolvedName


def test_resolve_is_canonical():
    assert utils.resolve is name_resolver.resolve


def test_resolve_batch_is_canonical():
    assert utils.resolve_batch is name_resolver.resolve_batch


def test_classify_is_canonical():
    assert utils.classify is device_classifier.classify


def test_classify_device_is_canonical():
    assert utils.classify_device is device_classifier.classify_device


def test_classify_with_evidence_is_canonical():
    assert utils.classify_with_evidence is device_classifier.classify_with_evidence


def test_classify_registry_first_is_canonical():
    assert utils.classify_registry_first is device_classifier.classify_registry_first


def test_all_reexports_listed_in_dunder_all():
    for name in (
        "lookup_vendor", "ResolvedName", "resolve", "resolve_batch",
        "classify", "classify_device", "classify_with_evidence", "classify_registry_first",
    ):
        assert name in utils.__all__

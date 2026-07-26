"""Tests for scripts/vt_scan.py — RULE-REL1 classification and engine extraction.

No network calls: only the pure `classify()` / `flagging_engines()` functions are
exercised, using sample VT API response shapes.
"""

from __future__ import annotations

import importlib

import scripts.vt_scan as vt_scan


def test_classify_zero_hits_is_clean():
    assert vt_scan.classify({"malicious": 0, "suspicious": 0, "harmless": 90}) == "clean"


def test_classify_at_threshold_is_flagged():
    # Default SOFT_FLAG_MAX is 2 — this is the exact incident shape (1 malicious / 92 engines).
    assert vt_scan.classify({"malicious": 1, "suspicious": 0}) == "flagged"


def test_classify_combined_at_threshold_is_still_flagged():
    assert vt_scan.classify({"malicious": 1, "suspicious": 1}) == "flagged"


def test_classify_above_threshold_is_blocked():
    assert vt_scan.classify({"malicious": 2, "suspicious": 1}) == "blocked"


def test_classify_many_malicious_is_blocked():
    assert vt_scan.classify({"malicious": 10, "suspicious": 0}) == "blocked"


def test_soft_flag_max_env_override(monkeypatch):
    monkeypatch.setenv("VT_SOFT_FLAG_MAX", "0")
    reloaded = importlib.reload(vt_scan)
    try:
        assert reloaded.classify({"malicious": 1, "suspicious": 0}) == "blocked"
    finally:
        monkeypatch.delenv("VT_SOFT_FLAG_MAX", raising=False)
        importlib.reload(vt_scan)  # restore default for any other test in this process


def test_flagging_engines_filters_and_sorts():
    results = {
        "EngineB": {"category": "malicious", "engine_name": "EngineB"},
        "EngineA": {"category": "suspicious", "engine_name": "EngineA"},
        "EngineC": {"category": "harmless", "engine_name": "EngineC"},
        "EngineD": {"category": "undetected", "engine_name": "EngineD"},
    }
    assert vt_scan.flagging_engines(results) == ["EngineA", "EngineB"]


def test_flagging_engines_empty_when_none_flagged():
    results = {"EngineA": {"category": "harmless"}, "EngineB": {"category": "undetected"}}
    assert vt_scan.flagging_engines(results) == []

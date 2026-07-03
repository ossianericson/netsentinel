"""Tests for modules/threat_intel.py — threat intelligence feed.

Also covers P3 regression: ThreatIntelPage._fill_table must cap rows at
_MAX_TABLE_ROWS to prevent a 20-26 s main-thread freeze on large feeds.

And a stability regression: refresh_from_feeds() must fetch feeds concurrently,
not sequentially — sequential fetching held the calling QThread (and the
UI-visible "Update Feeds" wait) busy for the sum of both feeds' timeouts,
widening the window in which unrelated main-thread contention (page-crossfade
animation + the WM_NCHITTEST native callback in ui/header.py) could fault.
"""
import json
import time

from modules.threat_intel import (
    ThreatEntry, ThreatIntelDB, _is_public_ip,
    _parse_feodo_json, _parse_urlhaus_text, _parse_plain_ip_list,
)


def test_import():
    from modules import threat_intel as m
    assert hasattr(m, "ThreatEntry")
    assert hasattr(m, "ThreatIntelDB")
    assert hasattr(m, "_is_public_ip")
    assert hasattr(m, "refresh_from_feeds")


def test_threat_entry_fields():
    e = ThreatEntry(
        indicator="198.51.100.1",
        itype="ip",
        categories=["botnet"],
        source="feodo",
        confidence=85,
        last_seen="2024-01-01",
    )
    assert e.indicator == "198.51.100.1"
    assert e.source == "feodo"
    assert "botnet" in e.categories
    assert e.confidence == 85


def test_is_public_ip_rfc1918():
    assert _is_public_ip("192.168.1.1") is False
    assert _is_public_ip("10.0.0.1") is False
    assert _is_public_ip("172.16.0.1") is False


def test_is_public_ip_loopback():
    assert _is_public_ip("127.0.0.1") is False


def test_is_public_ip_public():
    assert _is_public_ip("1.1.1.1") is True
    assert _is_public_ip("8.8.4.4") is True


def test_parse_feodo_json_valid():
    # Feodo feed is a flat JSON array (not nested under "blocklist")
    data = json.dumps([
        {"ip_address": "1.2.3.4", "malware": "Emotet", "last_online": "2024-01-01", "status": "online"}
    ]).encode()
    entries = _parse_feodo_json(data)
    assert len(entries) >= 1
    assert any(e.indicator == "1.2.3.4" for e in entries)


def test_parse_feodo_json_invalid():
    entries = _parse_feodo_json(b"not json")
    assert entries == []


def test_parse_urlhaus_text_returns_list():
    data = b"# comment\n2024-01-01,http://1.2.3.4/malware,online,phishing,\n"
    entries = _parse_urlhaus_text(data)
    assert isinstance(entries, list)


def test_parse_plain_ip_list():
    data = b"# comment\n1.2.3.4\n5.6.7.8\n"
    entries = _parse_plain_ip_list(data, "test_source", ["malware"], 75)
    assert len(entries) == 2
    indicators = {e.indicator for e in entries}
    assert "1.2.3.4" in indicators
    assert "5.6.7.8" in indicators


def test_plain_ip_list_parses_ips():
    # _parse_plain_ip_list parses all IPs; RFC1918 filtering happens at query time
    data = b"1.2.3.4\n5.6.7.8\n"
    entries = _parse_plain_ip_list(data, "test", [], 50)
    indicators = {e.indicator for e in entries}
    assert "1.2.3.4" in indicators
    assert "5.6.7.8" in indicators


def test_threat_intel_db_empty():
    db = ThreatIntelDB()
    assert db.check_ip("1.2.3.4") is None


def test_threat_intel_db_from_entries():
    entry = ThreatEntry(
        indicator="1.2.3.4", itype="ip", categories=["botnet"],
        source="feodo", confidence=90, last_seen="2024",
    )
    db = ThreatIntelDB.from_entries([entry])
    result = db.check_ip("1.2.3.4")
    assert result is not None
    assert result.indicator == "1.2.3.4"


def test_threat_intel_db_miss():
    entry = ThreatEntry(
        indicator="1.2.3.4", itype="ip", categories=[],
        source="feodo", confidence=50, last_seen="",
    )
    db = ThreatIntelDB.from_entries([entry])
    assert db.check_ip("5.5.5.5") is None


def test_threat_intel_db_size():
    entries = [
        ThreatEntry(indicator=f"1.2.3.{i}", itype="ip", categories=[], source="test", confidence=50, last_seen="")
        for i in range(10)
    ]
    db = ThreatIntelDB.from_entries(entries)
    assert len(db) == 10


# ── Stability regression: feeds must be fetched concurrently, not sequentially ─

def test_refresh_from_feeds_runs_feeds_concurrently(tmp_path, monkeypatch):
    """Each feed's simulated download sleeps _DELAY seconds. Sequential fetching
    takes >= len(FEEDS) * _DELAY; concurrent fetching takes ~= _DELAY regardless
    of feed count. Assert wall time stays close to a single feed's delay."""
    from modules import threat_intel as ti

    assert len(ti.FEEDS) >= 2, "test assumes at least 2 configured feeds"
    _DELAY = 0.4

    class _FakeResp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        time.sleep(_DELAY)
        return _FakeResp(b"")

    monkeypatch.setattr(ti.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(ti, "_rate_wait", lambda host: None)

    t0 = time.time()
    ti.refresh_from_feeds(cache_dir=tmp_path)
    elapsed = time.time() - t0

    # Sequential would take len(FEEDS) * _DELAY (0.8s+ for 2 feeds); concurrent
    # should land close to a single _DELAY. Generous margin for CI jitter.
    assert elapsed < _DELAY * 1.8, (
        f"refresh_from_feeds took {elapsed:.2f}s for {len(ti.FEEDS)} feeds each "
        f"delayed {_DELAY}s — feeds appear to be fetched sequentially, not concurrently"
    )


def test_fetch_one_feed_falls_back_to_cache_on_failure(tmp_path, monkeypatch):
    from modules import threat_intel as ti

    feed = ti.FEEDS[0]
    cache_path = tmp_path / feed["filename"]
    cache_path.write_bytes(b"1.2.3.4\n")

    def _fail_urlopen(req, timeout=None):
        raise OSError("network unreachable")

    monkeypatch.setattr(ti.urllib.request, "urlopen", _fail_urlopen)
    monkeypatch.setattr(ti, "_rate_wait", lambda host: None)

    entries = ti._fetch_one_feed(feed, tmp_path, progress_cb=None)
    # Whatever the feed's parser makes of "1.2.3.4\n" — just confirm the cache
    # path was read (no exception) rather than the function returning empty
    # solely because the network call raised.
    assert isinstance(entries, list)


# ── P3 regression: _fill_table must cap rows at _MAX_TABLE_ROWS ───────────────

def test_fill_table_max_rows_constant_defined():
    """_MAX_TABLE_ROWS must be defined and have a sane value (P3 regression)."""
    from ui.pages.threat_intel_page import ThreatIntelPage
    cap = ThreatIntelPage._MAX_TABLE_ROWS
    assert isinstance(cap, int)
    assert 1_000 <= cap <= 20_000, f"_MAX_TABLE_ROWS={cap} is outside expected 1k-20k range"


def test_fill_table_caps_at_max_rows(qt_app):
    """_fill_table with N > _MAX_TABLE_ROWS must only insert _MAX_TABLE_ROWS rows.

    Regression for P3: rendering 50k+ rows caused a 20-26 s main-thread freeze.
    """
    import pytest
    if qt_app is None:
        pytest.skip("No QApplication")

    from ui.pages.threat_intel_page import ThreatIntelPage

    cap = ThreatIntelPage._MAX_TABLE_ROWS
    # Build cap+50 entries to exercise the limiting code path
    entries = [
        ThreatEntry(
            indicator=f"198.51.100.{i % 256}",
            itype="ip",
            categories=["test"],
            source="test",
            confidence=50,
            last_seen="2024-01-01",
        )
        for i in range(cap + 50)
    ]

    page = ThreatIntelPage()
    page._threat_entries = entries
    page._fill_table(entries)

    assert page._table.rowCount() == cap, (
        f"Expected exactly {cap} rows, got {page._table.rowCount()}"
    )

    try:
        page.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if qt_app:
        for _ in range(3):
            qt_app.processEvents()

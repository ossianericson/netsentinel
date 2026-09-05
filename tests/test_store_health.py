"""Tests for tools/store_health.py — the Partner Center failure puller (C1).

Why this tool exists: v2.2.8's regional hardening was driven by 13 Store failures across
en-AU, en-US, sv-SE, es-BO and hi-IN, and its own commit message says attribution to
those events is **unproven**. Every fix was a hypothesis fitted to a market code and a
count, because that is all Partner Center gives. This tool is what turns "we think we
fixed it" into a before/after measurement — and the API window is only 30 days, so data
not captured is gone permanently.

Only the pure parsing/summarising/rendering half is tested here. The HTTP half is a thin
urllib wrapper against a live authenticated endpoint; faking it would assert the shape of
a mock rather than anything about Partner Center.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]


def _load_store_health():
    """Load tools/store_health.py by path — tools/ is not an importable package.

    The module must be registered in ``sys.modules`` *before* it executes: it uses
    ``from __future__ import annotations``, so its dataclass field types are strings,
    and ``dataclasses`` resolves them via ``sys.modules[cls.__module__].__dict__``.
    Skipping the registration raises ``AttributeError: 'NoneType' object has no
    attribute '__dict__'`` at class-definition time.
    """
    spec = importlib.util.spec_from_file_location(
        "store_health", _REPO / "tools" / "store_health.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sh():
    return _load_store_health()


# A trimmed response in the documented failurehits shape. Field names and types are
# taken from the Microsoft Store analytics API reference, including the quirk that
# deviceCount/eventCount are floats, not ints.
_PAYLOAD = {
    "Value": [
        {
            "date": "2026-08-21",
            "applicationId": "9NZ124C7HJWS",
            "failureName": "STOWED_EXCEPTION_...NetSentinel.exe!unknown_error_in_application",
            "failureHash": "c21da75f-ea4d-538b-cfec-73654ef810b9",
            "eventType": "crash",
            "market": "IN",
            "osVersion": "Windows 11",
            "packageVersion": "2.2.7.0",
            "deviceCount": 3.0,
            "eventCount": 5.0,
        },
        {
            "date": "2026-08-22",
            "applicationId": "9NZ124C7HJWS",
            "failureName": "APPLICATION_HANG_...NetSentinel.exe!unknown_error_in_application",
            "failureHash": "233e04bb-7a3d-eb28-c316-1120aa9defc0",
            "eventType": "hang",
            "market": "SE",
            "osVersion": "Windows 11",
            "packageVersion": "2.2.7.0",
            "deviceCount": 1.0,
            "eventCount": 2.0,
        },
    ],
    "@nextLink": None,
    "TotalCount": 2,
}


def test_parse_failure_hits_reads_the_documented_response_shape(sh):
    rows = sh.parse_failure_hits(_PAYLOAD)

    assert len(rows) == 2
    first = rows[0]
    assert first.market == "IN"
    assert first.package_version == "2.2.7.0"
    assert first.event_type == "crash"
    assert first.event_count == 5.0
    assert first.device_count == 3.0


def test_summarize_groups_by_market_version_and_event_type(sh):
    """The breakdown the v2.2.8 question needs: did market X stop failing on version Y?"""
    rows = sh.parse_failure_hits(_PAYLOAD) + sh.parse_failure_hits(
        {"Value": [dict(_PAYLOAD["Value"][0], date="2026-08-23", eventCount=4.0,
                        deviceCount=2.0)]}
    )

    summary = sh.summarize(rows)

    assert summary[("IN", "2.2.7.0", "crash")].events == pytest.approx(9.0)
    assert summary[("IN", "2.2.7.0", "crash")].devices == pytest.approx(5.0)
    assert summary[("SE", "2.2.7.0", "hang")].events == pytest.approx(2.0)


def test_summarize_keeps_versions_apart_so_a_fix_is_visible(sh):
    """Collapsing versions would hide exactly the signal the tool exists to show."""
    rows = sh.parse_failure_hits({
        "Value": [
            dict(_PAYLOAD["Value"][0], packageVersion="2.2.7.0", eventCount=5.0),
            dict(_PAYLOAD["Value"][0], packageVersion="2.2.8.0", eventCount=1.0),
        ]
    })

    summary = sh.summarize(rows)
    assert summary[("IN", "2.2.7.0", "crash")].events == pytest.approx(5.0)
    assert summary[("IN", "2.2.8.0", "crash")].events == pytest.approx(1.0)


# Partner Center's Failures CSV export. Header names differ from the API's JSON keys,
# which is the whole reason this needs its own parser rather than a dict rename.
_CSV = (
    "Date,Failure Name,Failure Hash,Event Type,Market,OS Version,Package Version,"
    "Device Count,Event Count\r\n"
    "2026-08-21,STOWED_EXCEPTION_x,abc,crash,IN,Windows 11,2.2.7.0,3,5\r\n"
    "2026-08-22,APPLICATION_HANG_y,def,hang,SE,Windows 11,2.2.7.0,1,2\r\n"
)


def test_parse_failures_csv_matches_the_api_shape(sh):
    """Both inputs must produce the same rows, or the two paths would disagree."""
    rows = sh.parse_failures_csv(_CSV)

    assert len(rows) == 2
    assert rows[0].market == "IN"
    assert rows[0].event_type == "crash"
    assert rows[0].package_version == "2.2.7.0"
    assert rows[0].event_count == pytest.approx(5.0)
    assert rows[1].market == "SE"


def test_csv_headers_are_matched_case_and_space_insensitively(sh):
    """Partner Center has renamed these columns before; don't fail on cosmetics."""
    csv = (
        "date,failure name,event type,market,package version,event count,device count\r\n"
        "2026-08-21,X,crash,IN,2.2.8.0,4,2\r\n"
    )
    rows = sh.parse_failures_csv(csv)
    assert rows[0].market == "IN"
    assert rows[0].event_count == pytest.approx(4.0)


def test_diff_reports_resolved_new_and_changed_buckets(sh):
    """The actual deliverable: did 2.2.8 clear the markets 2.2.7 was failing in?"""
    before = sh.summarize(sh.parse_failures_csv(_CSV))
    after = sh.summarize(sh.parse_failures_csv(
        "Date,Failure Name,Event Type,Market,Package Version,Device Count,Event Count\r\n"
        "2026-09-01,STOWED_EXCEPTION_x,crash,IN,2.2.7.0,1,1\r\n"
        "2026-09-01,NEW_THING,crash,BR,2.2.8.0,2,3\r\n"
    ))

    d = sh.diff(before, after)

    assert ("SE", "2.2.7.0", "hang") in d.resolved     # gone entirely
    assert ("BR", "2.2.8.0", "crash") in d.new         # appeared
    assert ("IN", "2.2.7.0", "crash") in d.changed     # 5.0 -> 1.0
    assert d.changed[("IN", "2.2.7.0", "crash")] == pytest.approx(-4.0)


def test_render_markdown_shows_markets_versions_and_totals(sh):
    summary = sh.summarize(sh.parse_failures_csv(_CSV))
    out = sh.render_markdown(summary, generated="2026-09-04")

    assert "| IN |" in out and "| SE |" in out
    assert "2.2.7.0" in out
    assert "crash" in out and "hang" in out


def test_render_markdown_states_plainly_when_there_is_nothing(sh):
    """An empty report must not look like a broken run."""
    out = sh.render_markdown({}, generated="2026-09-04")
    assert "No failures" in out


def test_render_markdown_includes_the_diff_when_given_one(sh):
    before = sh.summarize(sh.parse_failures_csv(_CSV))
    after = sh.summarize(sh.parse_failures_csv(
        "Date,Failure Name,Event Type,Market,Package Version,Device Count,Event Count\r\n"
        "2026-09-01,NEW_THING,crash,BR,2.2.8.0,2,3\r\n"
    ))
    out = sh.render_markdown(after, generated="2026-09-04", delta=sh.diff(before, after))

    assert "Resolved" in out
    assert "SE" in out          # the resolved bucket is named, not just counted
    assert "New" in out


def test_snapshot_round_trips_through_json(sh):
    """A snapshot is the baseline for the next run — it must survive serialisation."""
    rows = sh.parse_failures_csv(_CSV)
    restored = sh.rows_from_snapshot(sh.snapshot_from_rows(rows))
    assert restored == rows


def test_snapshot_filenames_do_not_collide_within_a_day(sh):
    """Two runs in one day must not overwrite each other's snapshot.

    The API window is 30 days, so a snapshot is the only durable copy of data that
    expires. An overwrite silently destroys the baseline the run just compared against
    — the exact failure this tool exists to prevent.
    """
    import datetime

    a = sh.snapshot_filename(datetime.datetime(2026, 9, 4, 9, 30, 0))
    b = sh.snapshot_filename(datetime.datetime(2026, 9, 4, 17, 5, 0))

    assert a != b
    assert a.endswith(".json") and b.endswith(".json")
    # Lexical order must match chronological order — the baseline picker sorts by name.
    assert sorted([b, a]) == [a, b]


def test_snapshot_filenames_sort_chronologically_across_days(sh):
    import datetime

    names = [
        sh.snapshot_filename(datetime.datetime(2026, 9, 4, 23, 0, 0)),
        sh.snapshot_filename(datetime.datetime(2026, 10, 1, 1, 0, 0)),
        sh.snapshot_filename(datetime.datetime(2026, 9, 4, 1, 0, 0)),
    ]
    assert sorted(names) == [names[2], names[0], names[1]]


def test_snapshot_filenames_differ_below_one_second(sh):
    """Demonstrated live: two CLI runs completed inside the same wall-clock second,
    and the second overwrote the first's snapshot. Second resolution is not enough."""
    import datetime

    a = sh.snapshot_filename(datetime.datetime(2026, 9, 4, 16, 47, 12, 100000))
    b = sh.snapshot_filename(datetime.datetime(2026, 9, 4, 16, 47, 12, 900000))

    assert a != b
    assert sorted([b, a]) == [a, b]

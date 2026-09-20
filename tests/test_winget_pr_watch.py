"""
test_winget_pr_watch.py

Covers scripts/winget_pr_watch.py — the watcher that reacts when a microsoft/winget-pkgs
PR is flagged, instead of letting it sit unnoticed (the v2.3.0 incident: 64 of 71.5 hours
were pure detection latency).

The load-bearing case is `test_v230_defender_error_routes_to_auto_comment`, which replays
PR #430336's real label set. Everything here is pure-function level and runs offline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).parent.parent


def _load():
    """Import scripts/winget_pr_watch.py by path — scripts/ is not a package."""
    path = ROOT / "scripts" / "winget_pr_watch.py"
    spec = importlib.util.spec_from_file_location("winget_pr_watch", path)
    assert spec and spec.loader, f"could not load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def w():
    return _load()


# ---------------------------------------------------------------------------
# Label classification
# ---------------------------------------------------------------------------

def test_v230_defender_error_routes_to_auto_comment(w):
    """The exact labels microsoft/winget-pkgs put on PR #430336 on 2026-09-06.

    Validation-Defender-Error must land in the auto-comment bucket: its documented
    remedy is "add a comment to get the Windows Package Manager engineers to
    investigate", and an author comment is what flips Needs-Author-Feedback to
    Needs-Attention.
    """
    labels = [
        "New-Manifest",
        "Validation-Defender-Error",
        "Needs-Author-Feedback",
        "Validation-Guide",
    ]
    auto, notify = w.classify_labels(labels)

    assert auto == ["Validation-Defender-Error"]
    assert notify == []
    assert w.needs_attention(labels)


def test_healthy_pr_labels_produce_no_action(w):
    """A PR that merged cleanly must not notify — this is 28 of our last 30 PRs."""
    labels = [
        "New-Manifest",
        "Azure-Pipeline-Passed",
        "Validation-Completed",
        "Moderator-Approved",
    ]
    auto, notify = w.classify_labels(labels)

    assert auto == []
    assert notify == []
    assert not w.needs_attention(labels)


def test_our_own_bugs_notify_but_never_auto_comment(w):
    """Failures that are plausibly ours must not ask a moderator to investigate.

    Validation-Unattended-Failed is the live precedent (RULE-W1: a nested winget call
    in a /VERYSILENT install hangs). Commenting "please investigate" there would waste
    moderator time on a defect we caused.
    """
    for label in ("Validation-Unattended-Failed", "Error-Hash-Mismatch",
                  "Manifest-Validation-Error", "Binary-Validation-Error"):
        auto, notify = w.classify_labels([label])
        assert auto == [], f"{label} must never be auto-commented"
        assert notify == [label]


def test_unknown_labels_are_ignored(w):
    """winget-pkgs adds many informational labels; none may trigger a notification."""
    auto, notify = w.classify_labels(["Some-Future-Label", "Hardware", "Needs-CLA"])
    assert (auto, notify) == ([], [])


def test_mixed_labels_split_into_both_buckets(w):
    auto, notify = w.classify_labels(
        ["Validation-Defender-Error", "Validation-Merge-Conflict", "New-Manifest"]
    )
    assert auto == ["Validation-Defender-Error"]
    assert notify == ["Validation-Merge-Conflict"]


# ---------------------------------------------------------------------------
# Idempotency — the watcher runs every 30 minutes against the same PR
# ---------------------------------------------------------------------------

def test_marker_detection_prevents_a_second_comment(w):
    body = w.render_comment(version="2.3.0", labels=["Validation-Defender-Error"])
    assert w.already_commented([body])
    assert w.already_commented(["unrelated", body, "also unrelated"])


def test_no_marker_means_not_yet_commented(w):
    bot = "Hello @ossianericson,\n\nThe package manager bot was blocked..."
    assert not w.already_commented([bot, "@wingetbot run"])
    assert not w.already_commented([])
    assert not w.already_commented([None, ""])


def test_issue_match_is_exact_not_substring(w):
    """Idempotency depends on this: a near-miss would file a duplicate every 30 min.

    The lookup lists open issues rather than using GitHub search, because the search
    index is eventually consistent and a just-filed issue stays unfindable for
    minutes - long enough for the next tick to duplicate it.
    """
    title = w.issue_title(430336)
    issues = [
        {"number": 1, "title": "unrelated"},
        {"number": 2, "title": title + " (follow-up)"},   # substring, must NOT match
        {"number": 3, "title": title},
    ]
    assert w.match_issue(issues, title) == 3
    assert w.match_issue([], title) is None
    assert w.match_issue([{"number": 1, "title": "nope"}], title) is None


def test_issue_title_is_stable_for_a_given_pr(w):
    assert w.issue_title(430336) == w.issue_title(430336)
    assert w.issue_title(430336) != w.issue_title(430337)
    assert "430336" in w.issue_title(430336)


# ---------------------------------------------------------------------------
# Comment rendering — it must never claim something we have not done
# ---------------------------------------------------------------------------

def test_comment_never_claims_a_defender_submission(w):
    """WDSI submission is a web form with no API, so it stays a human step.

    Claiming it automatically would be a false statement to a moderator.
    """
    body = w.render_comment(
        version="2.3.0",
        labels=["Validation-Defender-Error"],
        vt_permalink="https://www.virustotal.com/gui/url/abc",
        sha256="deadbeef",
        prior_merged=29,
    )
    lowered = body.lower()
    assert "wdsi" not in lowered
    assert "submitted the installer" not in lowered
    assert "i have submitted" not in lowered


def test_comment_never_claims_a_reproduction_attempt(w):
    """Nothing has been reproduced at the moment this posts.

    Asserting "I cannot reproduce this locally" would be a false statement to a
    volunteer moderator - the automation fires within 30 minutes of the label, long
    before a human has installed anything. The body states belief plus evidence and
    promises a follow-up; the notification issue is what holds us to that promise.
    """
    body = w.render_comment(
        version="2.3.0",
        labels=["Validation-Defender-Error"],
        vt_permalink="https://www.virustotal.com/gui/url/abc",
        prior_merged=29,
    ).lower()
    for claim in ("unable to reproduce", "cannot reproduce", "could not reproduce",
                  "i ran a full", "i have scanned", "does not reproduce"):
        assert claim not in body, f"comment claims {claim!r}, which has not happened"
    # It must still commit to doing the work.
    assert "follow up" in body


def test_comment_includes_evidence_when_available(w):
    """URLs are asserted via urlparse, never substring (tests.md / CodeQL
    py/incomplete-url-substring-sanitization)."""
    body = w.render_comment(
        version="2.3.0",
        labels=["Validation-Defender-Error"],
        installer_url="https://example.invalid/NetSentinel-Setup-2.3.0.exe",
        vt_permalink="https://www.virustotal.com/gui/url/abc",
        sha256="deadbeef",
        run_url="https://github.com/o/n/actions",
        prior_merged=29,
    )
    hosts = {}
    for tok in body.split():
        parsed = urlparse(tok.strip("()[]<>,."))
        if parsed.scheme and parsed.hostname:
            hosts.setdefault(parsed.hostname, []).append(parsed)

    assert "www.virustotal.com" in hosts
    assert hosts["www.virustotal.com"][0].path == "/gui/url/abc"
    assert "example.invalid" in hosts
    assert hosts["example.invalid"][0].path.endswith("NetSentinel-Setup-2.3.0.exe")

    assert "deadbeef" in body
    assert "29 previous versions" in body
    assert w.MARKER in body


def test_comment_omits_evidence_lines_it_does_not_have(w):
    """A missing VT permalink must drop the line, never render an empty or broken one."""
    body = w.render_comment(version="2.3.0", labels=["Validation-Defender-Error"])
    assert "VirusTotal" not in body
    assert "SHA256" not in body
    assert "previous versions" not in body
    assert w.MARKER in body
    # Still says the essential thing.
    assert "false positive" in body.lower()


def test_comment_names_the_actual_labels(w):
    body = w.render_comment(version="2.3.0", labels=["Validation-SmartScreen"])
    assert "Validation-SmartScreen" in body


# ---------------------------------------------------------------------------
# Version parsing
# ---------------------------------------------------------------------------

def test_version_parsed_from_real_wingetcreate_title(w):
    title = "New version: NetSentinel.NetSentinel version 2.3.0"
    assert w.version_from_title(title) == "2.3.0"


def test_unfamiliar_title_yields_empty_not_a_guess(w):
    """A wrong version in the comment is worse than no version."""
    assert w.version_from_title("Remove NetSentinel 1.0.0") == ""
    assert w.version_from_title("") == ""


# ---------------------------------------------------------------------------
# Issue rendering
# ---------------------------------------------------------------------------

def test_issue_body_carries_the_manual_wdsi_step(w):
    body = w.render_issue(
        pr_number=430336,
        pr_url="https://github.com/microsoft/winget-pkgs/pull/430336",
        version="2.3.0",
        auto=["Validation-Defender-Error"],
        notify=[],
        commented=True,
    )
    assert "wdsi/filesubmission" in body
    assert "430336" in body
    assert "Validation-Defender-Error" in body
    # The auto-close timer is the thing most likely to be forgotten.
    assert "No-Recent-Activity" in body


def test_issue_body_states_whether_we_commented(w):
    kwargs = dict(
        pr_number=1, pr_url="u", version="2.3.0",
        auto=["Validation-Defender-Error"], notify=[],
    )
    assert "Needs-Attention" in w.render_issue(**kwargs, commented=True)
    assert "| no |" in w.render_issue(**kwargs, commented=False)


# ---------------------------------------------------------------------------
# Config invariants
# ---------------------------------------------------------------------------

def test_label_buckets_are_disjoint(w):
    """A label in both buckets would comment AND claim it needs our judgement."""
    assert not (w.AUTO_COMMENT_LABELS & w.NOTIFY_ONLY_LABELS)


def test_auto_comment_set_is_narrow(w):
    """Guard against the set quietly growing into "comment on everything".

    Widening this is a judgement call about Microsoft's moderator relationship, so it
    should require deliberately editing this number.
    """
    assert len(w.AUTO_COMMENT_LABELS) <= 8

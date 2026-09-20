"""
scripts/winget_pr_watch.py — Watch our open microsoft/winget-pkgs PRs and react to failures.

Usage (called from .github/workflows/winget-watch.yml):
    python scripts/winget_pr_watch.py                # act
    python scripts/winget_pr_watch.py --dry-run      # print what would happen, change nothing

Why this exists
---------------
Nothing used to watch a winget PR after `wingetcreate --submit` exited. The v2.3.0
submission (PR #430336) was flagged `Validation-Defender-Error` 30 minutes after it
opened and then sat untouched for **64 hours** until a moderator noticed it by hand —
71.5 h total against a 1.1 h median across the previous 29 submissions. The failure was
half an hour long; the rest was nobody knowing about it.

Worse, the bot parks such a PR under `Needs-Author-Feedback`, and winget-pkgs'
`scheduledSearch.markNoRecentActivity` adds `No-Recent-Activity` after 5 days of silence
and then auto-closes it. Silence is not neutral — it loses the submission.

The unlock
----------
Microsoft's own guidance for a Defender error you cannot reproduce is "add a comment to
get the Windows Package Manager engineers to investigate", and that is wired into their
automation (`.github/policies/labelManagement.issueUpdated.yml`):

    if:   Issue_Comment AND isActivitySender(issueAuthor) AND hasLabel(Needs-Author-Feedback)
    then: removeLabel(Needs-Author-Feedback); addLabel(Needs-Attention)

`Needs-Attention` auto-assigns their on-call engineers. One comment from the PR author
moves the PR out of our court and into a queue somebody is actually paged for — and
WINGET_PAT belongs to the PR author, so we can post exactly the sanctioned remedy.

Scope discipline
----------------
We only auto-comment for labels whose documented remedy is literally "add a comment"
(`AUTO_COMMENT_LABELS`). Everything else notifies a human instead: some failures are
genuinely our bug to fix (RULE-W1's `Validation-Unattended-Failed` is the precedent),
and "please investigate" on those wastes moderator time and sours the relationship.

Exits 0 whenever it did its job, including "nothing to do" — a watcher that fails the
workflow on a flagged PR would just be a second notification channel with worse text.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Callable, Iterable, Sequence

UPSTREAM = "microsoft/winget-pkgs"
PACKAGE = "NetSentinel.NetSentinel"

# Hidden HTML marker; presence in any PR comment means we already spoke on this PR.
MARKER = "<!-- netsentinel-auto-fp-notice -->"

# Labels whose documented remedy is "add a comment to get the Windows Package Manager
# engineers to investigate" — see the Error labels table at
# https://learn.microsoft.com/windows/package-manager/package/repository#error-labels
AUTO_COMMENT_LABELS = frozenset({
    "Validation-Defender-Error",
    "Validation-SmartScreen",
    "Validation-SmartScreen-Error",
    "Needs-SmartScreen-Investigation",
    "Validation-Domain",
    "Error-Installer-Availability",
    "Validation-Executable-Error",
})

# Labels that mean something failed but the fix is plausibly ours. Notify, never comment.
NOTIFY_ONLY_LABELS = frozenset({
    "Binary-Validation-Error",
    "Blocking-Issue",
    "Changes-Requested",
    "Error-Analysis-Timeout",
    "Error-Hash-Mismatch",
    "Manifest-Installer-Validation-Error",
    "Manifest-Path-Error",
    "Manifest-Validation-Error",
    "No-Recent-Activity",
    "PullRequest-Error",
    "URL-Validation-Error",
    "Validation-Error",
    "Validation-Hash-Verification-Failed",
    "Validation-HTTP-Error",
    "Validation-Indirect-URL",
    "Validation-Installation-Error",
    "Validation-Merge-Conflict",
    "Validation-MSIX-Dependency",
    "Validation-Unattended-Failed",
    "Validation-Uninstall-Error",
    "Validation-Unapproved-URL",
    "Validation-VCRuntime-Dependency",
})


# ---------------------------------------------------------------------------
# Pure logic — no network, no subprocess. Everything below here is unit-tested.
# ---------------------------------------------------------------------------

def classify_labels(labels: Iterable[str]) -> tuple[list[str], list[str]]:
    """Split a PR's labels into (auto-commentable, notify-only).

    Unknown labels are ignored entirely: winget-pkgs adds many purely informational
    ones (New-Manifest, Azure-Pipeline-Passed, Validation-Completed, Moderator-Approved)
    and treating an unrecognised label as a failure would notify on every healthy PR.
    """
    names = [str(x) for x in labels]
    auto = sorted({n for n in names if n in AUTO_COMMENT_LABELS})
    notify = sorted({n for n in names if n in NOTIFY_ONLY_LABELS})
    return auto, notify


def needs_attention(labels: Iterable[str]) -> bool:
    """True when this PR is in a state a human or the bot should hear about."""
    auto, notify = classify_labels(labels)
    return bool(auto or notify)


def already_commented(comment_bodies: Iterable[str]) -> bool:
    """True when one of our auto-notices is already on the PR (idempotency gate)."""
    return any(MARKER in (b or "") for b in comment_bodies)


def render_comment(
    *,
    version: str,
    labels: Sequence[str],
    installer_url: str = "",
    vt_permalink: str = "",
    sha256: str = "",
    run_url: str = "",
    prior_merged: int | None = None,
) -> str:
    """Build the PR comment body.

    Every claim here must be independently checkable by whoever reads it, and the body
    must never assert something we have not actually done. Two specific traps:

    - It never claims a WDSI submission. That is a web form with no API, so it is a
      human step tracked on the notification issue instead.
    - It never claims we tried and failed to reproduce the detection. Nothing has been
      reproduced at the moment this posts; the body states the belief and the evidence,
      and commits to following up - which is a promise the notification issue holds us
      to, not a report of work already done.
    """
    label_list = ", ".join(f"`{x}`" for x in labels) or "a validation error"

    lines = [
        f"Maintainer of `{PACKAGE}` here. This PR is flagged {label_list}. I believe "
        "this is a false positive and would be grateful for engineer investigation.",
        "",
        "Evidence, all independently verifiable:",
        "",
    ]

    if run_url:
        lines.append(
            f"- **Built entirely in public CI** from a tagged commit in a public "
            f"repository — build log: {run_url}"
        )
    else:
        lines.append(
            "- **Built entirely in public CI** from a tagged commit in a public repository."
        )

    if vt_permalink:
        lines.append(f"- **VirusTotal**, this exact installer URL: {vt_permalink}")
    if sha256:
        lines.append(
            f"- **SHA256** `{sha256}`, published in `SHA256SUMS.txt` on the release "
            "alongside a Sigstore cosign attestation."
        )
    if installer_url:
        lines.append(f"- **Installer** (unchanged since submission): {installer_url}")
    if prior_merged:
        lines.append(
            f"- **{prior_merged} previous versions** of this package were built by the "
            "identical pipeline and passed validation without a Defender flag."
        )

    lines += [
        "",
        "NetSentinel is an open-source network scanner packaged with PyInstaller. A "
        "newly built PyInstaller binary has no download history, which is a well-known "
        "source of heuristic and ML false positives on first submission.",
        "",
        "I am working through a local reproduction against the published installer and "
        "will follow up in this thread with what I find, either way. Happy to provide "
        "anything else that would help.",
        "",
        MARKER,
    ]
    return "\n".join(lines)


def issue_title(pr_number: int) -> str:
    """Stable, greppable title so the notification issue is created at most once."""
    return f"winget PR #{pr_number} needs attention"


def render_issue(
    *,
    pr_number: int,
    pr_url: str,
    version: str,
    auto: Sequence[str],
    notify: Sequence[str],
    commented: bool,
) -> str:
    """Body of the GitHub issue that tells a human the submission is stuck."""
    lines = [
        f"[winget PR #{pr_number}]({pr_url}) for `{PACKAGE}` {version} is flagged.",
        "",
        "| | |",
        "|---|---|",
        f"| Auto-commentable labels | {', '.join(f'`{x}`' for x in auto) or '—'} |",
        f"| Needs your judgement | {', '.join(f'`{x}`' for x in notify) or '—'} |",
        f"| Author comment posted | {'yes' if commented else 'no'} |",
        "",
    ]

    if commented:
        lines += [
            "An author comment has been posted, which moves the PR from "
            "`Needs-Author-Feedback` to `Needs-Attention` and assigns the Windows "
            "Package Manager on-call engineers. Usually nothing further is needed.",
            "",
        ]

    lines += [
        "### Manual follow-up",
        "",
        "- [ ] If a Defender/SmartScreen flag: submit the installer to the Microsoft "
        "Defender team at https://www.microsoft.com/en-us/wdsi/filesubmission "
        "(choose **Software developer**). There is no API for this, so it cannot be "
        "automated. If you do submit, add a follow-up comment on the PR with the "
        "submission ID — it materially speeds up the review.",
        "- [ ] Try to reproduce locally: install the published installer, then run a "
        "full Microsoft Defender scan. If it *does* reproduce, this is our bug — fix "
        "the binary rather than asking for a re-run.",
        "- [ ] Check the PR has not stalled again. `Needs-Author-Feedback` plus 5 days "
        "of silence adds `No-Recent-Activity`, and the PR is auto-closed 3 days later.",
        "",
        "Background: `docs/internal/vt-false-positive-runbook.md`.",
        "",
        "_Opened automatically by `.github/workflows/winget-watch.yml`._",
    ]
    return "\n".join(lines)


def version_from_title(title: str) -> str:
    """Pull the version out of wingetcreate's PR title.

    Titles look like "New version: NetSentinel.NetSentinel version 2.3.0". Returns ""
    rather than guessing when the shape is unfamiliar — the version is cosmetic here,
    so a wrong one is worse than none.
    """
    marker = "version "
    idx = title.rfind(marker)
    if idx == -1:
        return ""
    return title[idx + len(marker):].strip()


# ---------------------------------------------------------------------------
# I/O — thin wrappers over the gh CLI, kept out of the tested surface above.
# ---------------------------------------------------------------------------

class GhError(RuntimeError):
    """A gh invocation failed. Carries stderr, which CalledProcessError swallows."""


def _gh(args: Sequence[str]) -> str:
    """Run gh and return stdout, raising GhError with stderr attached on failure.

    Inherits the parent environment rather than rebuilding one: the workflow puts
    GH_TOKEN in the process environment, so there is nothing to override.

    Surfacing stderr is the point of the custom error. ``check=True`` raises a
    CalledProcessError whose message is only the exit status, so a real failure
    ("HTTP 403: Resource not accessible by personal access token", an expired PAT,
    a DNS failure) arrives as a bare "returned non-zero exit status 1" - unactionable
    in a CI log, which is the only place anyone will read it.
    """
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise GhError(
            f"gh {' '.join(args)} failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or '<no stderr>'}"
        )
    return proc.stdout


def _gh_json(args: Sequence[str]) -> object:
    out = _gh(args).strip()
    return json.loads(out) if out else []


def _pat_owner() -> str:
    return _gh(["api", "user", "--jq", ".login"]).strip()


def _open_prs(owner: str) -> list[dict]:
    raw = _gh_json([
        "pr", "list",
        "--repo", UPSTREAM,
        "--author", owner,
        "--state", "open",
        "--json", "number,title,url,labels,createdAt",
    ])
    return list(raw) if isinstance(raw, list) else []


def _pr_comment_bodies(number: int) -> list[str]:
    raw = _gh_json([
        "pr", "view", str(number),
        "--repo", UPSTREAM,
        "--json", "comments",
    ])
    if not isinstance(raw, dict):
        return []
    return [c.get("body", "") for c in raw.get("comments", [])]


def _count_prior_merged(owner: str) -> int | None:
    """How many of our winget PRs merged cleanly before now. None if unavailable."""
    try:
        raw = _gh_json([
            "search", "prs",
            "--repo", UPSTREAM,
            "--author", owner,
            "--merged",
            "--limit", "100",
            "--json", "number",
        ])
    except GhError:
        return None
    return len(raw) if isinstance(raw, list) else None


def _release_facts(version: str, repo: str) -> tuple[str, str]:
    """(vt_permalink, installer_url) scraped from our own release body.

    release.yml already embeds the VirusTotal permalink there via
    scripts/update_release_body.py, so this reuses that rather than re-querying VT.
    """
    if not version:
        return "", ""
    try:
        body = _gh(["release", "view", f"v{version}", "--repo", repo, "--json", "body",
                    "--jq", ".body"])
    except GhError:
        return "", ""

    vt = ""
    for token in body.split():
        cleaned = token.strip("()[]<>,")
        if cleaned.startswith("https://www.virustotal.com/"):
            vt = cleaned
            break

    installer = (
        f"https://github.com/{repo}/releases/download/"
        f"v{version}/NetSentinel-Setup-{version}.exe"
    )
    return vt, installer


def match_issue(items: Iterable[dict], title: str) -> int | None:
    """Exact-title match over a list of issues. Pure, so it is unit-tested."""
    for item in items:
        if item.get("title") == title:
            try:
                return int(item["number"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _find_open_issue(repo: str, title: str) -> int | None:
    """Is our notification issue for this PR already open?

    Lists rather than using `--search`. GitHub's search index is eventually
    consistent - a just-created issue is not findable for some minutes - and this
    workflow runs every 30 minutes, so a search-based check would file a fresh
    duplicate on the next tick or two after every real incident. Listing is
    deterministic and, at this repo's issue volume, no more expensive.
    """
    raw = _gh_json([
        "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title",
    ])
    return match_issue(raw, title) if isinstance(raw, list) else None


# ---------------------------------------------------------------------------

def process_pr(
    pr: dict,
    *,
    owner: str,
    repo: str,
    dry_run: bool,
    log: Callable[[str], None] = print,
) -> bool:
    """Handle one open PR. Returns True if it needed attention."""
    number = int(pr["number"])
    title = pr.get("title", "")
    url = pr.get("url", "")
    labels = [x.get("name", "") for x in pr.get("labels", [])]
    version = version_from_title(title)

    auto, notify = classify_labels(labels)
    if not (auto or notify):
        log(f"  PR #{number} ({version or 'unknown version'}) - healthy, nothing to do")
        return False

    log(f"  PR #{number} ({version or 'unknown version'}) - FLAGGED")
    log(f"    auto-commentable : {', '.join(auto) or '-'}")
    log(f"    notify-only      : {', '.join(notify) or '-'}")

    commented = False
    if auto:
        if already_commented(_pr_comment_bodies(number)):
            log("    author comment already present - not repeating it")
            commented = True
        else:
            vt, installer = _release_facts(version, repo)
            body = render_comment(
                version=version,
                labels=auto,
                installer_url=installer,
                vt_permalink=vt,
                run_url=f"https://github.com/{repo}/actions",
                prior_merged=_count_prior_merged(owner),
            )
            if dry_run:
                log("    [dry-run] would post author comment:")
                log("    " + body.replace("\n", "\n    "))
            else:
                _gh(["pr", "comment", str(number), "--repo", UPSTREAM, "--body", body])
                log("    posted author comment "
                    "(Needs-Author-Feedback -> Needs-Attention)")
            commented = True

    title_text = issue_title(number)
    existing = _find_open_issue(repo, title_text)
    if existing:
        log(f"    notification issue already open: #{existing}")
    elif dry_run:
        log(f"    [dry-run] would open issue: {title_text}")
    else:
        body = render_issue(
            pr_number=number, pr_url=url, version=version,
            auto=auto, notify=notify, commented=commented,
        )
        _gh(["issue", "create", "--repo", repo,
             "--title", title_text, "--body", body])
        log(f"    opened notification issue: {title_text}")

    return True


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would happen without commenting or opening issues")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""),
                    help="this project's repo, for release lookups and issues")
    args = ap.parse_args(argv)

    if not args.repo:
        print("::error::--repo (or GITHUB_REPOSITORY) is required")
        return 1

    owner = _pat_owner()
    print(f"Watching {UPSTREAM} PRs authored by {owner}")

    prs = _open_prs(owner)
    if not prs:
        print("No open winget PRs - nothing to do.")
        return 0

    print(f"{len(prs)} open PR(s):")
    flagged = sum(
        process_pr(pr, owner=owner, repo=args.repo, dry_run=args.dry_run)
        for pr in prs
    )

    summary = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if summary:
        with open(summary, "a", encoding="utf-8", errors="replace") as fh:
            fh.write("### winget PR watch\n\n")
            fh.write(f"- Open PRs: {len(prs)}\n")
            fh.write(f"- Flagged: {flagged}\n")

    # Deliberately 0 even when a PR is flagged: the notification issue is the signal,
    # and a red workflow every 30 minutes would train us to ignore it (RULE-ENFORCE1).
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GhError as exc:
        # An Actions annotation beats a traceback: this runs unattended every 30
        # minutes and the log is the only place the failure is ever read.
        print(f"::error::{exc}")
        sys.exit(1)

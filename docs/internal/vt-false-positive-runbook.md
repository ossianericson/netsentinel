# Runbook — VirusTotal false-positive review & manual release completion

*Internal engineering reference — release-manager use only. Not linked from `docs/index.md`
(the public docs site); this is CI/ops process, not a user-facing feature.*

Applies when `.github/workflows/release.yml`'s "Submit to VirusTotal" step reports a `blocked`
verdict (see RULE-REL1 in the development rules for the mechanism and threshold). As of this
runbook, `blocked` means combined malicious+suspicious detections exceeded `VT_SOFT_FLAG_MAX`
(default 2) — genuinely corroborated across multiple engines, not the common single-engine
heuristic noise a brand-new binary attracts. A `flagged` verdict (at or below the threshold)
never blocks anything automatically; it only shows up as a `::warning::` in the Actions log, a
step summary, and a visible (non-hiding) note in the release body — no override procedure needed.

## 1. Recognize the situation

- The `release` job shows red on "Submit to VirusTotal".
- The `winget` job shows **skipped** (it depends on `release`'s overall conclusion via
  `needs: [release]` — RULE 20 — which a `blocked` verdict correctly fails).
- The GitHub Release and all its assets (installer, MSIX, checksums, cosign bundles) **already
  exist** — "Create GitHub Release" runs *before* the VT step in the pipeline, so a VT block never
  prevents the release+assets from being published. Only the security-notes patch and the WinGet
  submission are affected.

## 2. Do not `gh run rerun` anything in this chain

`winget` depends on `release`, which depends on all three build jobs. Rerunning `winget` (or the
whole run) when `release` failed reruns the **entire upstream chain** — GitHub Actions has no
"rerun just this job, trust the upstream outputs" mode when the dependency itself failed. This
re-deletes and recreates the live GitHub Release and re-submits the identical download URL to
VirusTotal. VT returns the **same cached analysis** for an identical URL, so nothing changes
except ~35 minutes of burned CI time (confirmed live, 2026-07-26). Do not do this.

## 3. Read the actual VT verdict

Open the failed "Submit to VirusTotal" step's log. It now prints (as of the RULE-REL1 fix):
- The VT permalink.
- The malicious/suspicious/total counts.
- The names of every engine that flagged it (`Flagging engines: ...`) — previously unavailable
  outside CI; no personal VT API key is needed to see this anymore.

Open the permalink itself too and check engine reputations/detection names directly on
virustotal.com — some engines label detections more specifically than the bare category the API
returns.

## 4. Make the judgment call

This is a human decision, not something to automate further. Lean toward **not overriding** unless
the pattern clearly matches known false-positive shapes:

- **Likely false positive:** 1–2 heuristic/ML/generic-signature engines (names like "Generic",
  "Heuristic.*", "ML.Attribute.*", or similar), a brand-new PyInstaller binary (never-before-seen
  hash), and the flagged code path is a known, already-documented, deliberate technique — e.g. the
  `modules/single_instance.py` `Global\` named-mutex pattern (RULE-WIN16) that triggered the
  2026-07-26 v2.1.45 incident this runbook exists because of. This exact case is a precedent: 1
  malicious / 92 engines, all-clean the release before and after, no corroboration from any
  reputable engine.
- **Real signal — do not override:** multiple reputable engines agree, a consistent named malware
  family, or a code path that is genuinely new/unreviewed (not an already-documented, spiked
  pattern). Stop here. Investigate the actual diff, consider yanking the release
  (`gh release delete <tag>`), and treat it as a real security incident, not a CI nuisance.

## 5. If judged a false positive: patch the release notes

Run locally (needs a `GITHUB_TOKEN` with repo scope and `GITHUB_REPOSITORY` set — a personal
access token works; nothing from GitHub Actions secrets is required for this step):

```powershell
$env:GITHUB_TOKEN = "<your PAT>"
$env:GITHUB_REPOSITORY = "ossianericson/netsentinel"

python scripts/update_release_body.py <release_id> <version> <sha256sums_url> `
  --vt-permalink <link> --vt-status blocked --vt-detections "<M>/<T>" --vt-engines "<names>" `
  --human-override "reviewed 2026-MM-DD by <name>: <engine(s)>, matches the single-instance mutex FP precedent — judged non-blocking" `
  --bundle-name "NetSentinel-Setup-<version>.exe.bundle" --msix-bundle-name "NetSentinel-<version>.msix.bundle"
```

This renders a visible "🛑 Blocked ... — reviewed" line plus your reviewer note in the release
notes — it does not pretend the flag never happened.

## 6. Complete WinGet distribution — use the workflow that already exists for this

**Do not try to run `wingetcreate` locally.** It needs `WINGET_PAT` (a GitHub-Actions-only
secret, correctly not available on a laptop) and an interactive device-code login.

Instead: **Actions → "WinGet Submit" → Run workflow → enter the version (e.g. `2.1.45`, no `v`
prefix) → Run.** This is `.github/workflows/winget-submit.yml` — it already exists, is
`workflow_dispatch`-triggered (a manual, non-cascading entry point; it does not touch builds, the
`release` job, or VT at all), and builds the installer URL directly from the version input against
the release/assets that already exist. It has sat unused since it was added in v2.1.21 — this
runbook exists partly because nobody reached for it during the 2026-07-26 incident. Use it.

(`.github/workflows/promote-release.yml` is a related staged-rollout helper for marking a
prerelease stable — not needed here since `release.yml` currently publishes with
`prerelease: false` directly; noted only so it isn't confused with the winget step above.)

---

# Part 2 — A winget PR flagged *after* submission

Everything above covers a VirusTotal verdict raised **inside our own pipeline**, where the
release job goes red and we notice immediately. This part covers the opposite case: our
pipeline was green, the PR opened normally, and `microsoft/winget-pkgs` flagged it
**downstream**, where nothing of ours was watching.

## What this cost us once

`microsoft/winget-pkgs` PR [#430336](https://github.com/microsoft/winget-pkgs/pull/430336)
(v2.3.0), against a **1.1 h median** across the previous 29 submissions (1.15 h including it):

| Elapsed | Event |
|---|---|
| T+0:00 | PR opened by `release.yml`'s winget job |
| **T+0:30** | `Validation-Defender-Error`. Bot applied `Needs-Author-Feedback` + `Validation-Guide` and assigned the PR **to us** |
| T+0:30 → T+64:21 | **Nothing.** No human and no automation knew it had failed |
| T+64:21 | Moderator @stephengillie manually ran `@wingetbot run` |
| T+71:28 | Merged — **the identical binary passed, unchanged** |

The real failure was 30 minutes long. The other 64 hours were detection latency.

## The single most important fact

**Silence is not neutral — it loses the submission.** `scheduledSearch.markNoRecentActivity`
adds `No-Recent-Activity` to any PR that has sat under `Needs-Author-Feedback` for 5 days, and
`scheduledSearch.closeNoRecentActivity` closes it 3 days after that. #430336 was 2.7 days into
that 8-day countdown when a moderator happened to intervene.

## The unlock: a comment from the PR author

Microsoft's documented remedy for a Defender error you cannot reproduce is *"add a comment to
get the Windows Package Manager engineers to investigate"*, and it is wired into their
automation (`microsoft/winget-pkgs/.github/policies/labelManagement.issueUpdated.yml`):

```yaml
if:   Issue_Comment AND isActivitySender(issueAuthor) AND hasLabel(Needs-Author-Feedback)
then: removeLabel(Needs-Author-Feedback); addLabel(Needs-Attention)
```

`Needs-Attention` **auto-assigns their on-call engineers**. One comment from the PR author moves
the PR out of our court and into a queue somebody is actually paged for.

Note who can do what: only the moderators listed in `moderatorTriggers.yml` (and anyone with
write access) can run `@wingetbot run`. We cannot re-trigger validation ourselves. Commenting is
the entire lever we have — and it is enough.

## What is automated now

`.github/workflows/winget-watch.yml` runs `scripts/winget_pr_watch.py` every 30 minutes:

- **No open PR → exits in seconds.** Free on a public repo; this is the normal case.
- **`AUTO_COMMENT_LABELS`** (Defender, SmartScreen, Domain, Installer-Availability,
  Executable-Error) → posts the author comment once, guarded by a hidden marker so a later tick
  cannot repeat it. The body carries only checkable evidence: the VirusTotal permalink from our
  own release body, the public CI build, the SHA256, and a **live-computed** count of prior
  clean submissions.
- **Everything else** → opens a GitHub issue and says nothing on the PR. Some failures are
  genuinely ours (RULE-W1's `Validation-Unattended-Failed` is the precedent), and asking a
  moderator to investigate our own bug wastes their time.
- **Either way** → a notification issue lands in this repo so a human hears about it.

Run it by hand with `--dry-run` to see what it would do without touching anything:

```powershell
python scripts/winget_pr_watch.py --repo ossianericson/netsentinel --dry-run
```

## Your manual steps when it fires

1. **Try to reproduce.** Install the published installer, run a full Microsoft Defender scan. If
   it reproduces, this is our bug — fix the binary; do not ask for a re-run.
2. **Submit to WDSI** if it does not reproduce:
   https://www.microsoft.com/en-us/wdsi/filesubmission → **Software developer**. There is no API
   for this, which is exactly why the automation does not claim to have done it. If you submit,
   add a follow-up comment on the PR with the submission ID — it materially speeds up review.
3. **Watch the clock.** If it stalls again, another author comment resets the
   `No-Recent-Activity` timer and re-raises `Needs-Attention`.

## Why the installer gets flagged at all

The evidence points at a **transient cloud/ML reputation verdict on a brand-new, unsigned,
zero-prevalence PyInstaller hash**, not a stable behavioural rule:

- The identical bytes passed on re-run 2.7 days later with **no change whatsoever**.
- The 28 prior releases from this same pipeline were never flagged. A deterministic behavioural
  trigger — `installer.iss`'s four `netsh advfirewall` calls are the obvious candidate — would
  have fired every time, on all of them.

What we have done about it (v2.3.1), all free:

- **UPX off** on `NetSentinel-cli.exe` and `NetSentinel-svc.exe`, which were `upx=True` while the
  GUI was already `upx=False`. Note honestly what this did and did not fix: UPX is not installed
  on any builder and PyInstaller silently skips packing without it, so those binaries were never
  actually packed and this was **not** a cause of the v2.3.0 flag (measured: the same spec at
  `upx=True` vs `upx=False` differs by 2 KB on a 9.79 MB exe, in the wrong direction — noise, not
  compression). It closes a latent trap rather than an open wound: UPX packing is a top-tier
  heuristic trigger, and the day a builder happens to have UPX these would start shipping packed.
- **VERSIONINFO on all three exes** (`packaging/version_info.py`) and on the Inno setup stub
  (`installer.iss`). Every binary previously shipped with no CompanyName, ProductName, or
  FileVersion at all.

## What we deliberately did not do

- **Delay the winget submission** to let the binary age into some reputation. 28 of 30 PRs merge
  in about an hour; slowing the common case to hedge a 1-in-30 case is a bad trade.
- **Chase `Publisher-Verified`.** `verifiedDeveloper.yml` does define a fast path that bypasses
  moderator review entirely, but the label is applied server-side by `wingetbot` with no public
  self-enrolment — and it would only have saved the final ~7 hours, not the 64.
- **Authenticode code signing.** This is the genuine root-cause fix and the only thing that also
  removes end-user SmartScreen warnings. **Azure Artifact Signing** (formerly Trusted Signing,
  ~$10/month) is the cheap modern route, but its public-trust certificates require **individual
  developers to be located in the US or Canada**; organizations are eligible across the EU/UK and
  more. As an individual outside those two countries this is a closed door — recorded here so it
  is not researched again. The remaining options are a traditional OV certificate (~$200–400/yr,
  private key on a hardware token or cloud HSM since 2023) or signing as a registered legal
  entity.

Nothing we ship is Authenticode-signed today. The cosign `.bundle` sidecars are Sigstore
signatures over the blob — real, verifiable, and completely invisible to SmartScreen, Defender,
and winget validation. Do not cite them as "the installer is signed" in a winget PR comment.

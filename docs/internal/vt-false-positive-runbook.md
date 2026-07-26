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

---
paths:
  - "CHANGELOG.md"
  - "README.md"
---

# Changelog Entry Format

Full detail lives in `CHANGELOG.md`; `README.md` carries only a 3–5 bullet plain-English
summary of the current release under `## Changelog` (RULE-R1b). Each version gets a
`### vX.Y.Z` header, added by `bump_version.py` promoting the topmost header in each file.

## CHANGELOG.md entry structure

Group changes under these type headers (omit empty groups):

```
### vX.Y.Z
**Added**
- Short description of new feature or page (#PR or commit ref if available)

**Changed**
- Short description of behaviour change

**Fixed**
- Short description of bug fix

**Security**
- Short description of security hardening
```

## Rules

- One line per logical change. Combine related commits into one entry.
- Use backticks for code references: module names, page labels, file paths, setting keys.
- Start each bullet with a capital letter; no trailing period.
- Do NOT include version-bump machinery entries ("bump to vX.Y.Z", "update winget manifests").
- Do NOT pad with filler ("various improvements", "minor fixes").
- Security entries go last within a version block, always under `**Security**`.
- Every new module, page, or worker gets an `**Added**` entry — no exceptions.

## README.md summary block

Update the topmost `### vX.Y.Z (current)` block under `## Changelog` to 3–5 bullets in
plain English — the public-facing highlights, not a restatement of every CHANGELOG line.

## Examples

```
### v1.9.43
**Added**
- `modules/isp_telemetry.py` — anonymous opt-in ISP comparison with daily submission
- `ui/pages/classroom_page.py` — Classroom Export page in Education section

**Fixed**
- `speed_tester.py`: Ookla CLI detection now checks WinGet Links dir on first launch

**Security**
- `rest_api.py`: API key now stored in OS keychain via `keyring` (previously QSettings)
```

# NetSentinel — Wiring & Import Crash Audit
_Generated: 2026-06-05_

This document records every potential runtime crash risk found in an audit of signal/slot
wiring, style-constant imports, and cross-mixin method calls across the entire `ui/`
tree. No code was changed during this audit. Each item is a **backlog task** to be fixed
in a future session.

---

## Executive Summary

| Category | Issues Found | Status |
|---|---|---|
| Style constant missing import (crash on code path) | 1 | FIXED |
| Style constant name collision / confusion risk | 1 | FIXED (WIRING-2A) |
| Dynamic `globals().update()` — no static-analysis coverage | structural | FIXED (WIRING-3A) |
| Signal/slot connections — missing handlers | 0 | Clean |
| Worker result handlers — missing methods | 0 | Clean |
| Cross-mixin `self.X()` calls — unresolved | 0 | Clean |
| Coach mark / onboarding signals | 0 | Clean |
| hub_helpers / hub_card cross-imports | 0 | Clean |
| Page creation vs nav registration | 0 | Clean |

---

## Category 1 — Style Constants: Missing Explicit Imports

### Background: how the crash pattern works

`ui/styles.py` injects all per-theme colour constants into its own module globals via
`globals().update(THEMES[_ACTIVE_THEME])` at import time. This makes them accessible
via `from ui.styles import NAME`, but **static analysers (mypy, Pylance, Pyright) cannot
see them** — they only see the `globals().update()` call. The constants are invisible until
runtime.

When a UI file uses a constant (e.g. `f"color:{AMBER_BG}"`) **without** an explicit
`from ui.styles import AMBER_BG`, Python raises `NameError` the first time that code path
runs. The crash may not appear at startup — it surfaces only when the specific widget is
rendered, which is why these are silent until a user navigates to the affected page.

Dynamic constants (injected via `globals().update()`):

```
ACCENT  ACCENT_LITE  ACCENT_DARK  ADMIN_WARN_BG  ADMIN_WARN_BORDER  ADMIN_WARN_FG
ADMIN_WARN_HOVER  AMBER  AMBER_BG  AUDIT_RED  BG_ALT_ROW  BG_CARD  BG_DARK
BG_HOVER  BLUE  BORDER  BORDER_LITE  BORDER_MED  BTN_DISABLED_BORDER  BTN_DISABLED_FG
BTN_EXPORT_HOVER  BTN_HOVER_BG  CARD_HDR_BORDER  CHART_BG  CHART_GRID  CHART_PLOT_BG
CHART_TITLE  CRITICAL  GRADE_A_BG  GRADE_B_BG  GRADE_B_FG  GRADE_C_BG  GRADE_D_BG
GRADE_F_BG  GRADE_F_FG  GREEN  GREEN_BG  INPUT_BTN_BG  INPUT_PLACEHOLDER
LABEL_SUBTITLE  NAV_BAR  NAV_DIVIDER  PROGRESS_TRACK  PRO_BANNER_BORDER  PRO_WARN_BG
RED  RED_BG  SCROLLBAR_HANDLE  SCROLLBAR_TRACK  SIDEBAR_BG  SIDEBAR_HOVER
SIDEBAR_ITEM_FG  SIDEBAR_SECTION_BG  SIDEBAR_SECTION_FG  SIDEBAR_SEL  SIDEBAR_SEL_BG
TABLE_ROW_BORDER  TABLE_SEL  TEXT_MUTED  TEXT_PRIMARY  TEXT_SECONDARY  TH_BG
TH_BORDER  TH_TEXT  TOOLTIP_BG  TOOLTIP_BORDER  UPDATE_BAR_BG  UPDATE_BAR_BORDER
UPDATE_BAR_FG  WHITE
```

**Non-dynamic constants** (plain module-level assignments — always safe to import):
`STATUS_OFFLINE`, `OVERLAY_BG`, `OVERLAY_BG2`, `OVERLAY_BG3`, `OVERLAY_BLUE`,
`OVERLAY_BLUE2`, `OVERLAY_FG2`, `OVERLAY_FG3`, `INLINE_WARN_FG`, `INLINE_WARN_BG`,
`BADGE_OK_FG/BG/BORDER`, `BADGE_OFF_FG/BG/BORDER`, `TEAL`, `DEEP_ORANGE`,
`ACCENT_PURPLE`, `CARD_RADIUS`, and the `RISK_COLORS`/`RISK_BG` dicts.

---

### P0 — FIXED this session

| File | Constants | Fix |
|---|---|---|
| `ui/scan_wiring.py` | `AMBER_BG`, `RED_BG` | Added to `from ui.styles import (...)` |

These were used as colour variables in f-strings inside `_on_m1_result()` and
`_on_plugin_result()`. Any navigation to Overview or the Plugin scan result would
have crashed with `NameError`.

---

### P1 — No current crash, but fragility risk to document

The AST-based audit ran across all `ui/**/*.py` files and found **no other file** uses a
dynamic constant as a bare variable without importing it. All apparent hits from a
surface-level grep were string literals (e.g., `if sev == "CRITICAL"`) not colour
variable references.

**However**, this is only true of the current state of the codebase. The risk is
structural (see Category 3 below).

---

## Category 2 — `CRITICAL` Naming Collision Risk

`styles.py` defines `CRITICAL = "#8B0000"` as a **dark-red colour** for the "Critical
CVE severity" UI level. At the same time, the string `"CRITICAL"` is used throughout the
codebase as a **severity label** for comparisons:

```python
# In scan_wiring.py, tabs_recon.py, cve_page.py etc.:
color = RED if sev in ("CRITICAL", "HIGH") else AMBER
```

These are two different things:
- `CRITICAL` (bare name) — a colour hex string, e.g. `"#8B0000"`
- `"CRITICAL"` (quoted) — a severity label string

**Current state:** no file uses the `CRITICAL` colour constant as a bare variable — it is
never imported and never used as a colour. It exists only in the theme dicts and is
therefore dead code today.

**Risk:** A future developer adding a CVE colour scheme might write
`f"color:{CRITICAL}"` without importing it, producing a NameError. Or they might import
it and accidentally use `CRITICAL` where they meant `"CRITICAL"` in a string comparison,
producing a silent colour-in-a-string bug.

**Backlog item:**

- [x] **WIRING-2A** Renamed `CRITICAL` → `CVE_CRITICAL_FG` in all four theme dicts in
  `styles.py`; updated the one active consumer (`cve_page.py`); removed the unused import
  from 8 other files; updated `tools/_hex_purge.py`.

---

## Category 3 — Structural: No Automated Test for Dynamic Import Coverage

The `globals().update()` injection pattern is invisible to static analysis. There is no
test that enforces "every dynamic constant used as a bare name in any UI file is
explicitly imported in that file." The AMBER_BG/RED_BG crash was only caught at runtime.

**Backlog items:**

- [x] **WIRING-3A** Created `tests/test_style_imports.py` — AST-based test covering all
  `ui/**/*.py`, enforces every dynamic theme constant used as a bare Name is explicitly
  imported. 115 files checked, passes clean.

- [x] **WIRING-3B** Added `RULE-AH6` to `.apm/instructions/development-rules.instructions.md`
  (and auto-compiled into `.claude/rules/development-rules.md`) documenting the procedure
  for adding/renaming theme dict keys, including the `test_style_imports.py` command.

---

## Category 4 — Signal/Slot Connections: Clean

Checked: all `.connect()` calls in `ui/dashboard.py`, `app.py`, `ui/scan_wiring.py`,
and the six modified files (`monitor_state.py`, `hardware_integration_page.py`,
`settings_cards.py`, `coach_mark.py`, `hub_helpers.py`, `scan_wiring.py`).

- All `result_ready.connect(...)` handlers exist on the target class.
- All `error.connect(...)` handlers exist.
- `coach_mark.py` — `dismissed` / `advanced` signals connected to `_on_dismissed` /
  `_on_advanced`; both methods defined in `CoachMarkChain`. Clean.
- `CoachMarkChain(on_done=...)` callback is optional; guarded with `callable()`. Clean.

**No issues found.**

---

## Category 5 — Cross-Mixin `self.X()` Calls: Clean

`_MonitorStateMixin` calls `self._refresh_section_badges()`, `self._set_status()`, and
`self._nav_rail_go_to()`. All three are defined on Dashboard via other mixins in the MRO.

`_PluginPageMixin`, `_NavBuilderMixin`, `ScanResultMixin`, `AppHeaderMixin`,
`TabBuilderMixin` — spot-checked for calls on `self` to methods not in the same file.
All resolve through the Dashboard MRO.

**No issues found.**

---

## Category 6 — Worker Result Handlers: Clean

All `_on_*_result` methods referenced in `result_ready.connect(...)` calls exist.
`app.py` always-on worker connections (`cert_worker`, `svc_worker`, `snmp_trap_worker`,
`syslog_worker`, `arp_monitor`) — all target methods exist on Dashboard.

**No issues found.**

---

## Category 7 — `settings_cards.py` Non-Standard Imports: Clean

`settings_cards.py` imports `ACCENT_PURPLE`, `BADGE_OFF_BG/BORDER/FG`, `BADGE_OK_BG/BORDER/FG`,
`CARD_RADIUS`, `DEEP_ORANGE`, `INLINE_WARN_BG/FG`, `TEAL` from `ui.styles`. All of these
are **plain static assignments** (not dynamic theme-dict keys), defined unconditionally at
lines 496–552 in `styles.py`. They are always present regardless of active theme.

Also imports `BTN_HOVER_BG`, `CARD_HDR_BORDER`, `PRO_WARN_BG`, `RED_BG` which ARE dynamic
(theme-dict) — but are explicitly listed in the import block, so they're safe.

**No issues found.**

---

## Category 8 — `coach_mark.py` Overlay Imports: Clean

Imports `OVERLAY_BG`, `OVERLAY_BG3`, `OVERLAY_BLUE`, `OVERLAY_BLUE2`, `OVERLAY_FG2`,
`STATUS_OFFLINE` from `ui.styles`. All are plain static assignments (lines 494–538),
not theme-dict entries. Safe across all four themes.

**No issues found.**

---

## Prioritised Backlog

### P0 — Definite crash, fixed
- [x] **WIRING-0A** `scan_wiring.py`: add `AMBER_BG`, `RED_BG` to import — **done**

### P1 — Crash waiting to happen (structural, no test coverage)
- [x] **WIRING-3A** `tests/test_style_imports.py` written — AST-based, covers all `ui/**/*.py`.
  115 files pass. Would have caught the AMBER_BG/RED_BG crash before it shipped.

### P2 — Latent naming confusion, no crash today
- [x] **WIRING-2A** `CRITICAL` renamed to `CVE_CRITICAL_FG` in all four theme dicts.
  One active consumer (`cve_page.py`) updated; 8 unused imports removed.

### P3 — Documentation / process
- [x] **WIRING-3B** `RULE-AH6` added to `.apm/instructions/development-rules.instructions.md`
  and auto-compiled into `.claude/rules/development-rules.md`.

---

## How to Re-Run This Audit

```powershell
cd c:\Code\netsentinel

# AST-based: find dynamic constants used as bare names without import
python -c "
import ast, re
from pathlib import Path

styles_src = Path('ui/styles.py').read_text(encoding='utf-8')
# Extract theme dict keys (dynamic constants)
import re as _re
theme_match = _re.search(r'_ARCTIC_CLEAN\s*=\s*\{([^}]+)\}', styles_src, _re.DOTALL)
DYNAMIC_KEYS = set(_re.findall(r'\"([A-Z_]+)\":', theme_match.group(1))) if theme_match else set()

issues = []
for pyf in sorted(Path('ui').rglob('*.py')):
    if pyf.name == 'styles.py':
        continue
    src = pyf.read_text(encoding='utf-8', errors='replace')
    imported = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        continue
    has_module_import = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and 'ui.styles' in (node.module or ''):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if 'styles' in alias.name:
                    has_module_import = True
    if has_module_import:
        continue
    for k in DYNAMIC_KEYS:
        if _re.search(r'\b' + k + r'\b', src) and k not in imported:
            n = len(_re.findall(r'\b' + k + r'\b', src))
            issues.append((str(pyf), k, n))

for f, k, n in sorted(issues):
    print(f'{f}: {k} ({n}x) — check if bare name or string literal')
"
```

_After running, manually inspect each hit to determine whether the usage is a bare
variable (crash risk) or a quoted string (safe comparison). See WIRING-3A for
automating this distinction._

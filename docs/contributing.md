# Contributing to NetSentinel

Thanks for your interest in contributing. This document covers everything from setting up a dev environment to shipping a release.

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10 or newer (3.11 recommended for builds) | `build.bat` explicitly targets 3.11 to match GitHub Actions |
| pip | bundled with Python | |
| PyQt6 | ~6.11 | installed via requirements.txt |
| Npcap | latest | **Windows only — required for packet-capture features** (Rogue Bridge / STP, Broadcast Storm tabs). Download from [npcap.com](https://npcap.com). Not needed to run the app or its other tabs. |
| Inno Setup | 6.x | Required only to build the Windows installer `.exe`. Download from [jrsoftware.org](https://jrsoftware.org/isinfo.php). |

Optional system tools used at runtime but not required to develop:

- `nmap` — OS fingerprinting and SYN scanner
- Ookla Speedtest CLI (`winget install Ookla.Speedtest.CLI`) — tier-1 speed test backend
- `pywin32` — Windows service build only (not needed for GUI or CLI)

---

## 2. Clone and set up

```bash
git clone https://github.com/ossianericson/netsentinel.git
cd netsentinel
pip install -r requirements.txt
```

The pinned dependencies in `requirements.txt` use `~=` (compatible-release) specifiers — they allow only patch updates within the same major.minor, which prevents silent breaking changes. Do not loosen these pins without a deliberate review.

Core runtime dependencies installed by the above:

| Package | Purpose |
|---|---|
| `PyQt6~=6.11` | UI framework |
| `scapy~=2.7` | Packet capture (ARP, STP, storm analysis) |
| `matplotlib~=3.10` | Charts and graphs |
| `psutil~=7.0` | Active connections, process monitor |
| `speedtest-cli~=2.1` | Fallback speed test backend |
| `keyring~=25.0` | OS credential store (SMTP password, SNMP community, API keys) |
| `flask~=3.0` | Local read-only REST API (127.0.0.1, disabled by default) |
| `cryptography~=44.0` | Required by scapy; enables KRACK module |
| `maxminddb~=3.1` | GeoLite2 IP geolocation |

---

## 3. Running the app from source

```bash
python app.py
```

The app requires administrator/root privileges for features that use raw sockets (ARP scanning, STP detection, packet capture). On Windows, right-click your terminal and choose "Run as Administrator" before launching. On Linux/macOS:

```bash
sudo python app.py
```

For a quick import sanity check without opening the GUI:

```bash
python app.py --smoke
```

This runs `_smoke_test()` in `app.py`, which imports every module and worker to catch missing dependencies or broken imports — the same check that `build.bat` runs before a PyInstaller build.

---

## 4. Running tests

```bash
pytest tests/ -v
```

**CI / headless environments:** PyQt6 requires a display. Set the platform to `offscreen` before running:

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

On Windows (PowerShell):

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest tests/ -v
```

The `conftest.py` fixture at `tests/conftest.py` handles this automatically when tests are invoked via `pytest` — it creates a single session-scoped `QApplication` with `["-platform", "offscreen"]` so Qt widget tests don't segfault between modules. If you set `QT_QPA_PLATFORM=offscreen` in the environment before running, that takes precedence.

After each test the fixture closes orphaned top-level widgets and runs three passes of `processEvents()` to drain `deleteLater()` queues. This prevents C-level segfaults caused by accumulated Qt objects across QWidget-heavy tests.

To run only the version consistency check (useful after a bump):

```bash
pytest tests/test_version_consistency.py -v
```

---

## 5. Building the installer

### Windows

```bat
build.bat
```

`build.bat` will:

1. Create a `.venv311` virtual environment using Python 3.11 (matches GitHub Actions).
2. Install all dependencies inside it.
3. Run a pre-build smoke test (`python app.py --smoke`).
4. Call `pyinstaller --clean -y NetSentinel.spec` to produce `dist\NetSentinel.exe`.
5. Optionally build the CLI (`NetSentinelCLI.spec`) and Windows service (`NetSentinelSvc.spec`).
6. Run a post-build smoke test against the bundled executable.

Selective builds:

```bat
build.bat --gui     # GUI only (skip CLI and service)
build.bat --cli     # CLI only
build.bat --debug   # GUI with console window for diagnosing PyInstaller issues
```

After a successful GUI build, build the installer:

```bat
iscc installer.iss
```

This produces `dist\NetSentinel-Setup-X.Y.Z.exe`.

### macOS / Linux

```bash
./build.sh
```

Produces `dist/NetSentinel` (GUI) and optionally `dist/NetSentinel-cli`. The macOS build does not include Inno Setup packaging — distribute the raw executable or wrap it in a `.app` bundle manually.

---

## 6. Bumping the version

**Never edit version strings by hand.** Use the bump script every time — no exceptions (RULE-R1).

```bash
python bump_version.py X.Y.Z
```

Example:

```bash
python bump_version.py 1.60
```

The script updates all 13 tracked locations atomically:

| File | What changes |
|---|---|
| `app.py` | `setApplicationVersion("X.Y.Z")` |
| `cli.py` | `_VERSION = "X.Y.Z"` |
| `apm.yml` | top-level `version: X.Y.Z` |
| `installer.iss` | `#define MyAppVersion "X.Y.Z"` |
| `build.bat` | version banner line |
| `build.sh` | version banner line |
| `README.md` | release badge link + What's New header |
| `tools/debug_launch.py` | `setApplicationVersion("X.Y.Z")` |
| `modules/rest_api.py` | `"version"` in `/health` endpoint |
| `.github/winget/NetSentinel.NetSentinel.yaml` | `PackageVersion: X.Y.Z` |
| `.github/winget/NetSentinel.NetSentinel.installer.yaml` | `PackageVersion` + installer URL |
| `.github/winget/NetSentinel.NetSentinel.locale.en-US.yaml` | `PackageVersion: X.Y.Z` |

After running, the script automatically executes `tests/test_version_consistency.py` and exits with code 1 if any location was missed.

Then commit and tag:

```bash
git add -p          # review every change
git commit -m "chore: bump version to 1.60"
git tag v1.60
git push && git push --tags
```

---

## 7. Adding a new page

Pages live in `ui/pages/`. Follow these steps:

**Step 1 — Create the page file**

```
ui/pages/my_page.py
```

Your page class must be a `QWidget` subclass. Show meaningful content within 200 ms of navigation (RULE-UX1) — use `MetricStore` cached data for the initial render, then refresh via a worker signal.

**Step 2 — Register the page in `_build_tabs()`**

Open `ui/dashboard.py` and find `_build_tabs()`. Instantiate your page alongside the others:

```python
from ui.pages.my_page import MyPage
self._my_page = MyPage(store=self._store, parent=None)
```

**Step 3 — Add a navigation entry**

Still inside `_build_tabs()`, after the page is instantiated and the sidebar list `self._nav` has been created, call `_nav_add_page()` inside the appropriate section or subgroup:

```python
self._nav_add_page("◈", "My Page", self._my_page)
```

The first argument is the icon (a geometric Unicode symbol — see RULE-AH3 / RULE 25), the second is the sidebar label, and the third is the widget instance. `_nav_add_page()` registers the widget in `self._stack` and maps the nav row to the page index automatically.

If your page belongs in a new subgroup, call `_nav_add_subgroup()` first:

```python
self._nav_add_subgroup("My Group", "▸")
self._nav_add_page("◈", "My Page", self._my_page)
```

**Step 4 — Update the smoke test**

Add an import of your page to `app.py _smoke_test()` (RULE-T4).

**Step 5 — Write tests**

At minimum: one import test and one behavioural test in `tests/test_my_page.py`.

---

## 8. Adding a new module

Modules live in `modules/`. They contain pure business logic — no Qt imports, no widgets, no UI calls.

**File size limit:** No module file may exceed 600 lines (RULE-AH1). If you find yourself going over, extract cohesive sub-concerns into sibling modules.

**Lazy imports for optional dependencies:**

Any dependency that is not universally available (nmap, scapy, speedtest-cli, Npcap-dependent libs) must not be imported at module level (RULE-AH4). Wrap them in a lazy import inside the function that needs them:

```python
def run_scan(target: str):
    try:
        import nmap
    except ImportError:
        return []   # degrade gracefully — never crash on import
    # ... use nmap
```

The fallback must degrade gracefully: return empty results, emit an error signal, or show a banner. Never let an optional import crash the app.

**Test file required (RULE-T1):** Every new file added under `modules/` must have a corresponding `tests/test_<name>.py` in the same PR. The test file must contain at minimum:

- one import test (verifies the module loads cleanly)
- one behavioural test covering the primary function or class

If you are adding a worker under `workers/`, it also needs a start/stop lifecycle test (RULE-T2): instantiate the worker, call `start()`, wait briefly, call `stop()`, and assert `isRunning()` is `False`.

---

## 9. Coding standards

Key rules from `apm.yml` that every contributor must follow:

**No raw hex colours outside `ui/styles.py` and `modules/colours.py` (RULE-AH3 — blocking)**

Running `grep -rn '#[0-9a-fA-F]\{6\}' --include="*.py"` and finding matches outside those two files is a CI failure. Add new colours to `ui/styles.py` (for UI/widget use) or `modules/colours.py` (for charts and HTML report use), then import from there.

**No raw exceptions shown to users (RULE-A2 — required)**

No Python traceback or `AttributeError` may ever appear in the UI. All worker error signals must be caught and translated to an actionable message using a helper like `_friendly_error(exc) -> str` in each page class. The message must say what failed, why it likely failed, and what the user should try next.

**Severity labels must use the canonical four (RULE-A3 — required)**

All severity/risk labels visible in the UI must be exactly one of: `Info`, `Warning`, `High`, `Critical`. Do not invent new strings (`SEVERE`, `NOTICE`, `ALERT`, etc.). The visual treatment is defined by `RISK_COLORS` / `RISK_BG` in `ui/styles.py`.

**Every feature needs plain-English and technical views (RULE-A1 — required)**

Scan results must be presented at two levels: a plain-English summary (what it means, what to do) visible by default, and full technical detail (raw values, MACs, exact RTTs, OIDs) accessible via a collapsible section or "Details" button.

**New pages must show content within 200 ms (RULE-UX1 — required)**

Use cached `MetricStore` data for the initial render, then refresh via a worker signal.

**Every scan result table needs a right-click context menu (RULE-UX3 — required)**

At minimum: "Copy" (selected row as text) and "How to Fix" (plain-English remediation panel). Use `customContextMenuRequested` signal — never override `mousePressEvent`.

**Workers must not block for more than 5 seconds without a progress signal (RULE-AH2 — required)**

Long-running workers must emit a `progress(str)` or `status(str)` signal at least every 5 seconds. Use `msleep()` in polling loops and check a `_running` flag on each iteration.

---

## 10. PR checklist

Before opening a pull request, confirm all of the following:

- [ ] `pytest tests/ -v` passes with zero failures (run with `QT_QPA_PLATFORM=offscreen` if headless)
- [ ] `tests/test_version_consistency.py` passes — all 13 version locations are in sync
- [ ] If a new module was added: `tests/test_<module>.py` exists with at least one import test and one behavioural test (RULE-T1)
- [ ] If a new worker was added: start/stop lifecycle test exists (RULE-T2)
- [ ] If this is a bug fix: a regression test that fails before the fix and passes after is included (RULE-T3)
- [ ] `app.py _smoke_test()` was updated if a new module or worker was added (RULE-T4)
- [ ] No raw hex colour strings outside `ui/styles.py` / `modules/colours.py` (`grep '#[0-9a-fA-F]\{6\}'` returns zero matches in other files)
- [ ] No raw Python exceptions visible in the UI — all errors go through a `_friendly_error()` translation layer
- [ ] Manual smoke test: `python app.py` launches without errors, the new page/feature is visible and functional
- [ ] If a new page was added: it shows content within 200 ms (not a blank panel while a worker starts)
- [ ] PR title follows conventional commits style: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`

---

## 11. Release process

1. **Bump the version** — run `python bump_version.py X.Y.Z` from the repo root. The script updates all 13 tracked locations and self-verifies by running `tests/test_version_consistency.py`.

2. **Review and commit** — `git add -p` to review every diff, then:
   ```bash
   git commit -m "chore: bump version to X.Y.Z"
   ```

3. **Tag and push** —
   ```bash
   git tag vX.Y.Z
   git push && git push --tags
   ```

4. **CI builds the installer** — the `release.yml` GitHub Actions workflow triggers on the new tag. It builds `NetSentinel-Setup-X.Y.Z.exe` using PyInstaller + Inno Setup, then attaches it to a GitHub Release.

5. **WinGet auto-submits** — the workflow generates the three WinGet manifests (main, installer, locale) from the full template (RULE-R2) and opens a pull request against the `winget-pkgs` community repo. Ookla.Speedtest.CLI is declared as `ExternalDependencies` (not `PackageDependencies`) to avoid blocking installs (RULE-R3).

6. **Verify the release** — once the GitHub Release is published, install from winget on a clean machine to confirm the installer works end-to-end:
   ```powershell
   winget install NetSentinel.NetSentinel
   ```

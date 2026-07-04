# Hardware Integrations

NetSentinel supports any router, modem, access point, NAS, or smart home hub through an open plugin protocol — not just the brands it was built for. The minimal interface is two constants and two Python functions.

---

## Bundled integrations

11 hardware plugins ship with the app, all signed and hash-verified against `data/plugin_hashes.json` (a 12th bundled file, `example_open_ports_report.py`, is an example for the separate *scan*-plugin system used by the Security Audit → Recon Plugins page — see `docs/plugin-authoring.md` — and is not a hardware integration):

| Plugin | Hardware |
|---|---|
| `zte_plugin.py` | ZTE MC889 5G modem (SINR, RSRP, band, cell ID) |
| `deco_plugin.py` | TP-Link Deco XE75 mesh router (nodes, clients, topology) |
| `asus_plugin.py` | ASUS routers and ZenWiFi mesh (via `asusrouter` library) |
| `fritzbox_plugin.py` | AVM FRITZ!Box (DSL/cable, WAN IP, uptime, clients) |
| `unifi_plugin.py` | Ubiquiti UniFi (via UniFi API; requires local controller) |
| `netgear_plugin.py` | Netgear routers (Nighthawk, Orbi via SOAP API) |
| `mikrotik_plugin.py` | MikroTik RouterOS (REST API; v7.1+) |
| `openwrt_plugin.py` | OpenWrt (ubus JSON-RPC API) |
| `synology_plugin.py` | Synology NAS (DSM API; connection stats, uptime) |
| `ha_plugin.py` | Home Assistant (REST API; entity state and attributes) |
| `template_plugin.py` | Starter template for writing a new plugin |

If your hardware is not on this list, see [Writing a new plugin](#writing-a-new-plugin) below. Most consumer hardware takes under 30 minutes to integrate.

---

## The plugin interface

Any `.py` file that satisfies the required interface becomes a first-class integration — it gets its own Hub card, nav entry, health tracking, and sandboxed execution.

### Required

```python
HARDWARE_NAME = "My Router XYZ"   # displayed in the app
HARDWARE_TYPE = "router"           # router | modem | ap | switch | other

def get_info() -> dict:
    """Static metadata: model, firmware version, local IP."""
    return {"model": "XYZ v2", "firmware": "1.2.3", "ip": "192.168.1.1"}

def get_status(config=None) -> dict:
    """Live data polled every N seconds. Accept a `config` kwarg even if
    unused — see CONFIG_SCHEMA below; the poller falls back to calling
    get_status() with no arguments if this raises TypeError."""
    return {"wan_ip": "84.x.x.x", "uptime_sec": 86400, "download_mbps": 450.0}

# Optional — if present, connected clients appear on the plugin's device page
def get_clients() -> list:
    """Each item: {"ip": "...", "mac": "...", "hostname": "..."}"""
    return [...]
```

Neither `get_info` nor `get_status`/`get_clients` may take a *required* positional argument — the validator rejects any of them that do.

**Every outbound request must set a timeout** (e.g. `requests.get(url, timeout=10)`). Without one, an unreachable device blocks the polling thread for the OS-level TCP connect timeout (often 20 s+) with no progress signal.

### Optional constants

| Constant | Type | Purpose |
|---|---|---|
| `HARDWARE_IP` | `str` | Default target IP pre-populated in the credential dialog |
| `DESCRIPTION` | `str` | One-line blurb shown in the plugin catalog |
| `CREDENTIAL_LABEL` | `str` | Label on the password field in the credential dialog (default `"Password"`) |
| `PYPI_PACKAGE` | `str` | pip dependency name; NetSentinel warns at startup if missing |
| `CONFIG_SCHEMA` | `dict` | Typed settings declarations; Hub card auto-generates a config form |
| `ICON_PATH` | `str` | Path to a 24×24 PNG; falls back to a sibling `icon.png`/`.jpg`/`.svg` next to the script |

### `CONFIG_SCHEMA` example

```python
CONFIG_SCHEMA = {
    "poll_interval": {"type": "int",  "default": 30,   "label": "Poll every (seconds)"},
    "verify_ssl":    {"type": "bool", "default": False, "label": "Verify SSL certificate"},
}
```

If `CONFIG_SCHEMA` is present, saved values are passed to `get_status()` as the keyword argument `config={"poll_interval": 30, ...}` — `get_status` must accept it (a plain `config=None` parameter is enough even if you never read it).

### Error classification (required)

`get_status()` and `get_clients()` must catch every exception themselves and report it through `extra.error`, never let it propagate — an uncaught exception is reported as an *unclassified* error and incorrectly counts toward the auto-disable circuit breaker even for something as routine as a wrong password. Use a machine-readable prefix:

| Prefix | Meaning | Counts toward circuit breaker? |
|---|---|---|
| `AUTH:` | Wrong credentials | **No** — a wrong password won't fix itself by retrying, so the card stays in "Re-enter Password" instead of auto-disabling |
| `NET:` | Device unreachable / connection refused / timed out | Yes |
| `DEPS:` | Missing pip package | Yes |
| `ERR:` | Anything else | Yes |

```python
def get_status(config=None) -> dict:
    try:
        ...
        return {"wan_ip": "...", "extra": {}}
    except Exception as exc:
        return {"extra": {"error": _fmt_err(exc)}}
```

Classify by **exception type or HTTP status code first**, falling back to message-keyword matching only when neither is available. A raw `requests.exceptions.ConnectionError`'s message includes the request URL — if that URL's path happens to contain a word like `login` (e.g. `POST /api/login`), naive keyword-only matching misreads a plain connection failure as an `AUTH:` failure. See `_fmt_err()` in `plugins/template_plugin.py`, `plugins/deco_plugin.py`, or `plugins/zte_plugin.py` for the reference implementation:

```python
def _fmt_err(exc: Exception) -> str:
    msg = str(exc)
    if isinstance(exc, ImportError) or "pip install" in msg:
        return "DEPS: " + msg
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "AUTH: " + msg
    if any(w in type(exc).__name__ for w in ("Connection", "Timeout")):
        return "NET: " + msg
    lm = msg.lower()
    if any(w in lm for w in ("refused", "timed out", "unreachable", "no route", "network is")):
        return "NET: " + msg
    if any(w in lm for w in ("auth", "password", "login", "401", "forbidden", "wrong credential")):
        return "AUTH: " + msg
    return "ERR: " + msg
```

---

## Registration lifecycle

When you import a plugin, NetSentinel runs these steps in order:

1. **AST validation** — reads the source via `ast.parse`. No code executes. Checks: `HARDWARE_NAME`/`HARDWARE_TYPE` present, `get_info`/`get_status` defined with no required positional arguments. (The separate `python -m modules.plugin_tools validate` CLI, described below, additionally *warns* — non-blocking — about top-level network calls and imports outside a safe list; the in-app registration check does not.)
2. **Unsigned plugin consent** — if the plugin is not in `data/plugin_hashes.json`, a one-time SHA-256-keyed warning dialog asks for consent before proceeding. Consent is persisted per exact file content.
3. **Credential test** — a dialog collects IP and credentials; `get_info()` + `get_status()` run in a background thread. The plugin is only saved if both calls succeed.
4. **Hub card** — the plugin appears in the Hardware Hub (Extend section) with live status, poll counter, and health state.
5. **In-process polling** — every subsequent poll loads the plugin fresh via `importlib` on a dedicated `QThread` (not a subprocess — this works identically in both source-run and PyInstaller frozen builds, where `sys.executable` is the app's own .exe, not a Python interpreter) and calls `get_info()`/`get_status()`/`get_clients()` directly, wrapped in a broad `try/except`. A crashing plugin cannot bring down the app, but it does share the app's process — heavy CPU work in a plugin will contend with the main thread the way any Python-level exception handling does. Each poll gets a fresh module namespace, so module-level caches (e.g. a cached login session) never leak between polls or between two instances of the same plugin.

---

## Plugin ecosystem features

| Capability | Notes |
|---|---|
| AST validation before import | No code executed during validation; checks required constants and function signatures |
| Live credential test before registration | Runs `get_info()` + `get_status()` in background thread; only saves on success |
| In-process polling, try/except-contained | Each poll runs on a dedicated QThread with a fresh module namespace and a broad exception guard — a buggy plugin cannot crash the app, but it is not process-isolated |
| Multi-instance support | Same plugin type, multiple device IPs — each gets its own Hub card and nav entry |
| Per-instance OS keychain credentials | Password stored under a unique instance ID; zero cross-instance collisions |
| CONFIG_SCHEMA typed config panel | Plugin declares settings; Hub card auto-generates the form |
| Health tracking + circuit breaker | Success/error counters on each card; auto-disables after 10 consecutive *non-AUTH* errors; amber "degraded" state after 24 h without a successful poll |
| Structured error classification | `AUTH:` / `NET:` / `DEPS:` / `ERR:` prefixes route to specific remediation text; `AUTH:` is exempt from the circuit breaker |
| Re-enter Password button | Appears on AUTH errors; reopens credential dialog and restarts worker on success |
| Plugin log console | "≡ Logs" toggle on each Hub card shows the last 100 structured poll log lines |
| Plugin validator CLI | `python -m modules.plugin_tools validate <plugin.py>` — static checks before registering |
| Bundled plugin signing | `data/plugin_hashes.json` SHA-256 list; tampered bundled files blocked at load time |
| Plugin icon support | `icon.png` alongside the script or `ICON_PATH` constant; 24×24 on Hub cards |
| Plugin rename | "✎" button renames the instance; propagates atomically to nav flyout, breadcrumb, command palette |
| Community Browse tab | Fetches a GitHub-hosted JSON index; per-entry SHA-256 verified before download |
| `.nspkg` bundle format | ZIP containing `plugin.py` + `manifest.json` + optional `icon.png` |
| Startup dependency smoke-check | Missing `PYPI_PACKAGE` deps surface as card errors immediately on startup |

---

## Writing a new plugin

The **Hardware Hub** (Extend section) has a built-in **Write a Plugin** tab that walks through the process. Here is the same workflow in full.

### Step 1 — Find your hardware's API

Most consumer hardware exposes one of:

- An **HTTP REST API** — the router admin panel's own backend
- An **HTML scrape target** — older firmware with no JSON API
- **SNMP** — enterprise switches and APs
- **SSH** — OpenWrt, MikroTik, and other open-firmware devices

**Browser dev tools method (works for most consumer routers):**

1. Open your router's admin panel in a browser
2. Press F12 → Network tab → clear the log
3. Navigate to the Status or WAN page
4. Look for JSON responses — these are the API endpoints you need
5. Right-click a request → "Copy as cURL" to get the exact headers and auth tokens

### Step 2 — Generate the template

Click **"⬡ New Plugin"** in the Hardware Hub. Fill in hardware name, type, target IP, and any pip dependencies. A complete `.py` file is generated and opened in your system editor.

### Step 3 — Validate and test

```bash
python -m modules.plugin_tools validate my_plugin.py
```

This performs static analysis without executing code. Then import the plugin in the Hardware Hub — it runs the live credential test before saving.

### Step 4 — Use AI to accelerate (optional)

An AI assistant can write a working plugin for most hardware in about 10 minutes given the right input. The Write a Plugin tab includes three copy-ready prompts (reproduced here — the tab is the source of truth if this ever drifts, see `ui/pages/plugin_guide.py`):

**Prompt A — general (start here):**
```
I want to write a NetSentinel hardware plugin that reads live data from my [Brand] [Model]
router/modem. The admin panel is at http://192.168.1.1. Login: username 'admin', password 'admin'.

Please:
1. Find if this router has a local JSON REST API or requires HTML scraping
2. Write a Python script using requests (with timeout=10 on every call) that logs in and
   returns WAN IP, Uptime, Connected clients (name, IP, MAC)
3. Wrap it in the NetSentinel plugin format:
   - Constants: HARDWARE_NAME (str), HARDWARE_TYPE (must be exactly one of: router, modem,
     ap, switch, other)
   - Functions: get_info(), get_status(), and optionally get_clients() — none may take
     required positional arguments
   - Read the password from the OS keychain via the `keyring` package
     (NetSentinel/hardware/<ip>), never hard-code it
   - Catch every exception inside get_status()/get_clients() and return it as
     {"extra": {"error": "PREFIX: message"}} where PREFIX is AUTH: (wrong credentials),
     NET: (unreachable/timeout), DEPS: (missing pip package), or ERR: (anything else) —
     never let an exception propagate out of these functions
4. Add a main block at the bottom that prints get_info()/get_status()/get_clients() as JSON
5. Tell me which packages to install with pip
```

**Prompt B — from a cURL command (best results):**
```
I captured this API call from my router admin panel using browser dev tools (F12 → Network
→ right-click request → Copy as cURL). Convert it to a Python function using requests, with
timeout=10 on every call.

[Paste your cURL command here]

Then wrap the result in the NetSentinel plugin format:
- Constants: HARDWARE_NAME (str), HARDWARE_TYPE (exactly one of: router, modem, ap, switch, other)
- Functions: get_info(), get_status(), optionally get_clients()
- If the cURL command contains a password, move it to the OS keychain via the `keyring`
  package (NetSentinel/hardware/<ip>) instead of leaving it in the script — do not
  hard-code the captured credential
- Read the device address from a `_NETSENTINEL_INSTANCE_IP` global if present, falling
  back to a HARDWARE_IP constant, so the plugin still works if I add a second device of
  the same type at a different IP
- Catch every exception in get_status()/get_clients() and return it as
  {"extra": {"error": "PREFIX: message"}} — AUTH:/NET:/DEPS:/ERR: — never let an exception
  escape these functions
- if __name__ == '__main__': print all results as JSON
```

**Prompt C — debug an error:**
```
This NetSentinel hardware plugin raises the following error:

[Paste your plugin script here]

[Paste the error message here]

Fix it. Do not change the HARDWARE_NAME, HARDWARE_TYPE, get_info(), or get_status()
signatures, and keep every exception classified with the AUTH:/NET:/DEPS:/ERR: prefix
convention already used in the script.
```

---

## Submitting a plugin

Open a GitHub Issue titled `[Hardware Plugin] Brand Model XYZ` and include:

```
Hardware: Brand Model XYZ
Firmware tested: vX.Y.Z
Access method: HTTP REST / HTML scrape / SNMP / SSH
pip dependencies: requests, beautifulsoup4   (or none)
get_status() returns: wan_ip, uptime_sec, connected_clients, download_mbps, upload_mbps

[attach your .py file]
```

Reviewed scripts are signed (SHA-256 added to `data/plugin_hashes.json`) and merged as built-in integrations. Contributors are credited in release notes.

---

## The `.nspkg` bundle format

`.nspkg` is a ZIP archive that packages a plugin for distribution:

```
my_plugin.nspkg  (ZIP)
├── plugin.py        # the plugin script
├── manifest.json    # name, version, author, hardware_type, pypi_packages
└── icon.png         # optional 24×24 icon
```

**`manifest.json` schema:**

```json
{
  "name":          "My Router XYZ",
  "version":       "1.0.0",
  "author":        "Your Name",
  "hardware_type": "router",
  "pypi_packages": ["requests"]
}
```

Import via **"⬡ Import .nspkg"** in the Hardware Hub. NetSentinel verifies the SHA-256 of `plugin.py` against the manifest before installing.

---

## Validator CLI reference

```bash
# Validate before registering
python -m modules.plugin_tools validate my_plugin.py
python -m modules.plugin_tools validate my_plugin.py --live   # also imports and calls get_info()
```

`validate` is the only CLI subcommand. There is no `pack`/`verify` CLI for `.nspkg` bundles — building one is just zipping `plugin.py` + `manifest.json` (+ optional `icon.png`) yourself per the format above; importing one is done through **"⬡ Import .nspkg"** in the Hardware Hub, which calls `modules.nspkg.unpack_nspkg()` directly.

Validation checks (`python -m modules.plugin_tools validate`):
- **Errors (block registration):** `HARDWARE_NAME`/`HARDWARE_TYPE` present; `get_info()`/`get_status()` present with no required positional arguments
- **Warnings (non-blocking):** no `PYPI_PACKAGE` declared despite external imports; no `HARDWARE_IP`; a possible top-level network call detected at module scope
- **Info (advisory):** no `CREDENTIAL_LABEL`; imports outside the default safe list (`SAFE_IMPORTS` can acknowledge them)

Note the in-app registration flow (triggered by "＋ Add Integration") runs a lighter check than this CLI — it validates required constants and function signatures only, and does not warn about top-level network calls or unusual imports. Run the CLI validator manually if you want those extra checks before registering.

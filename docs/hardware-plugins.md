# Hardware Integrations

NetSentinel supports any router, modem, access point, NAS, or smart home hub through an open plugin protocol — not just the brands it was built for. The minimal interface is two constants and two Python functions.

---

## Bundled integrations

12 plugins ship with the app, all signed and hash-verified against `data/plugin_hashes.json`:

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

def get_status() -> dict:
    """Live data polled every N seconds."""
    return {"wan_ip": "84.x.x.x", "uptime_sec": 86400, "download_mbps": 450.0}

# Optional — if present, connected clients appear on the plugin's device page
def get_clients() -> list:
    """Each item: {"ip": "...", "mac": "...", "hostname": "..."}"""
    return [...]
```

### Optional constants

| Constant | Type | Purpose |
|---|---|---|
| `HARDWARE_IP` | `str` | Default target IP pre-populated in the credential dialog |
| `PYPI_PACKAGE` | `str` | pip dependency name; NetSentinel warns at startup if missing |
| `CONFIG_SCHEMA` | `dict` | Typed settings declarations; Hub card auto-generates a config form |
| `ICON_PATH` | `str` | Path to a 24×24 PNG; displayed on the Hub card and community catalog |

### `CONFIG_SCHEMA` example

```python
CONFIG_SCHEMA = {
    "poll_interval": {"type": "int",  "default": 30,   "label": "Poll every (seconds)"},
    "verify_ssl":    {"type": "bool", "default": False, "label": "Verify SSL certificate"},
}
```

---

## Registration lifecycle

When you import a plugin, NetSentinel runs these steps in order:

1. **AST validation** — reads the source via `ast.parse`. No code executes. Checks: required constants present, required function signatures match, no top-level network calls that would run at import time.
2. **Unsigned plugin consent** — if the plugin is not in `data/plugin_hashes.json`, a one-time SHA-256-keyed warning dialog asks for consent before proceeding. Consent is persisted per-hash.
3. **Credential test** — a dialog collects IP and credentials; `get_info()` + `get_status()` run in a background thread. The plugin is only saved if both calls succeed.
4. **Hub card** — the plugin appears in the Hardware Hub (Extend section) with live status, poll counter, and health state.
5. **Sandboxed polling** — every subsequent poll runs in an isolated subprocess. A buggy script cannot crash the app.

---

## Plugin ecosystem features

| Capability | Notes |
|---|---|
| AST validation before import | No code executed during validation; checks required constants and function signatures |
| Live credential test before registration | Runs `get_info()` + `get_status()` in background thread; only saves on success |
| Sandboxed subprocess execution | Buggy polls cannot crash the app; each poll runs in an isolated namespace |
| Multi-instance support | Same plugin type, multiple device IPs — each gets its own Hub card and nav entry |
| Per-instance OS keychain credentials | Password stored under a unique instance ID; zero cross-instance collisions |
| CONFIG_SCHEMA typed config panel | Plugin declares settings; Hub card auto-generates the form |
| Health tracking + circuit breaker | Success/error counters on each card; auto-disables after 10 consecutive errors; amber "degraded" state after 24 h without a successful poll |
| Structured error classification | `AUTH:` / `DEPS:` / `NET:` / `TIMEOUT:` prefixes route to specific remediation text |
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

An AI assistant can write a working plugin for most hardware in about 10 minutes given the right input. The Write a Plugin tab includes three copy-ready prompts:

**Prompt A — general:**
```
Write a NetSentinel hardware plugin for my [Brand Model] router at [IP].
Required interface: HARDWARE_NAME, HARDWARE_TYPE, get_info(), get_status().
get_info() should return model name and firmware version.
get_status() should return wan_ip, uptime_sec, connected_clients (count), download_mbps, upload_mbps.
The admin panel uses HTTP at [IP] with username/password auth.
```

**Prompt B — from cURL (best results for consumer hardware):**
```
Here is a cURL command captured from my router's admin panel:
[paste cURL]
Convert this into a complete NetSentinel hardware plugin. Use HARDWARE_NAME, HARDWARE_TYPE,
get_info(), and get_status(). Handle authentication the same way the captured request does.
```

**Prompt C — debug:**
```
This NetSentinel hardware plugin raises the following error:
[paste script]
[paste error message]
Fix it. Do not change the HARDWARE_NAME, HARDWARE_TYPE, get_info(), or get_status() signatures.
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

# Build a .nspkg bundle
python -m modules.plugin_tools pack my_plugin.py

# Verify a bundle's manifest and hash
python -m modules.plugin_tools verify my_plugin.nspkg
```

Validation checks:
- `HARDWARE_NAME` and `HARDWARE_TYPE` constants present and correct type
- `get_info()` and `get_status()` present with correct signatures
- No top-level network calls (would execute at import time)
- No imports outside stdlib + declared `PYPI_PACKAGE`
- If `CONFIG_SCHEMA` is present, all entries have `type`, `default`, and `label`

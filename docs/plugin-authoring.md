# Writing Scan Plugins

Scan plugins let you add custom security checks to NetSentinel without modifying core code. They receive the device list from a network scan and return findings.

> **This document covers scan plugins** — Python scripts in the `plugins/` directory that analyse the discovered device list. For integrating hardware (routers, modems, access points), see [Hardware Integrations](hardware-plugins.md) instead. NetSentinel has two distinct plugin systems; they are not interchangeable.

---

## How scan plugins work

Drop a `.py` file into the `plugins/` directory next to the executable, or into `~/.config/NetSentinel/plugins/`. NetSentinel discovers and loads it automatically on the next scan. Plugins appear in the **Security Audit** section of the nav.

Scan plugins are executed in a sandboxed subprocess and cannot crash the main app, but they do have access to the full scan result.

---

## Required interface

Every plugin must expose exactly these two names at module level:

```python
PLUGIN_META = {
    "name":        "My Plugin",          # Display name in the UI
    "version":     "1.0.0",              # Semver string
    "description": "What this checks",  # One sentence, shown on the plugin card
    "author":      "Your Name",
    "tags":        ["routing"],          # Optional — used for filtering in the plugin list
}

def run(devices: list, **kwargs) -> PluginResult:
    ...
```

### `run()` parameters

| Parameter | Type | Description |
|---|---|---|
| `devices` | `list` | `DeviceInfo`-like objects from the most recent Module 1 scan |
| `**kwargs` | `dict` | Reserved for future use — ignore or forward |

Each device object has these attributes:

| Attribute | Type | Notes |
|---|---|---|
| `ip` | `str` | Current IPv4 address |
| `mac` | `str` | MAC address (lowercase, colon-separated) |
| `vendor` | `str` | OUI vendor name from the MAC registry |
| `hostname` | `str` | Best resolved hostname (mDNS > NetBIOS > rDNS) |
| `device_type` | `str` | Classified type: `router`, `printer`, `phone`, `iot`, etc. |
| `os_family` | `str` | OS family if fingerprinted: `Windows`, `Linux`, `macOS`, etc. |
| `risk_level` | `str` | Current risk: `HIGH`, `STORM`, `MEDIUM`, `WARNING`, `LOW`, `CLEAN`, `UNKNOWN` |
| `verdict` | `str` | Human-readable one-line verdict |
| `remediation` | `str` | Suggested remediation action |

Use `getattr(d, "attribute", default)` rather than direct attribute access — future scan methods may not populate every field.

### Return value — `PluginResult`

Import from `modules.plugin_system`:

```python
from modules.plugin_system import PluginResult
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `plugin_name` | `str` | required | Set to `PLUGIN_META["name"]` |
| `findings` | `list[str]` | `[]` | Each string is one finding shown in the report |
| `risk_level` | `str` | `"LOW"` | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `raw_data` | `dict` | `{}` | Arbitrary data for programmatic consumption via REST API |
| `error` | `str` | `""` | Set if the plugin failed; suppresses `findings` in the UI |

`risk_level` on `PluginResult` is the overall severity of the plugin's findings — not the risk level of any individual device. Set it to the worst finding in the list.

---

## Minimal working example

```python
from modules.plugin_system import PluginResult

PLUGIN_META = {
    "name":        "Default Gateway Check",
    "version":     "1.0.0",
    "description": "Flags any device that shares the gateway IP with an unexpected vendor.",
    "author":      "You",
    "tags":        ["routing"],
}

TRUSTED_GATEWAY_VENDORS = {"TP-Link", "ASUS", "Netgear", "Ubiquiti", "MikroTik"}

def run(devices: list, **kwargs) -> PluginResult:
    findings = []
    for d in devices:
        ip = getattr(d, "ip", "")
        vendor = getattr(d, "vendor", "")
        if ip.endswith(".1") and vendor and vendor not in TRUSTED_GATEWAY_VENDORS:
            findings.append(
                f"{ip} ({vendor}) — gateway IP held by an unexpected vendor"
            )
    return PluginResult(
        plugin_name=PLUGIN_META["name"],
        findings=findings,
        risk_level="LOW" if not findings else "MEDIUM",
    )
```

---

## Error handling

Always return a `PluginResult` — never raise an unhandled exception:

```python
def run(devices: list, **kwargs) -> PluginResult:
    try:
        findings = _do_checks(devices)
        return PluginResult(plugin_name=PLUGIN_META["name"], findings=findings)
    except Exception as exc:
        return PluginResult(
            plugin_name=PLUGIN_META["name"],
            error=f"Plugin failed: {exc}",
        )
```

---

## Debugging locally

```bash
# Run the validator (no code executed)
python -m modules.plugin_tools validate my_plugin.py

# Test against a saved scan result (JSON)
python -c "
import json, importlib.util, pathlib
spec = importlib.util.spec_from_file_location('p', 'my_plugin.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

# Load a scan result exported from the app (File → Export → JSON)
devices = json.loads(pathlib.Path('scan_result.json').read_text())
result = p.run(devices)
print(result)
"
```

---

## Constraints

- **No outbound network connections** to addresses outside the local subnet without explicit user action. Plugins that call external APIs will fail the validator.
- **No disk writes** except under a path the user has configured. Use `raw_data` in `PluginResult` to pass data back to the caller.
- **No new dependencies** beyond stdlib and `requirements.txt`. If your plugin needs a new package, declare it in your PR and add it to `requirements.txt`.
- `run()` must return a `PluginResult` in **all code paths** — including exception handlers.
- Do not import `PyQt6` or any UI library. Plugins run outside the main process.

---

## Submitting a scan plugin

Open a pull request with your `.py` file in the `plugins/` directory. The PR description should include:

- What security check the plugin performs and why it matters
- Which device types or conditions trigger a finding
- Example output from a real scan (anonymise IPs if needed)
- Any new pip dependencies and why they are necessary

See the [PR checklist](../CONTRIBUTING.md#pr-checklist) for the full merge requirements.

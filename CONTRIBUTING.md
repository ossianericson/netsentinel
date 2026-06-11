# Contributing to NetSentinel

Thanks for your interest. Contributions are welcome — especially new offenders.json entries, bug fixes, and plugin examples.

For a complete developer guide see **[docs/contributing.md](docs/contributing.md)**.

---

## Dev setup

```bash
git clone https://github.com/ossianericson/netsentinel
cd netsentinel
pip install -r requirements.txt
python app.py              # GUI — add sudo / Run as Administrator for full scan
python cli.py scan         # Headless
python -m pytest tests/ -v --tb=short   # Run all tests
```

On Windows, install [Npcap](https://npcap.com) for packet-capture features (STP, Storm, ARP monitor, DHCP detector). Run as Administrator for those tabs.

### Bumping the version

Never edit version strings manually. Use the script:

```bash
python bump_version.py 1.60
```

This updates all 12 tracked locations atomically and runs the consistency test suite.

### Reporting security vulnerabilities

Please do not open a public issue. Use the [private vulnerability reporting](https://github.com/ossianericson/netsentinel/security/advisories/new) form — response within 48 hours.

---

## Adding an offenders.json entry

`offenders.json` is the MAC OUI database that drives rogue-device detection. Each entry is a JSON object in the top-level array.

### Schema

```json
{
  "vendor": "Device Brand Name",
  "ouis": ["aa:bb:cc", "dd:ee:ff"],
  "known_issues": [
    "One-line description of the Layer-2 behaviour that causes problems"
  ],
  "risk_level": "HIGH",
  "forum_reference": "https://link-to-bug-report-or-forum-thread",
  "remediation": "Plain-English fix for the end user."
}
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `vendor` | string | Human-readable brand name. Used in reports and the UI. |
| `ouis` | array of strings | One or more 6-hex-char OUI prefixes (`aa:bb:cc`). Lowercase, colon-separated. |
| `known_issues` | array of strings | At least one entry. Each string is one sentence describing a specific misbehaviour. |
| `risk_level` | string | Must be exactly one of the values below. |
| `remediation` | string | Actionable plain-English advice for the device owner. |

### `risk_level` values

| Value | When to use |
|---|---|
| `"HIGH"` | Device actively disrupts the network (rogue root bridge, rogue DHCP, ARP spoofing, IPv6 RA injection). |
| `"MEDIUM"` | Device has known issues that degrade performance or expose attack surface but does not actively block traffic. |
| `"LOW"` | Minor nuisance or cosmetic issue — flagged for awareness but not harmful in normal use. |

`forum_reference` is optional but strongly encouraged — a link to a vendor bug tracker, community forum thread, or public write-up gives reviewers confidence that the issue is real.

### Verification before submitting

- Confirm the OUI prefix against [Wireshark's OUI lookup](https://www.wireshark.org/tools/oui-lookup.html).
- Check for duplicates: `grep -i "aa:bb:cc" offenders.json` (replace with your OUI).
- The OUI must be the first three octets of the device's MAC address as it appears in `arp -a` output, not the full MAC.

---

## Plugin authoring guide

NetSentinel's plugin system lets you add custom checks without modifying core code. Drop a `.py` file into the `plugins/` directory next to the executable or into `~/.config/NetSentinel/plugins/`.

### Required module-level attributes

Every plugin must expose exactly these two names at module level:

```python
PLUGIN_META = {
    "name":        "My Plugin",          # Display name in the UI
    "version":     "1.0.0",              # Semver string
    "description": "What this checks",  # One sentence
    "author":      "Your Name",
    "tags":        ["tag1", "tag2"],     # Optional list of category tags
}

def run(devices: list, **kwargs) -> PluginResult:
    ...
```

### `run()` signature

| Parameter | Type | Description |
|---|---|---|
| `devices` | `list` | List of `DeviceInfo`-like objects from the most recent Module 1 scan. Each device has attributes: `ip`, `mac`, `vendor`, `hostname`, `device_type`, `os_family`, `risk_level`, `verdict`, `remediation`. |
| `**kwargs` | dict | Reserved for future use. Ignore or forward. |

### Return value — `PluginResult`

Import from `modules.plugin_system`:

```python
from modules.plugin_system import PluginResult
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `plugin_name` | string | required | Set to `PLUGIN_META["name"]`. |
| `findings` | list of strings | `[]` | Each string is one finding, shown in the report. |
| `risk_level` | string | `"LOW"` | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `raw_data` | dict | `{}` | Arbitrary data for programmatic consumption. |
| `error` | string | `""` | Set if the plugin failed; suppresses `findings` in the UI. |

### Minimal working example

```python
from modules.plugin_system import PluginResult

PLUGIN_META = {
    "name":        "Default Gateway Check",
    "version":     "1.0.0",
    "description": "Flags any device that shares the gateway IP.",
    "author":      "You",
    "tags":        ["routing"],
}

def run(devices: list, **kwargs) -> PluginResult:
    findings = []
    for d in devices:
        if getattr(d, "ip", "") == "192.168.1.1":
            findings.append(f"{d.ip} — gateway IP detected on {getattr(d, 'vendor', '?')}")
    return PluginResult(
        plugin_name=PLUGIN_META["name"],
        findings=findings,
        risk_level="LOW" if not findings else "MEDIUM",
    )
```

### Guidelines

- Plugins must not make outbound network connections to addresses outside the local subnet without explicit user action.
- Plugins must not write to disk except under a path the user has configured.
- Plugins must not import anything that is not in the stdlib or `requirements.txt`. If you need a new dependency, declare it in your PR.
- `run()` must return a `PluginResult` in all code paths — including error paths.

---

## PR checklist

Before submitting a pull request, confirm all of the following:

- [ ] `python -m pytest` passes with no failures or errors.
- [ ] For offenders.json entries: OUI verified, `risk_level` is one of the allowed values, `remediation` is present and actionable.
- [ ] For code changes: no new network calls in tests; all tests mock I/O.
- [ ] For plugins: `PLUGIN_META` and `run()` are present and match the contract above.
- [ ] No credentials, API keys, or secrets are present anywhere in the diff.
- [ ] `requirements.txt` is updated if a new dependency is introduced.
- [ ] The PR description states what problem it solves and on which device/firmware version the behaviour was observed (for offenders.json entries).

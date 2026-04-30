# Microsoft Store Submission Guide

## Before you submit

### 1 — Get your Publisher identity from Partner Center

1. Go to **Partner Center → Apps and games → NetSentinel → Product identity**
2. Copy the **Package/Identity/Publisher** value (looks like `CN=XXXXXX, O=..., C=US`)
3. Open [packaging/AppxManifest.xml](../packaging/AppxManifest.xml) and replace
   `CN=NetSentinel` on the `Publisher=` line with the exact value from Partner Center
4. Also copy the **Package/Identity/Name** value and replace `NetSentinel.NetSentinel`
   on the `Name=` line if Partner Center assigned a different one

### 2 — Sign the MSIX (requires SignPath certificate)

Once SignPath Foundation approves your application:

1. Download the `.pfx` certificate they provide
2. Add two GitHub repository secrets:
   - `SIGNPATH_CERT` — base64-encoded `.pfx` contents: `certutil -encode cert.pfx cert.b64`
   - `SIGNPATH_PASSWORD` — the certificate password
3. The release workflow will then sign the MSIX automatically using `signtool.exe`

*(Until SignPath is set up, the MSIX is unsigned and can only be used for local testing
with Developer Mode enabled)*

### 3 — Trigger a new release to build the MSIX

Push a new version tag (e.g. `v1.56`) — the release workflow produces
`NetSentinel-1.56.msix` automatically and attaches it to the GitHub Release.

---

## Submitting to Partner Center

1. Log in to **partner.microsoft.com/dashboard**
2. Open your **NetSentinel** app reservation → **Start a submission**
3. Fill in:

| Field | Value |
|---|---|
| Category | Utilities & tools |
| Sub-category | System tools |
| Privacy policy URL | `https://ossianericson.github.io/netsentinel/privacy-policy/` |
| Age rating | Complete the IARC questionnaire (General audience) |

4. **Packages** tab — upload the signed `.msix` from the GitHub Release
5. **Store listings** tab — fill in description, screenshots, and keywords

### Recommended description (short)

> Network security scanner for home users and IT professionals. Discovers devices,
> monitors bandwidth, detects rogue devices and STP attacks, and runs connectivity
> diagnostics — all locally, no cloud account required.

### Keywords
network, security, scanner, LAN, rogue device, monitoring, diagnostics, WiFi, DNS, speed test

---

## Restricted capability review

Because NetSentinel declares `runFullTrust` in its manifest, Microsoft will route
your submission to a manual review queue. Expect **1–3 weeks** additional wait time
on the first submission.

Prepare a brief justification email if they ask — suggested text:

> NetSentinel is a desktop network monitoring tool that requires full trust to perform
> raw packet capture via Npcap (for STP/BPDU and ARP analysis), bind to low-numbered
> ports for service monitoring, and run TCP port scans. These operations cannot be
> performed in a sandboxed UWP context. All network data is processed locally and
> never transmitted to any server.

---

## Screenshot requirements

Minimum 1 screenshot, recommended 4–5.
Required size: **1366 × 768** or larger (16:9 aspect ratio preferred).

Suggested screenshots:
1. Home page — Network healthy state with grade circle
2. Device scan results table
3. Bandwidth live chart
4. Security audit page
5. ISP Report export preview

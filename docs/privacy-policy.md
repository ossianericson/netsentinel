# Privacy Policy

**Last updated: 2026-05-01**

NetSentinel is a local desktop application for network monitoring and security analysis.
This policy explains what data the application processes and where it goes.

---

## Data processed locally (never leaves your device)

| Data | Purpose |
|---|---|
| Device IP addresses, MAC addresses, hostnames | LAN device discovery and fingerprinting |
| ARP, BPDU, and broadcast packet metadata | Rogue device and STP analysis |
| Ping latency, DNS response times | Connectivity monitoring and stability scoring |
| Port scan results, OS fingerprint guesses | Security audit pages |
| IoT behavioural baseline logs | Anomaly detection |
| Scan history and reports | Stored in `NetSentinel.db` on your local machine |

All of the above is stored **only on your device**. NetSentinel does not operate any cloud backend and does not transmit this data to the developer or any third party.

---

## Data sent to external services (on explicit user action)

| Action | Service contacted | Data sent |
|---|---|---|
| Speed test | Ookla Speedtest CLI / LibreSpeed | Your public IP, bandwidth measurement |
| CVE lookup | nvd.nist.gov | Software name / version string you type |
| Threat intelligence | VirusTotal API, AbuseIPDB API | IP address you submit for lookup |
| Geo-location | ip-api.com | Your public IP address |
| DNS leak test | Public DNS resolvers | DNS queries to check resolver path |

These requests are made **only when you explicitly trigger them** inside the application. No background telemetry is sent.

---

## No analytics, no accounts, no tracking

- NetSentinel collects no usage analytics.
- There is no user account or registration.
- No advertising identifiers or fingerprinting techniques are used.
- The application does not phone home on startup or in the background.

---

## Local data storage

All application data (scan results, device history, settings) is stored in:

- `NetSentinel.db` — SQLite database in the application directory
- `NetSentinel.ini` — Settings file in the application directory

You can delete these files at any time to remove all stored data.

---

## Contact

If you have questions about this privacy policy, open an issue at
[github.com/ossianericson/netsentinel](https://github.com/ossianericson/netsentinel/issues)
or email **ossian.ericson@gmail.com**.

# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Older releases | No — please upgrade |

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **ossian.ericson@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- The impact — what an attacker could achieve
- Your assessment of severity (if any)

You will receive a response within 48 hours confirming receipt.
If the vulnerability is confirmed, a fix will be released as soon as practical
and you will be credited in the release notes (unless you prefer to remain anonymous).

## Scope

NetSentinel is a local desktop application. In-scope vulnerabilities include:

- Code injection via automation hooks, plugin system, or imported data files
- Privilege escalation beyond what the user explicitly authorised
- Network traffic interception or data exfiltration

Out of scope:

- Attacks requiring physical access to the machine
- Denial of service against the local UI
- Issues in third-party dependencies (report these upstream)

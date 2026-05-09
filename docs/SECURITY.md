# Security Policy

This is a hobby project released under the MIT licence.
It is provided **as-is, with no warranty and no guaranteed support**.
That said, security issues are taken seriously and will be addressed
on a best-effort basis.

## Supported Versions

| Version | Status |
|---------|--------|
| 1.x     | best-effort |

## Reporting a Vulnerability

Please report security vulnerabilities by e-mail to **niwciu@gmail.com**
with the subject line `[SECURITY] SecureLoader`.

**Do not open a public GitHub issue** for security vulnerabilities before
giving me a chance to look at it first.

I will do my best to:
- Acknowledge your report when I have time to review it.
- Release a fix if the issue is within the scope of this project.
- Credit you in the changelog if you wish.

Because this is a hobby project there are no guaranteed response times
or patch deadlines. If you need a commercially supported tool with
an SLA, this project is not the right choice.

## Scope

In scope:
- The CLI tool (`sld` / `secure-loader`)
- The GUI application (`sld-gui`)
- The core firmware parsing and serial protocol libraries

Out of scope:
- Issues in third-party dependencies (report those upstream).
- Vulnerabilities that require physical access to the target device.

## Threat Model

SecureLoader defends against these threats within its own scope:

| Threat | Mitigation |
|--------|-----------|
| Corrupted firmware file | CRC-32 validated before and after every transfer |
| Credential leak via config file | OS keychain (keyring) when available; chmod 0600 fallback |
| Malicious firmware server exhausting memory | 100 MB hard download cap |
| Plaintext firmware over HTTP | Warning logged; HTTPS strongly recommended |
| Path traversal in version string from server | Strict alphanumeric/dot/hyphen regex validation |

Out of threat model (by design):
- Physical access to the target device
- Security of the embedded bootloader itself
- Confidentiality of the firmware binary (no encryption in this tool)
- Availability attacks (DoS) against the host machine

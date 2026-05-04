# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- `GithubReleasesFirmwareSource` — complete integration with private
  GitHub repo (see [docs/GITHUB_SOURCE_MIGRATION.md](docs/GITHUB_SOURCE_MIGRATION.md)).
- Settings dialog in GUI (firmware source selection, PAT entry).

## [1.1.0] — 2026-05-04

Security hardening, audit log, OS keychain credential storage, and CI quality gates.

> ⚠️ **Breaking change:** `sld fetch` and `HttpFirmwareSource` now **reject** plain HTTP
> URLs (`http://`) and disabled TLS verification by default. If your `http.base_url` is set
> to an `http://` address, update it to `https://` or pass `--allow-insecure` explicitly.

### Added

- **Audit log** (`core/audit.py`) — every flash attempt (success or failure) is written
  to a rotating log file (`audit.log`, 1 MB × 5 backups) in the platform config directory
  (e.g. `~/.config/secureloader/audit.log` on Linux).
- **`sld config set-password`** subcommand — secure interactive password prompt (double-entry
  confirmation) that keeps the password out of shell history. A warning is printed whenever
  the less-secure `sld config set http.password <value>` form is used instead.
- **`--allow-insecure` flag** on `sld fetch` — explicit opt-in to allow plain HTTP URLs
  or disabled TLS certificate verification. Both are rejected by default; this flag
  acknowledges and accepts the associated risks for use in controlled lab environments.
- **OS keychain credential storage** via `keyring` (optional `[security]` extra). When
  installed (`pip install ".[security]"`), HTTP credentials are stored in macOS Keychain,
  Windows Credential Manager, or a D-Bus secret store on Linux — never in plaintext on disk.
- **SAST with `bandit`** — static analysis at MEDIUM+ severity runs on every CI push.
  Available locally via `pip install ".[dev]"` → `bandit -r src/ -ll`.
- **Dependency vulnerability scanning with `pip-audit`** — checks all installed packages
  for known CVEs on every CI push. Available locally via `pip-audit --skip-editable`.

### Fixed

- **Protocol state machine race condition** — `Protocol.start_download()` now transitions
  to `State.STARTING` *inside* `_download_lock`. Previously the state change happened after
  the lock was released, leaving a window where the alive-timeout thread could flip state
  back to `CONNECTING` before the `START` command was sent.

### Changed

- **`HttpFirmwareSource`** — plain HTTP URLs and `tls_verify=False` now raise
  `FirmwareSourceError` immediately unless `allow_insecure=True` is passed explicitly.
  This converts a warn-and-proceed behaviour into fail-fast, preventing credentials and
  firmware from being silently transmitted in cleartext.
- **Test suite** expanded from 24 to 133 tests. CI coverage gate raised to 70 %.
- **`[dev]` extras** now include `bandit[toml]` and `pip-audit`.

### Security

- Plain HTTP (`http://`) is now rejected by default in `HttpFirmwareSource._check_base_url()`
  — requires explicit `allow_insecure=True` to proceed. Closes a design gap where an
  `http://` base URL was silently accepted after logging a warning.
- `tls_verify=False` without `allow_insecure=True` now raises `FirmwareSourceError` at
  construction time rather than merely logging a warning.
- CI runs `bandit -r src/ -ll` (MEDIUM/HIGH severity, excluding Qt resource files) and
  `pip-audit --skip-editable` on every push and pull request.

## [1.0.0] — 2026-04-23

First release — Python implementation with Qt6 and separation of core / CLI / GUI layers.

### Added

- **Core** ([src/secure_loader/core/](src/secure_loader/core/)):
  - `firmware` — 48-byte `.bin` header parser (little-endian),
    `license_id` / `unique_id` extraction, `build_device_header` strips
    `prevAppVersion` before sending.
  - `protocol` — serial state machine with commands
    `GET_VERSION/START/NEXT_BLOCK/RESET`, ACK/NAK via XOR,
    500 ms polling, 10 s alive timeout.
  - `sources/` — `FirmwareSource` abstraction with three implementations:
    `LocalFirmwareSource`, `HttpFirmwareSource`,
    `GithubReleasesFirmwareSource` (scaffold).
  - `updater` — `check_device_matches_firmware` checking
    protocol/productID.
- **CLI** ([src/secure_loader/cli/](src/secure_loader/cli/))
  based on Click: `list-ports`, `info`, `fetch`, `flash`, `config`.
  Entry points `secure-loader`, `sld`, `sloader` (CLI) and `sld-gui`, `secure-loader-gui`, `sloader-gui` (GUI).
- **GUI** ([src/secure_loader/gui/](src/secure_loader/gui/))
  in PySide6/Qt6 — window reproducing original `mainwindow.ui` 1:1,
  credentials dialog, `QThread` workers wrapping core.
- **Tests** — 24 pytest tests covering the parser, state machine,
  compatibility check. Run with: `pytest`.

### Security

- Config file saved with `0600` permissions on Unix.
- Credentials do not appear in logs or error messages.

[Unreleased]: https://github.com/niwciu/secureloader/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/niwciu/secureloader/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/niwciu/secureloader/releases/tag/v1.0.0
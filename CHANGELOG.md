# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- `GithubReleasesFirmwareSource` — complete integration with private
  GitHub repo (see [docs/GITHUB_SOURCE_MIGRATION.md](docs/GITHUB_SOURCE_MIGRATION.md)).
- Settings dialog in GUI (firmware source selection, PAT entry).
- Support for tokens in the system keyring.

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

[Unreleased]: https://github.com/niwciu/secureloader/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/niwciu/secureloader/releases/tag/v1.0.0
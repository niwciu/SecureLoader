# Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Mandatory OS keychain credential storage** — `keyring` is now a required
  dependency (previously the optional `[security]` extra).  The HTTP password is
  always stored in macOS Keychain, Windows Credential Manager, or a D-Bus secret
  store on Linux and is **never written to `config.ini`**.  Existing configs that
  still contain a plaintext password are silently migrated to the keychain on the
  first load.

### Changed

- **Section editor — inclusive end display** — the *End* spinbox now shows the
  last nibble *included* in the section (range 0–15) instead of the
  Python-exclusive upper bound (range 1–16), eliminating the confusing appearance
  that adjacent sections share a boundary nibble.  Internal `IdSectionDef`
  storage is unchanged.
- **Section editor — position-based spinbox constraints** — overlap prevention
  now operates on nibble position rather than GUI row order, so a section can be
  freely repositioned across the ID without being blocked by a neighbouring row.
  New sections default to the first uncovered nibble.
- **Product ID visualisation** — the 16-nibble colour strip is now rendered by a
  native `QPainter` widget that scales to the full dialog width.  Section names
  and nibble ranges are displayed in a larger font.

## [2.0.0] — 2026-05-17

This release completes the HTTP firmware download feature, introducing
fully configurable Product ID sectioning and a redesigned Server Settings dialog.

> ⚠️ **Breaking change (bootloader):** the UART wire header shrinks from 48 B to
> 44 B.  Devices running **bootloader v1.0.0** will stall on `CMD_START` (they
> wait for 48 bytes and misparse the first page command).  Flash the updated
> bootloader (v1.1+) to the target device before deploying this release.

> ⚠️ **Breaking change (CLI):** `sld fetch --license / --unique` are replaced by
> `sld fetch --section NAME=VALUE` (repeatable).  Update any scripts that call
> `sld fetch` with the old flags.

### Added

- **Configurable Product ID sections** (`core/id_sections.py`) — the 64-bit
  `productId` can now be split into any number of named sections at nibble
  (half-byte) granularity (0–16).  Each section has a `name`, `start`, and `end`
  nibble position.  The default split matches the EncryptBIN / SecureBootloader
  convention: `custom_id [0:8]`, `hw_id [8:10]`, `license_id [10:12]`,
  `unique_id [12:16]`.
- **`product_id.sections` config key** — serialised as `name:start:end,…`; stored
  in the `[product_id]` INI section.  Configurable via
  `sld config set product_id.sections` or the new GUI section editor.
- **`get_sections(defs)` on `FirmwareHeader` and `DeviceInfo`** — extracts section
  values from `productId` using a list of `IdSectionDef` objects.
- **Redesigned Server Settings dialog** — four groups:
  - *Server* — base URL + allow-insecure checkbox (unchanged).
  - *Credentials* — login / password (unchanged).
  - *Product ID sections* — scrollable section editor (name + start/end spinboxes
    + delete per row, "Add section" button).  A 16-nibble colour-coded hex strip
    visualises the current layout dynamically.
  - *URL path structure* — checklist of defined sections with Up/Down ordering and
    a live URL preview.

### Changed

- **`sld fetch`** — `--license` / `--unique` flags replaced by repeatable
  `--section NAME=VALUE` (e.g. `--section license_id=AB --section unique_id=C0FE`).
  Any section name defined in `product_id.sections` is accepted.
- **`sld config show`** — now includes all `http.*` fields, `product_id.sections`,
  and `ui.instruction_url`.
- **`FirmwareIdentifier`** — redesigned from a frozen dataclass with fixed keyword
  fields to a dict-backed immutable class.  Sections are accessed as attributes
  (`identifier.license_id`) via `__getattr__`; all existing callers using the
  default section names continue to work without changes.
- **Wire header reduced from 48 B to 44 B** — `prevAppVersion` is no longer
  included in the `CMD_START` payload.  The field is still read from the `.bin`
  file and available for host-side rollback logic, but the bootloader
  `header_t` struct no longer contains it (bootloader v1.1+ change).
  `build_device_header()` now returns `file[0:16] + file[20:48]`.
- **`DEVICE_HEADER_SIZE`** constant updated from `48` to `44`.

### Fixed

- **CI workflow** — updated action versions for compatibility with current
  GitHub Actions runner environment.

## [1.2.0] — 2026-05-09

Protocol robustness improvements, GUI diagnostics, and UX polish.

### Added

- **Page Size display** — device and firmware page sizes shown in the GUI with red highlight on mismatch (prevents silent update failure).
- **`sld-gui --debug`** — debug logging is now off by default; pass `--debug` to enable verbose output in the console.
- **"Erasing…" status + indeterminate progress bar** during flash erase (STARTING state); both progress bars reset on disconnect.
- **Allow plain HTTP** checkbox in Server Settings dialog (`allow_insecure` config option).

### Fixed

- **Flash erase timeout** — separate 30 s timeout (`ERASE_TIMEOUT_S`) for the STARTING state prevents premature disconnect while the MCU erases flash.
- **Slow-baud page-write timeout** — SENDING timeout is now dynamic: `(page_size × 10 bits / baudrate) + 2 s margin`, avoiding false disconnects at low baud rates or with large pages.
- **`_last_alive` clock drift** — timestamp now resets when `START` is sent, not on the preceding `GET_VERSION` ACK.

### Changed

- **Protocol command names** aligned with C firmware: `NEXT_BLOCK` → `NEXT_PAGE`, `OK_MASK` → `OK`, `ERROR_MASK` → `ERR`.
- **CONNECTED → CONNECTING timeout** replaced by count-based check: 3 consecutive missed `GET_VERSION` polls (~1.5 s) instead of a fixed 10 s timer.

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

[Unreleased]: https://github.com/niwciu/secureloader/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/niwciu/secureloader/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/niwciu/secureloader/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/niwciu/secureloader/releases/tag/v1.0.0
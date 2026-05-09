# Roadmap — migration to GitHub Releases

This document describes **what, where, and how** to change so that the
application can download firmware from a private GitHub repository (instead
of the legacy HTTP server). The HTTP layer and scaffold are already in
place — this document walks through the **decisions still to be made** and
the **implementation steps**.

## TL;DR

**Already done:**
- `FirmwareSource` abstraction in [core/sources/base.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/core/sources/base.py).
- `GithubReleasesFirmwareSource` scaffold in [core/sources/github.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/core/sources/github.py) —
  HTTP plumbing for GitHub API, Bearer token authorisation,
  `releases/latest` and `releases/tags/{tag}` handling.

**Still needs clarification (design decisions):**
1. Release asset layout in the GHA workflow (asset naming convention).
2. ~~Where to store the PAT (keyring / config / env var).~~ **Done:** OS keychain via
   `keyring` (`[security]` extra). HTTP credentials already use this path; PAT storage
   for the GitHub source should follow the same pattern once the `[github]` config
   section is added.
3. How to identify the release for "previous version".
4. Whether the GH source completely replaces HTTP, or runs alongside it.

**Needs implementation (after decisions):**
1. Complete `_select_asset()` in `github.py`.
2. Add `[github]` section to `config.py`.
3. Expose a source factory (which to use: HTTP or GH).
4. Wire up in GUI (token/repo-link dialog) and CLI (flags).
5. Write tests with a mocked GitHub API.

## Table of Contents

1. [How GitHub API Works for Private Releases](#how-github-api-works-for-private-releases)
2. [Current State — What is Already There](#current-state-what-is-already-there)
3. [Decisions to Make](#decisions-to-make)
4. [Step-by-Step Implementation Plan](#step-by-step-implementation-plan)
5. [Suggested GHA Workflow](#suggested-gha-workflow)
6. [PAT Security](#pat-security)
7. [Test Plan](#test-plan)
8. [Checklist before merge](#checklist-before-merge)

## How GitHub API Works for Private Releases

### Endpoints

| Goal | Method + URL |
|------|-------------|
| Latest release | `GET /repos/{owner}/{repo}/releases/latest` |
| Release by tag | `GET /repos/{owner}/{repo}/releases/tags/{tag}` |
| List releases | `GET /repos/{owner}/{repo}/releases?per_page=100&page=1` |
| Download asset (private) | `GET /repos/{owner}/{repo}/releases/assets/{id}` with `Accept: application/octet-stream` |

**Key detail:** for private repos you must **not** use `browser_download_url`
from the JSON response — it returns an HTML login page. Instead use the
`url` field (API URL) with the `Accept: application/octet-stream` header.
GitHub will then issue a 302 redirect to a signed S3 URL, which `requests`
will follow.

This mechanism is already implemented in `_download_asset()`.

### Authorisation

All requests require the `Authorization: Bearer {token}` header.
GitHub accepts three token types:

| Type | Granularity | Setup | Notes |
|------|------------|-------|-------|
| **Classic PAT** | Per-user, `repo` scope gives access to all user repos | 1 min in Settings → Developer settings | Fastest, but overly broad permissions. |
| **Fine-grained PAT** | Per-repo, `Contents: read` permission | 3 min, requires selecting the repo | **Recommendation.** Minimal permissions. |
| **GitHub App installation token** | Per-installation | Requires creating a GitHub App | For a real commercial product — device flow without PAT. |

Prototypes can start with a Fine-grained PAT. When the application reaches
end-users (non-developers), consider Device Flow.

### Rate Limits

- Authenticated: 5000 req/h.
- One update = 2 requests (`releases/latest` + `assets/{id}` + redirect).
- Negligible in practice for a single desktop tool.

## Current State — What is Already There

### File [core/sources/github.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/core/sources/github.py)

```python
@dataclass(frozen=True, slots=True)
class GithubConfig:
    owner: str
    repo: str
    token: str
    api_base: str = GITHUB_API_BASE

class GithubReleasesFirmwareSource(FirmwareSource):
    def fetch_latest(self, identifier, progress=None) -> bytes: ...
    def fetch_previous(self, identifier, progress=None) -> bytes: ...

    def _select_asset(self, assets, identifier) -> dict:
        """TODO: placeholder heuristic."""

    def _get_json(self, path) -> dict: ...           # done
    def _download_asset(self, asset, progress) -> bytes: ...  # done
```

**Done:**
- Bearer authorisation, headers, timeouts.
- JSON fetch from release.
- Streaming download with progress callback.
- Error handling → `FirmwareSourceError`.

**Placeholder to replace:**
- `_select_asset()` — currently looks for an asset containing `license_id`
  and `unique_id` in the name. This is **not** the target convention — it
  is only a reasonable default to keep the class sensible in isolation.

## Decisions to Make

Three questions that drive everything else.

### Decision 1: how does GHA package firmware in a release?

Three archetypes (each implies a different `_select_asset`):

#### Option A — one asset per product in one release

```
Release tag: v1.2.3
  ├── firmware_AB_C0FE.bin      ← {licenseID}_{uniqueID}.bin
  ├── firmware_AB_C0FF.bin
  └── firmware_CD_DEAD.bin
```

`_select_asset` picks `{license}_{unique}.bin`.

- **+** simplest, single download
- **−** GHA must know about all combinations

#### Option B — one ZIP per release containing multiple `.bin` files

```
Release tag: v1.2.3
  └── firmware-bundle.zip
        ├── AB_C0FE.bin
        ├── AB_C0FF.bin
        └── CD_DEAD.bin
```

`_select_asset` returns the zip, then `fetch_*` unpacks to a temp
directory and reads the relevant file.

- **+** one asset, easy release
- **−** always downloads everything (even if only 30 KB is needed out of 10 MB)
- **−** more complex implementation

#### Option C — separate release per product

```
Release tag: fw-AB-C0FE-v1.2.3
  └── firmware.bin

Release tag: fw-CD-DEAD-v1.2.3
  └── firmware.bin
```

`fetch_latest` cannot use `releases/latest` since that returns whichever
is newest. Requires `releases?per_page=100` and filtering by tag prefix.

- **+** per-product releases independently
- **+** per-product versioning
- **−** more API calls (list + search)
- **−** what if there are > 100 releases?

**Recommendation:** **Option A** — one global release, assets named
`{licenseID}_{uniqueID}.bin` (or `{licenseID}_{uniqueID}_v{version}.bin`
if the version should be visible in the name). Simplest, and business
requirements (per-product release) are not yet clear.

### Decision 2: where to store the PAT?

Three options plus combinations:

| Option | Pro | Con | Extra dependencies |
|--------|-----|-----|--------------------|
| **A. `keyring` (system)** | Secure, per-user, no plaintext on disk | New dependency, on Linux may require `dbus` | `keyring` |
| **B. config.ini (chmod 0600)** | Zero dependencies, simple | Plaintext on disk, bad model on shared machines | — |
| **C. ENV `GITHUB_TOKEN`** | No persistence, CI-friendly | User must export it manually | — |
| **D. Device Flow** | Professional, no PAT | GitHub App + server refresh logic | `requests` already present |

**Recommendation:** `A + C` — primary via `keyring`, fallback to the
`GITHUB_TOKEN` env var. Config.ini stores only *metadata* (`owner`,
`repo`), never the token itself.

Additional argument for `keyring`: Windows Credential Manager, GNOME
Keyring, macOS Keychain are transparent to the user. First entry in the
GUI → persists forever without a file on disk.

### Decision 3: "previous version" — how to identify?

The `fetch_previous` method uses the `prevAppVersion` field from
the current firmware header. With GitHub there are three options:

1. **Tag = appVersion** (numeric or hex). The application reads
   `prevAppVersion` from the header, calls `releases/tags/0x01020300`.
   Requires a GHA convention: the tag must match exactly what is stored
   in the header.
2. **Release list + filtering.** `releases?per_page=20`, take the second
   from the top.
3. **Custom asset name per version.** `firmware_{lic}_{uniq}_v{version}.bin`
   — a single global release holds all version assets; `fetch_previous`
   filters by version suffix.

**Recommendation:** option 1 (tag = appVersion). It is unambiguous,
deterministic, and probably closest to what GHA will tag anyway
(tag = app version).

### Decision 4: HTTP and GH in parallel, or GH only?

The current code already supports **both in parallel** — source selection
happens in a factory (see [plan](#step-by-step-implementation-plan)).

Suggestion:
- During migration: both, with a `ui.firmware_source = http | github`
  flag in config.
- After migration: remove HTTP + `HttpFirmwareSource` + legacy credentials.

## Step-by-Step Implementation Plan

The steps below assume **Option A + keyring + tag = appVersion**.
Other choices follow analogously.

### Step 1 — complete `_select_asset()` in [github.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/core/sources/github.py)

Replace the current heuristic with a deterministic convention:

```python
def _select_asset(self, assets, identifier):
    lic = identifier.license_id.upper()
    uid = identifier.unique_id.upper()
    expected = f"{lic}_{uid}.bin"
    for a in assets:
        if a["name"].upper() == expected:
            return a
    names = sorted(a["name"] for a in assets)
    raise FirmwareSourceError(
        f"no asset named {expected!r}; available: {names}"
    )
```

If you chose Option B (ZIP), you also need to rewrite `fetch_latest` /
`fetch_previous`, not just `_select_asset` — the flow changes
(download + unzip + selection from inside).

### Step 2 — add `[github]` section to [config.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/config.py)

Add to `AppConfig`:

```python
@dataclass
class AppConfig:
    # ...existing fields...
    firmware_source: str = "http"           # "http" | "github"
    github_owner: str = ""
    github_repo: str = ""
    # NOTE: token is NOT a field of AppConfig; it goes to keyring.
```

Add to `load_config`:

```python
gh = parser["github"] if parser.has_section("github") else {}
config.firmware_source = ui.get("firmware_source", "http")
config.github_owner = gh.get("owner", "")
config.github_repo = gh.get("repo", "")
```

And symmetrically in `save_config`.

### Step 3 — add a `secrets.py` module

New file [src/secure_loader/secrets.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/secrets.py)
(TODO, does not exist yet):

```python
"""Secure storage for access tokens."""
from __future__ import annotations
import os
import keyring

SERVICE = "secureloader"
USER_GITHUB = "github-pat"

def get_github_token() -> str | None:
    # Priority: env var → keyring
    env = os.environ.get("GITHUB_TOKEN")
    if env:
        return env
    try:
        return keyring.get_password(SERVICE, USER_GITHUB)
    except keyring.errors.KeyringError:
        return None

def set_github_token(token: str) -> None:
    keyring.set_password(SERVICE, USER_GITHUB, token)

def delete_github_token() -> None:
    try:
        keyring.delete_password(SERVICE, USER_GITHUB)
    except keyring.errors.PasswordDeleteError:
        pass
```

In `pyproject.toml`:

```toml
dependencies = [
    ..."keyring>=24.0",
]
```

### Step 4 — source factory

New file [src/secure_loader/core/sources/factory.py](https://github.com/niwciu/secureloader/blob/main/src/secure_loader/core/sources/factory.py)
(TODO):

```python
"""Creates a FirmwareSource based on the current configuration."""
from __future__ import annotations
from ...config import AppConfig
from ...secrets import get_github_token
from . import FirmwareSource
from .github import GithubConfig, GithubReleasesFirmwareSource
from .http import HttpFirmwareSource

def make_source(config: AppConfig) -> FirmwareSource:
    if config.firmware_source == "github":
        token = get_github_token()
        if not token:
            raise RuntimeError("GitHub token not configured")
        return GithubReleasesFirmwareSource(
            GithubConfig(
                owner=config.github_owner,
                repo=config.github_repo,
                token=token,
            )
        )
    return HttpFirmwareSource(
        base_url=config.http_base_url,
        credentials=config.credentials(),
    )
```

All places that currently instantiate `HttpFirmwareSource(...)` (CLI
`fetch_cmd`, GUI `_start_fetch`) should be replaced with `make_source(config)`.

### Step 5 — CLI

Add to `sld config set` the keys:
- `firmware_source` — `"http"` or `"github"`.
- `github.owner` / `github.repo`.

Add a command `sld token set` / `sld token clear` (write/delete the
token in keyring). Alternatively `sld config set github.token <value>`
with a custom handler that saves to keyring, not to the file.

Add override flags:
- `sld fetch --source github --repo owner/name`.

### Step 6 — GUI

`Settings` dialog (new) with tabs:
- **Server:** select `http | github`, HTTP server URL, owner/repo.
- **Credentials:** HTTP login/password (as today), + GitHub PAT (masked,
  saved to keyring).

The existing `LoginDialog` can be extended or left as is with a separate
`SettingsDialog`. A separate dialog is recommended.

Add a `Settings...` entry to the `Credentials` menu.

### Step 7 — documentation

Update:
- [README.md](https://github.com/niwciu/secureloader/blob/main/README.md) — "Firmware sources" section + info about
  the `GITHUB_TOKEN` env var.
- [ARCHITECTURE.md](ARCHITECTURE.md) — "Configuration" section
  (new fields, `[github]` section, keyring).

## Suggested GHA Workflow

Example `.github/workflows/release-firmware.yml`:

```yaml
name: Release firmware

on:
  push:
    tags: ['v*.*.*']

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write   # required for creating releases

    steps:
      - uses: actions/checkout@v4

      - name: Build firmware for all products
        run: |
          # TODO: fill in your own build and encryption pipeline
          # Output: release-assets/{licenseID}_{uniqueID}.bin
          mkdir -p release-assets
          make all-firmware OUTDIR=release-assets

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          files: release-assets/*.bin
          draft: false
          prerelease: false
```

Key assumptions for this workflow:
- **Tag** = app version (corresponds to the `appVersion` field in the
  header — can be semver or hex format).
- **File names** = `{licenseID}_{uniqueID}.bin` (to match the convention
  in `_select_asset`).
- The repo is **private**, so the release is also private — access only
  for authorised tokens.

### If appVersion is in hex format

Tag-to-hex conversion is straightforward, but must be consistent:

- Tag: `v0x01020304` → appVersion `0x01020304` in the header.
- Or: tag `v1.2.3.4`, and `appVersion` in the header is
  `(1<<24)|(2<<16)|(3<<8)|4`.

The application must be able to map `prevAppVersion` → tag. Currently
`fetch_previous` calls `releases/tags/{app_version}`, where
`app_version` is the string produced by `format_prev_app_version()`
(e.g. `"0x01020300"`). Ensure that GHA tags releases in exactly the same
convention, or add a mapping in `GithubReleasesFirmwareSource`.

## PAT Security

- **Never commit the token.** `.gitignore` already excludes `config.ini`
  because it lives outside the repo (user config dir), but keyring is better.
- **Minimal scope.** Fine-grained PAT with `Contents: read` on the specific
  repo. Not a classic PAT with `repo`.
- **Rotation.** Fine-grained PATs expire after at most 1 year — plan the
  UX for rotation (the GUI should handle 401 gracefully → "token expired,
  enter a new one" dialog).
- **Logs.** Make sure the token never ends up in logs. `logging` in
  `_headers()` could accidentally leak it — add masking via
  `logging.Filter` if DEBUG is enabled.
- **In-memory leak.** Python does not guarantee string zeroing. For a
  desktop tool this is acceptable; for highly sensitive use-cases consider
  `secrets` with `mlock`.

## Test Plan

Tests for `GithubReleasesFirmwareSource` should:

1. **Mock `requests.Session`** (via `pytest-mock` or `responses`).
2. Cover:
   - Happy path `fetch_latest` — mock `releases/latest` → mock asset
     download → returns expected bytes.
   - `fetch_previous` with app_version — mock `releases/tags/{tag}`.
   - No matching asset → `FirmwareSourceError`.
   - 401 / 403 / 404 from API → `FirmwareSourceError` with a useful message.
   - Progress callback is called during streaming.
   - `_select_asset` picks an exact match in preference to a partial one.
3. Never hit the real GitHub.

Skeleton (TODO):

```python
# tests/test_sources_github.py
import pytest
from unittest.mock import MagicMock
from secure_loader.core.sources import FirmwareIdentifier
from secure_loader.core.sources.github import (
    GithubConfig, GithubReleasesFirmwareSource,
)

@pytest.fixture
def config():
    return GithubConfig(owner="acme", repo="fw", token="fake")

@pytest.fixture
def session(mocker):
    s = MagicMock()
    return s

class TestFetchLatest:
    def test_returns_selected_asset_bytes(self, config, session):
        # 1) mock releases/latest → {"assets": [{"name": "AB_C0FE.bin", "url": ".../1", "size": 4}]}
        # 2) mock asset download → bytes b"abcd"
        # 3) call fetch_latest
        # 4) assert result == b"abcd"
        ...
```

## Checklist before merge

Before shipping the GH source as production-ready:

- [ ] `_select_asset` implemented according to the agreed convention.
- [ ] Unit tests covering `GithubReleasesFirmwareSource`.
- [ ] Token in keyring, not in file (if Option A was chosen).
- [ ] `GITHUB_TOKEN` env var honoured for CI/automation.
- [ ] GUI: settings dialog allows selecting source + entering owner/repo/PAT.
- [ ] CLI: `--source` flag and `sld token set` command.
- [ ] 401/403 handling in GUI: clear error + offer to renew the token.
- [ ] GHA workflow updated and tested on a dev repo.
- [ ] README + ARCHITECTURE updated.
- [ ] Migration path for existing users (their `config.ini` still works
      with `http` as default).
- [ ] Decision: whether the HTTP source stays as fallback or is removed.

## Appendix — if Device Flow is needed

If you eventually distribute the tool to end-users (non-developers),
Device Flow is more user-friendly than pasting a PAT:

1. The tool calls `POST https://github.com/login/device/code` with the
   `client_id` of the application (a GitHub App created once).
2. GitHub returns `device_code`, `user_code`, `verification_uri`.
3. The tool shows the user: "Go to `github.com/login/device` and enter
   `XXXX-YYYY`".
4. The tool polls `POST https://github.com/login/oauth/access_token`
   every 5 s until the user approves.
5. Receives an `access_token` (plus `refresh_token` if the GitHub App
   has that option enabled).

Advantages: no PAT is ever requested, the token is tied to the
application not the user, and it can be revoked for everyone at once.

Disadvantage: requires registering a GitHub App (free), and maintaining
`client_id`/`client_secret` — client_secret must not be in the binary,
so either a public client (PKCE) or a serverside hop is needed.

This is an advanced topic — a Fine-grained PAT in keyring is sufficient
for now.

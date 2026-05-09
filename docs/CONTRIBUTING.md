# 🤝 Contributing

This document covers everything needed to develop, test, and extend SecureLoader.

## 📋 Table of Contents

1. [Dev Environment Setup](#-dev-environment-setup)
2. [Running Tests](#-running-tests)
3. [Code Style and Linting](#-code-style-and-linting)
4. [Project Layout](#-project-layout)
5. [Adding a Firmware Source](#-adding-a-firmware-source)
6. [Adding a Language](#-adding-a-language)
7. [Building a Standalone Executable](#-building-a-standalone-executable)
8. [Building the Documentation](#-building-the-documentation)
9. [Submitting Changes](#-submitting-changes)

---

## 🛠️ Dev Environment Setup

Python 3.10 or later is required. A virtual environment is strongly recommended.

```bash
git clone https://github.com/niwciu/SecureLoader.git
cd SecureLoader

python -m venv .venv
source .venv/bin/activate       # Linux / macOS
.venv\Scripts\activate          # Windows

pip install -e ".[gui,dev]"
```

This installs the CLI (`sld`), the GUI (`sld-gui`), and all development tools:
pytest, ruff, mypy, black, flake8, bandit, and pip-audit.

---

## 🧪 Running Tests

```bash
pytest                            # run all tests
pytest -v                         # verbose output
pytest --cov=src -v               # with coverage
pytest tests/test_firmware.py     # single file
pytest tests/test_firmware.py::TestParseHeader::test_round_trips_known_values
```

Tests cover the core layer only. The protocol state machine is tested by
feeding bytes directly into `_handle_byte()` — no physical device or mocked
serial library is required.

---

## 🎨 Code Style and Linting

All tools are configured in [`pyproject.toml`](https://github.com/niwciu/SecureLoader/blob/main/pyproject.toml):

| Tool | Command | Notes |
|------|---------|-------|
| **ruff** | `ruff check .` | Primary linter. Auto-fixable issues: `ruff check --fix .` |
| **flake8** | `flake8 src tests` | Additional style checks |
| **black** | `black src tests` | Auto-formatter. Run before committing. |
| **mypy** | `mypy src` | Strict type checking. All public APIs must be fully typed. |
| **bandit** | `bandit -r src/ -ll -x src/secure_loader/gui/resources` | SAST — reports MEDIUM and above severity findings. |
| **pip-audit** | `pip-audit --skip-editable` | Dependency vulnerability scan. |

Line length is **100** for all tools. Ruff rule set: `E, F, W, I, N, UP, B, SIM, RUF`
(E501 ignored — black handles length).

Mypy runs in `--strict` mode. Every public function and method must carry type
annotations. `# type: ignore` comments require a specific error code (e.g.
`# type: ignore[import-not-found]`).

---

## 📁 Project Layout

```
src/secure_loader/
├── __init__.py            # __version__, __app_name__
├── config.py              # Cross-platform INI config (platformdirs + configparser)
├── i18n/
│   └── __init__.py        # Lightweight in-process translations
├── core/
│   ├── audit.py           # Rotating flash-attempt audit log (1 MB × 5)
│   ├── firmware.py        # Binary header parser
│   ├── protocol.py        # Serial state machine + driver
│   ├── updater.py         # Firmware/device compatibility check
│   └── sources/
│       ├── base.py        # FirmwareSource ABC + FirmwareIdentifier
│       ├── local.py       # Read from disk
│       ├── http.py        # HTTP server download (HTTPS by default; allow_insecure opt-in)
│       └── github.py      # GitHub Releases scaffold (intentionally incomplete)
├── cli/
│   └── main.py            # Click CLI entry point (sld)
└── gui/
    ├── app.py             # QApplication bootstrap
    ├── main_window.py     # Main window
    ├── login_dialog.py    # HTTP credentials dialog
    └── workers.py         # QThread wrappers for core

tests/
├── conftest.py            # Shared fixtures (sample_firmware, sample_header_bytes)
├── test_firmware.py       # Header parser + helpers
├── test_protocol.py       # Protocol state machine
├── test_updater.py        # Compatibility check
├── test_config.py         # Config load/save + keyring integration
├── test_http_source.py    # HttpFirmwareSource (URL encoding, TLS, auth, size cap)
├── test_local_source.py   # LocalFirmwareSource
├── test_github_source.py  # GithubReleasesFirmwareSource (mocked API)
├── test_cli.py            # CLI commands: config set/show/path, fetch, flash confirmation
├── test_cli_flash.py      # CLI flash command integration (Protocol mock)
├── test_audit.py          # Audit log rotation and entry format
└── test_gui.py            # GUI smoke tests (QT_QPA_PLATFORM=offscreen)

docs/                      # MkDocs documentation source
install_scripts/           # Build and install scripts (build.sh / build.bat)
```

**Strict import rule:** `core/` never imports from `cli/` or `gui/`. CLI and GUI
import core but not each other.

---

## ➕ Adding a Firmware Source

1. Create `src/secure_loader/core/sources/mysource.py`.
2. Subclass `FirmwareSource` from `base.py` and implement both abstract methods:

```python
from .base import FirmwareSource, FirmwareIdentifier, FirmwareSourceError, ProgressCallback

class MyFirmwareSource(FirmwareSource):
    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        ...

    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        ...
```

3. Export from `src/secure_loader/core/sources/__init__.py`.
4. Wire it up in CLI (`cli/main.py`) and/or GUI (`gui/main_window.py`).
5. Add tests in `tests/`.

Both CLI and GUI depend only on the `FirmwareSource` abstract interface for
network-fetch paths, so the wiring step is the only frontend change required.

---

## 🌐 Adding a Language

All translations live in `src/secure_loader/i18n/__init__.py` as a Python
dictionary — no `msgfmt` or `.mo` compilation step is needed.

1. Add the language code to `SUPPORTED`:
   ```python
   SUPPORTED: tuple[Language, ...] = ("en", "de", "fr", "es", "it", "pl", "xx")
   ```
   And update the `Language` Literal type accordingly.

2. Add a translation dictionary under `TRANSLATIONS`:
   ```python
   "xx": {
       "Connect": "...",
       "Disconnect": "...",
       # ... (copy the "de" block as a template)
   }
   ```
   Keys that are missing fall back to the English string automatically.

3. Add the language to `_LANGUAGES` in `gui/main_window.py` so it appears
   in the Language menu:
   ```python
   _LANGUAGES: list[tuple[str, str]] = [
       ...
       ("xx", "My Language"),
   ]
   ```

---

## 🏗️ Building a Standalone Executable

PyInstaller is supported via the optional `[build]` extra:

```bash
pip install -e ".[build]"
```

**Linux / macOS:**

```bash
pyinstaller \
    --name="sld-gui" \
    --icon=src/secure_loader/gui/resources/icons/icon.png \
    --windowed \
    --onefile \
    -p src \
    src/secure_loader/gui/app.py
```

**Windows:**

```bat
pyinstaller ^
    --name="sld-gui" ^
    --icon=src/secure_loader/gui/resources/icons/icon.ico ^
    --windowed ^
    --onefile ^
    -p src ^
    src/secure_loader/gui/app.py
```

The resulting binary will be in `dist/`.

Alternatively, use the provided scripts in `install_scripts/` which automate
the virtual environment setup, dependency installation, and PyInstaller invocation:

```bash
# Linux / macOS
cd install_scripts && ./build.sh

# Windows
cd install_scripts && build.bat
```

---

## 📚 Building the Documentation

The documentation site is built with [MkDocs](https://www.mkdocs.org/) and
the [Material theme](https://squidfunk.github.io/mkdocs-material/).

Install the documentation dependencies:

```bash
pip install mkdocs mkdocs-material pymdown-extensions
```

Serve locally with live reload:

```bash
mkdocs serve
```

Then open `http://127.0.0.1:8000` in your browser.

Build a static site for deployment:

```bash
mkdocs build
```

The output is written to `site/`. Deploy to GitHub Pages:

```bash
mkdocs gh-deploy
```

---

## 🚀 Submitting Changes

1. Fork the repository and create a feature branch.
2. Run `black src tests`, `ruff check .`, `flake8 src tests`, and `mypy src` —
   all must pass cleanly.
3. Run `pytest --cov=src/secure_loader --cov-fail-under=70` — all tests must pass with
   coverage at or above 70 %.
4. Run `bandit -r src/ -ll -x src/secure_loader/gui/resources` — no MEDIUM or HIGH findings.
5. Run `pip-audit --skip-editable` — no known vulnerabilities.
6. Open a pull request with a clear description of what changed and why.

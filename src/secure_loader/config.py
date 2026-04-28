"""Cross-platform configuration storage.

Uses :mod:`platformdirs` to resolve the correct per-user config location:

* Linux:   ``~/.config/secureloader/config.ini``
* Windows: ``%APPDATA%\\secureloader\\config.ini``
* macOS:   ``~/Library/Application Support/secureloader/config.ini``

The format is INI (:mod:`configparser`) so it is trivially editable by hand
and does not require any additional dependencies.

For backwards compatibility we also read legacy credentials from the
``QSettings("microAQUA", "cridential")`` location when they exist and the
new config does not (see :func:`_load_legacy_credentials`).
"""

from __future__ import annotations

import configparser
import contextlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from .core.sources.http import DEFAULT_BASE_URL, HttpCredentials

log = logging.getLogger(__name__)

APP_DIR_NAME: str = "secureloader"
APP_AUTHOR: str = "niwciu"
CONFIG_FILENAME: str = "config.ini"


def config_dir() -> Path:
    return Path(user_config_dir(APP_DIR_NAME, APP_AUTHOR, ensure_exists=True))


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


@dataclass
class AppConfig:
    """Mutable, in-memory representation of the user configuration."""

    http_base_url: str = DEFAULT_BASE_URL
    http_login: str = ""
    http_password: str = ""
    language: str = "auto"  # "en" | "de" | "fr" | "es" | "it" | "pl" | "auto"
    update_instruction_url: str = ""  # empty = menu item hidden
    last_firmware_paths: list[str] = field(default_factory=list)

    def credentials(self) -> HttpCredentials | None:
        if not self.http_login and not self.http_password:
            return None
        return HttpCredentials(login=self.http_login, password=self.http_password)


def load_config(path: Path | None = None) -> AppConfig:
    """Read the config file, filling in defaults and legacy values."""
    cfg_path = path or config_path()
    parser = configparser.ConfigParser()
    if cfg_path.exists():
        parser.read(cfg_path, encoding="utf-8")

    http = parser["http"] if parser.has_section("http") else {}
    ui = parser["ui"] if parser.has_section("ui") else {}
    recent = parser["recent"] if parser.has_section("recent") else {}

    config = AppConfig(
        http_base_url=http.get("base_url", DEFAULT_BASE_URL),
        http_login=http.get("login", ""),
        http_password=http.get("password", ""),
        language=ui.get("language", "auto"),
        update_instruction_url=ui.get("instruction_url", ""),
        last_firmware_paths=[recent[key] for key in sorted(recent) if key.startswith("firmware_")],
    )

    # One-time migration from the original QSettings location.
    if not config.http_login and not config.http_password:
        legacy = _load_legacy_credentials()
        if legacy is not None:
            config.http_login, config.http_password = legacy
            log.info("imported legacy credentials from QSettings")

    return config


def save_config(config: AppConfig, path: Path | None = None) -> None:
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    parser = configparser.ConfigParser()
    parser["http"] = {
        "base_url": config.http_base_url,
        "login": config.http_login,
        "password": config.http_password,
    }
    parser["ui"] = {
        "language": config.language,
        "instruction_url": config.update_instruction_url,
    }
    parser["recent"] = {
        f"firmware_{i}": path for i, path in enumerate(config.last_firmware_paths[:10])
    }

    tmp = cfg_path.with_suffix(cfg_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        parser.write(fh)
    os.replace(tmp, cfg_path)
    with contextlib.suppress(OSError):  # chmod is unavailable on Windows
        os.chmod(cfg_path, 0o600)


def _load_legacy_credentials() -> tuple[str, str] | None:
    """Import credentials from the original QSettings("microAQUA","cridential") store.

    Returns ``None`` when no legacy data is present or when PySide6 is not
    installed (the GUI is an optional dependency).
    """
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        return None

    settings = QSettings("microAQUA", "cridential")
    settings.beginGroup("login_and_password")
    login = settings.value("login", "", type=str)
    password = settings.value("password", "", type=str)
    settings.endGroup()
    if not login and not password:
        return None
    return (str(login), str(password))

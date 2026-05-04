"""Cross-platform configuration storage.

Uses :mod:`platformdirs` to resolve the correct per-user config location:

* Linux:   ``~/.config/secureloader/config.ini``
* Windows: ``%APPDATA%\\secureloader\\config.ini``
* macOS:   ``~/Library/Application Support/secureloader/config.ini``

The format is INI (:mod:`configparser`) so it is trivially editable by hand
and does not require any additional dependencies.
"""

from __future__ import annotations

import configparser
import contextlib
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

from .core.sources.http import DEFAULT_BASE_URL, HttpCredentials

log = logging.getLogger(__name__)

try:
    import keyring as _keyring

    _KEYRING_SERVICE = "secureloader"
    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover
    _keyring = None  # type: ignore[assignment]
    _KEYRING_AVAILABLE = False

APP_DIR_NAME: str = "secureloader"
APP_AUTHOR: str = "niwciu"
CONFIG_FILENAME: str = "config.ini"

# Protects concurrent in-process load/save (e.g. GUI thread + CLI invocation
# running in the same process, or multiple QThread workers calling save_config).
_config_lock = threading.Lock()


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
    """Read the config file, filling in defaults for any missing keys."""
    with _config_lock:
        return _load_config_locked(path)


def _load_config_locked(path: Path | None) -> AppConfig:
    cfg_path = path or config_path()
    parser = configparser.ConfigParser()
    if cfg_path.exists():
        parser.read(cfg_path, encoding="utf-8")

    http = parser["http"] if parser.has_section("http") else {}
    ui = parser["ui"] if parser.has_section("ui") else {}
    recent = parser["recent"] if parser.has_section("recent") else {}

    cfg = AppConfig(
        http_base_url=http.get("base_url", DEFAULT_BASE_URL),
        http_login=http.get("login", ""),
        http_password=http.get("password", ""),
        language=ui.get("language", "auto"),
        update_instruction_url=ui.get("instruction_url", ""),
        last_firmware_paths=[recent[key] for key in sorted(recent) if key.startswith("firmware_")],
    )
    if _KEYRING_AVAILABLE and cfg.http_login:
        stored = _keyring.get_password(_KEYRING_SERVICE, cfg.http_login)
        if stored is not None:
            cfg.http_password = stored
    return cfg


def save_config(config: AppConfig, path: Path | None = None) -> None:
    with _config_lock:
        _save_config_locked(config, path)


def _save_config_locked(config: AppConfig, path: Path | None) -> None:
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if _KEYRING_AVAILABLE and config.http_login:
        try:
            _keyring.set_password(_KEYRING_SERVICE, config.http_login, config.http_password)
            ini_password = ""
        except Exception:
            log.warning("keyring write failed — storing HTTP password in plaintext")
            ini_password = config.http_password
    else:
        if config.http_password:
            log.warning(
                "keyring not installed — storing HTTP password in plaintext. "
                "Install the 'keyring' package for secure storage."
            )
        ini_password = config.http_password

    parser = configparser.ConfigParser()
    parser["http"] = {
        "base_url": config.http_base_url,
        "login": config.http_login,
        "password": ini_password,
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

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

import keyring
from platformdirs import user_config_dir

from .core.id_sections import (
    DEFAULT_ID_SECTIONS,
    IdSectionDef,
    parse_id_sections,
    serialize_id_sections,
)
from .core.sources.http import DEFAULT_BASE_URL, DEFAULT_PATH_SEGMENTS, HttpCredentials

log = logging.getLogger(__name__)

_KEYRING_SERVICE = "secureloader"

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
    http_use_credentials: bool = False
    http_allow_insecure: bool = False
    http_path_segments: list[str] = field(default_factory=lambda: list(DEFAULT_PATH_SEGMENTS))
    id_section_defs: list[IdSectionDef] = field(
        default_factory=lambda: list(DEFAULT_ID_SECTIONS)
    )
    language: str = "auto"  # "en" | "de" | "fr" | "es" | "it" | "pl" | "auto"
    update_instruction_url: str = ""  # empty = menu item hidden
    last_firmware_paths: list[str] = field(default_factory=list)

    def credentials(self) -> HttpCredentials | None:
        if not self.http_use_credentials:
            return None
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
    product_id_sec = parser["product_id"] if parser.has_section("product_id") else {}

    _raw_segs = http.get("path_segments", "")
    path_segments = (
        [s.strip() for s in _raw_segs.split(",") if s.strip()]
        if _raw_segs.strip()
        else list(DEFAULT_PATH_SEGMENTS)
    )
    _login = http.get("login", "")
    _use_creds_raw = http.get("use_credentials", "")
    # Backward compat: if the key is absent, infer True when a login is already stored.
    http_use_credentials = _use_creds_raw.lower() == "true" if _use_creds_raw else bool(_login)

    _raw_id_sections = product_id_sec.get("sections", "")
    try:
        id_section_defs = parse_id_sections(_raw_id_sections)
    except ValueError:
        log.warning("product_id.sections is malformed — using defaults")
        id_section_defs = list(DEFAULT_ID_SECTIONS)

    http_password = _resolve_password(_login, http.get("password", ""))

    cfg = AppConfig(
        http_base_url=http.get("base_url", DEFAULT_BASE_URL),
        http_login=_login,
        http_password=http_password,
        http_use_credentials=http_use_credentials,
        http_allow_insecure=http.get("allow_insecure", "false").lower() == "true",
        http_path_segments=path_segments,
        id_section_defs=id_section_defs,
        language=ui.get("language", "auto"),
        update_instruction_url=ui.get("instruction_url", ""),
        last_firmware_paths=[recent[key] for key in sorted(recent) if key.startswith("firmware_")],
    )
    return cfg


def _resolve_password(login: str, ini_password: str) -> str:
    """Return the password from the keychain, migrating a plaintext INI value if needed."""
    if not login:
        return ""
    try:
        stored = keyring.get_password(_KEYRING_SERVICE, login)
        if stored is not None:
            return stored
        if ini_password:
            # One-time migration: move plaintext password from INI into the keychain.
            keyring.set_password(_KEYRING_SERVICE, login, ini_password)
            log.info("Migrated HTTP password from config file into the system keychain.")
            return ini_password
    except Exception:
        log.warning("keyring read failed — password not loaded")
    return ""


def save_config(config: AppConfig, path: Path | None = None) -> None:
    with _config_lock:
        _save_config_locked(config, path)


def _save_config_locked(config: AppConfig, path: Path | None) -> None:
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if config.http_login and config.http_password:
        try:
            keyring.set_password(_KEYRING_SERVICE, config.http_login, config.http_password)
        except Exception:
            log.error(
                "keyring write failed — password NOT saved to disk. "
                "Ensure a keyring backend is available "
                "(on Linux, install 'secretstorage' or 'keyrings.alt')."
            )

    parser = configparser.ConfigParser()
    parser["http"] = {
        "base_url": config.http_base_url,
        "login": config.http_login,
        "password": "",  # never written to disk — stored in system keychain only
        "use_credentials": str(config.http_use_credentials).lower(),
        "allow_insecure": str(config.http_allow_insecure).lower(),
        "path_segments": ",".join(config.http_path_segments),
    }
    parser["product_id"] = {
        "sections": serialize_id_sections(config.id_section_defs),
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

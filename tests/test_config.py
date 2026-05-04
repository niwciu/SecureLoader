"""Tests for config load/save round-trip."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secure_loader.config import AppConfig, load_config, save_config


@pytest.fixture
def tmp_cfg(tmp_path: Path) -> Path:
    return tmp_path / "config.ini"


class TestRoundTrip:
    def test_defaults_when_file_missing(self, tmp_cfg: Path) -> None:
        cfg = load_config(tmp_cfg)
        assert cfg.http_base_url == ""
        assert cfg.http_login == ""
        assert cfg.http_password == ""
        assert cfg.language == "auto"
        assert cfg.update_instruction_url == ""
        assert cfg.last_firmware_paths == []

    def test_save_and_reload(self, tmp_cfg: Path) -> None:
        original = AppConfig(
            http_base_url="https://example.com",
            http_login="user",
            http_password="secret",
            language="de",
            update_instruction_url="https://example.com/instructions",
            last_firmware_paths=["/tmp/fw1.bin", "/tmp/fw2.bin"],
        )
        save_config(original, tmp_cfg)
        loaded = load_config(tmp_cfg)
        assert loaded.http_base_url == "https://example.com"
        assert loaded.http_login == "user"
        assert loaded.http_password == "secret"
        assert loaded.language == "de"
        assert loaded.update_instruction_url == "https://example.com/instructions"
        assert loaded.last_firmware_paths == ["/tmp/fw1.bin", "/tmp/fw2.bin"]

    def test_recent_paths_capped_at_10(self, tmp_cfg: Path) -> None:
        cfg = AppConfig(last_firmware_paths=[f"/tmp/fw{i}.bin" for i in range(15)])
        save_config(cfg, tmp_cfg)
        loaded = load_config(tmp_cfg)
        assert len(loaded.last_firmware_paths) == 10

    def test_partial_config_fills_defaults(self, tmp_cfg: Path) -> None:
        tmp_cfg.write_text("[http]\nbase_url = https://partial.example.com\n", encoding="utf-8")
        cfg = load_config(tmp_cfg)
        assert cfg.http_base_url == "https://partial.example.com"
        assert cfg.http_login == ""
        assert cfg.language == "auto"


class TestCredentials:
    def test_credentials_none_when_both_empty(self) -> None:
        cfg = AppConfig()
        assert cfg.credentials() is None

    def test_credentials_set_when_login_present(self) -> None:
        cfg = AppConfig(http_login="admin", http_password="pw")
        creds = cfg.credentials()
        assert creds is not None
        assert creds.login == "admin"
        assert creds.password == "pw"

    def test_credentials_set_when_only_login(self) -> None:
        cfg = AppConfig(http_login="admin")
        creds = cfg.credentials()
        assert creds is not None


class TestConcurrentAccess:
    def test_concurrent_save_load_is_consistent(self, tmp_cfg: Path) -> None:
        import threading

        errors: list[Exception] = []

        def writer(language: str) -> None:
            try:
                for _ in range(20):
                    save_config(AppConfig(language=language), tmp_cfg)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    cfg = load_config(tmp_cfg)
                    assert cfg.language in ("en", "de", "auto")
            except Exception as exc:
                errors.append(exc)

        save_config(AppConfig(language="auto"), tmp_cfg)
        threads = [
            threading.Thread(target=writer, args=("en",)),
            threading.Thread(target=writer, args=("de",)),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        assert errors == []


class TestKeyringStorage:
    def test_password_stored_in_keyring_not_ini(
        self, tmp_cfg: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None
        monkeypatch.setattr("secure_loader.config._KEYRING_AVAILABLE", True)
        monkeypatch.setattr("secure_loader.config._keyring", mock_kr)

        cfg = AppConfig(http_login="user", http_password="secret")
        save_config(cfg, tmp_cfg)

        mock_kr.set_password.assert_called_once_with("secureloader", "user", "secret")
        text = tmp_cfg.read_text()
        assert "secret" not in text

    def test_password_loaded_from_keyring(
        self, tmp_cfg: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = "from_keyring"
        monkeypatch.setattr("secure_loader.config._KEYRING_AVAILABLE", True)
        monkeypatch.setattr("secure_loader.config._keyring", mock_kr)

        cfg = AppConfig(http_login="user", http_password="")
        save_config(cfg, tmp_cfg)
        loaded = load_config(tmp_cfg)

        assert loaded.http_password == "from_keyring"


class TestFilePermissions:
    @pytest.mark.skipif(os.name == "nt", reason="chmod not meaningful on Windows")
    def test_saved_file_has_0600_permissions(self, tmp_cfg: Path) -> None:
        save_config(AppConfig(), tmp_cfg)
        mode = stat.S_IMODE(tmp_cfg.stat().st_mode)
        assert mode == 0o600

    def test_atomic_write_replaces_existing_file(self, tmp_cfg: Path) -> None:
        save_config(AppConfig(language="en"), tmp_cfg)
        save_config(AppConfig(language="fr"), tmp_cfg)
        loaded = load_config(tmp_cfg)
        assert loaded.language == "fr"
        # No leftover .tmp file.
        assert not tmp_cfg.with_suffix(tmp_cfg.suffix + ".tmp").exists()

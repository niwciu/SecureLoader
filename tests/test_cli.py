"""Tests for the CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secure_loader.cli.main import cli
from secure_loader.config import AppConfig, save_config


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "config.ini"
    save_config(AppConfig(), cfg_path)
    return cfg_path


def _invoke(runner: CliRunner, args: list[str], config_path: Path) -> object:
    """Run CLI with an isolated config path via env var override."""
    return runner.invoke(cli, args, catch_exceptions=False)


class TestConfigSet:
    def test_set_known_key(self, runner: CliRunner, tmp_config: Path, tmp_path: Path) -> None:
        with (
            patch("secure_loader.cli.main.config_path", return_value=tmp_config),
            patch("secure_loader.cli.main.load_config") as mock_load,
            patch("secure_loader.cli.main.save_config"),
        ):
            mock_load.return_value = AppConfig()
            result = runner.invoke(cli, ["config", "set", "http.base_url", "https://x.com"])
        assert result.exit_code == 0
        assert "saved" in result.output

    def test_set_unknown_key_errors(self, runner: CliRunner) -> None:
        with patch("secure_loader.cli.main.load_config", return_value=AppConfig()):
            result = runner.invoke(cli, ["config", "set", "bad.key", "value"])
        assert result.exit_code != 0
        assert "unknown key" in result.output.lower() or "unknown key" in (result.stderr or "")

    def test_invalid_language_rejected(self, runner: CliRunner) -> None:
        with patch("secure_loader.cli.main.load_config", return_value=AppConfig()):
            result = runner.invoke(cli, ["config", "set", "ui.language", "klingon"])
        assert result.exit_code != 0
        assert "invalid language" in result.output.lower() or "invalid language" in (
            result.stderr or ""
        )

    def test_valid_language_accepted(self, runner: CliRunner) -> None:
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config"),
        ):
            result = runner.invoke(cli, ["config", "set", "ui.language", "de"])
        assert result.exit_code == 0

    def test_auto_language_accepted(self, runner: CliRunner) -> None:
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config"),
        ):
            result = runner.invoke(cli, ["config", "set", "ui.language", "auto"])
        assert result.exit_code == 0

    def test_non_url_base_url_rejected(self, runner: CliRunner) -> None:
        with patch("secure_loader.cli.main.load_config", return_value=AppConfig()):
            result = runner.invoke(cli, ["config", "set", "http.base_url", "not-a-url"])
        assert result.exit_code != 0
        assert "http" in result.output.lower() or "http" in (result.stderr or "")

    def test_https_base_url_accepted(self, runner: CliRunner) -> None:
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config"),
        ):
            result = runner.invoke(
                cli, ["config", "set", "http.base_url", "https://example.com"]
            )
        assert result.exit_code == 0

    def test_empty_base_url_clears_value(self, runner: CliRunner) -> None:
        """An empty string should be accepted (it clears the configured URL)."""
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config"),
        ):
            result = runner.invoke(cli, ["config", "set", "http.base_url", ""])
        assert result.exit_code == 0


class TestConfigShow:
    def test_shows_all_keys(self, runner: CliRunner) -> None:
        cfg = AppConfig(http_base_url="https://example.com", language="fr")
        with patch("secure_loader.cli.main.load_config", return_value=cfg):
            result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "https://example.com" in result.output
        assert "fr" in result.output


class TestConfigPath:
    def test_prints_path(self, runner: CliRunner, tmp_config: Path) -> None:
        with (
            patch("secure_loader.cli.main.config_path", return_value=tmp_config),
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
        ):
            result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        assert str(tmp_config) in result.output


class TestFetchWarning:
    def test_http_url_rejected_without_allow_insecure(self, runner: CliRunner) -> None:
        cfg = AppConfig(http_base_url="http://insecure.example.com")
        with patch("secure_loader.cli.main.load_config", return_value=cfg):
            result = runner.invoke(
                cli,
                ["fetch", "--license", "CC", "--unique", "3344", "--output", "/dev/null"],
                catch_exceptions=True,
            )
        assert result.exit_code != 0
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "plain http" in combined.lower() or "not permitted" in combined.lower()

    def test_http_url_allowed_with_allow_insecure_flag(self, runner: CliRunner) -> None:
        cfg = AppConfig(http_base_url="http://insecure.example.com")
        with (
            patch("secure_loader.cli.main.load_config", return_value=cfg),
            patch("secure_loader.cli.main.HttpFirmwareSource") as mock_src_cls,
            patch("secure_loader.cli.main.parse_header", return_value=MagicMock()),
        ):
            mock_src = MagicMock()
            mock_src.fetch_latest.return_value = b"\x00" * 48
            mock_src_cls.return_value = mock_src
            runner.invoke(
                cli,
                [
                    "fetch", "--license", "CC", "--unique", "3344",
                    "--output", "/dev/null", "--allow-insecure",
                ],
                catch_exceptions=True,
            )
        assert mock_src_cls.call_args[1].get("allow_insecure") is True

    def test_https_url_no_cleartext_warning(self, runner: CliRunner) -> None:
        cfg = AppConfig(http_base_url="https://secure.example.com")
        with (
            patch("secure_loader.cli.main.load_config", return_value=cfg),
            patch("secure_loader.cli.main.HttpFirmwareSource") as mock_src_cls,
            patch("secure_loader.cli.main.parse_header", return_value=MagicMock()),
        ):
            mock_src = MagicMock()
            mock_src.fetch_latest.return_value = b"\x00" * 48
            mock_src_cls.return_value = mock_src
            result = runner.invoke(
                cli,
                ["fetch", "--license", "CC", "--unique", "3344", "--output", "/dev/null"],
                catch_exceptions=True,
            )
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "cleartext" not in combined.lower()


class TestSetPassword:
    def test_set_password_prompts_interactively(self, runner: CliRunner) -> None:
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config") as mock_save,
        ):
            result = runner.invoke(
                cli,
                ["config", "set-password"],
                input="mypassword\nmypassword\n",
            )
        assert result.exit_code == 0
        assert "saved" in result.output
        saved_cfg: AppConfig = mock_save.call_args[0][0]
        assert saved_cfg.http_password == "mypassword"

    def test_set_via_config_set_shows_warning(self, runner: CliRunner) -> None:
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.save_config"),
        ):
            result = runner.invoke(cli, ["config", "set", "http.password", "secret"])
        assert result.exit_code == 0
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "shell history" in combined.lower() or "set-password" in combined.lower()


class TestFlashCmd:
    """Tests for the flash command confirmation flow."""

    def _make_protocol_mock(self) -> MagicMock:
        proto = MagicMock()
        proto.state = MagicMock()
        proto.connect = MagicMock()
        proto.stop = MagicMock()
        proto.disconnect = MagicMock()
        proto.start_download = MagicMock()
        proto.wait_for_download = MagicMock()
        return proto

    def test_flash_prompts_for_confirmation(
        self, runner: CliRunner, tmp_path: Path, sample_firmware: bytes
    ) -> None:
        fw_path = tmp_path / "fw.bin"
        fw_path.write_bytes(sample_firmware)
        proto = self._make_protocol_mock()
        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.Protocol", return_value=proto),
            patch("secure_loader.cli.main.load_firmware") as mock_lf,
            patch("secure_loader.cli.main.threading.Thread") as mock_thread,
            patch("secure_loader.cli.main.threading.Event"),
        ):
            from secure_loader.core.firmware import parse_header

            mock_lf.return_value = (parse_header(sample_firmware), sample_firmware)
            mock_thread.return_value = MagicMock()
            # Simulate user answering "n" to confirmation → aborts.
            result = runner.invoke(
                cli,
                ["flash", "--port", "/dev/ttyUSB0", "--file", str(fw_path)],
                input="n\n",
                catch_exceptions=True,
            )
        assert result.exit_code != 0 or "aborted" in result.output.lower()

    def test_flash_yes_flag_skips_confirmation(
        self, runner: CliRunner, tmp_path: Path, sample_firmware: bytes
    ) -> None:
        fw_path = tmp_path / "fw.bin"
        fw_path.write_bytes(sample_firmware)

        connected_event = MagicMock()
        connected_event.wait.return_value = True

        proto = MagicMock()
        proto.connect = MagicMock()
        proto.stop = MagicMock()
        proto.disconnect = MagicMock()
        proto.start_download = MagicMock()
        proto.wait_for_download = MagicMock()
        device_info_holder: dict = {}

        def make_callbacks(**kwargs):  # type: ignore[no-untyped-def]
            from secure_loader.core.firmware import parse_header
            from secure_loader.core.protocol import DeviceInfo, ProtocolCallbacks

            cb = ProtocolCallbacks(**kwargs)
            hdr = parse_header(sample_firmware)
            dev = DeviceInfo(
                bootloader_version=hdr.protocol_version,
                product_id=hdr.product_id,
                flash_page_size=hdr.flash_page_size,
            )
            if cb.on_device_info:
                cb.on_device_info(dev)
                device_info_holder["event"] = True
            return cb

        with (
            patch("secure_loader.cli.main.load_config", return_value=AppConfig()),
            patch("secure_loader.cli.main.load_firmware") as mock_lf,
            patch("secure_loader.cli.main.ProtocolCallbacks", side_effect=make_callbacks),
            patch("secure_loader.cli.main.Protocol", return_value=proto),
            patch("secure_loader.cli.main.threading") as mock_threading,
        ):
            from secure_loader.core.firmware import parse_header

            mock_lf.return_value = (parse_header(sample_firmware), sample_firmware)
            mock_threading.Thread.return_value = MagicMock()
            mock_threading.Event.return_value = connected_event
            result = runner.invoke(
                cli,
                ["flash", "--port", "/dev/ttyUSB0", "--file", str(fw_path), "--yes"],
                catch_exceptions=True,
            )
        # Should not show confirmation prompt; exit cleanly (no abort).
        assert "Proceed with firmware update?" not in result.output

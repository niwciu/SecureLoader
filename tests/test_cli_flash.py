"""Integration test: flash CLI command from argument parsing to audit log."""

from __future__ import annotations

import struct
import threading
import zlib
from unittest.mock import patch

from click.testing import CliRunner

from secure_loader.cli.main import cli
from secure_loader.core.protocol import DeviceInfo, ProtocolCallbacks, ProtocolError


def _make_firmware() -> bytes:
    """Build a minimal valid firmware blob whose header matches _FakeDevice."""
    payload = b"\xAA" * 1024
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    # struct layout: protocolVersion, productId_MSB, productId_LSB,
    #                appVersion, prevAppVersion, pageCount, flashPageSize,
    #                IV (16 bytes), crc32
    header = struct.pack(
        "<IIIIIII16sI",
        0x00010002,  # protocolVersion  — matches _FakeDevice.bootloader_version
        0xAABBCCDD,  # productId MSB
        0x11223344,  # productId LSB    — together: 0xAABBCCDD11223344
        0x01020304,  # appVersion
        0x01020300,  # prevAppVersion
        1,           # pageCount
        1024,        # flashPageSize    — matches _FakeDevice.flash_page_size
        bytes(16),   # IV
        crc,
    )
    return header + payload


class _FakeProtocol:
    """Minimal Protocol double: fires device-info callback immediately in run()."""

    def __init__(self, *, callbacks: ProtocolCallbacks | None = None, **_kw: object) -> None:
        self._callbacks = callbacks
        self._stopped = threading.Event()

    def connect(self) -> None:
        pass

    def run(self) -> None:
        if self._callbacks and self._callbacks.on_device_info:
            self._callbacks.on_device_info(
                DeviceInfo(
                    bootloader_version=0x00010002,
                    product_id=0xAABBCCDD11223344,
                    flash_page_size=1024,
                )
            )
        self._stopped.wait()

    def stop(self) -> None:
        self._stopped.set()

    def disconnect(self) -> None:
        pass

    def start_download(self, firmware: bytes) -> None:
        pass

    def wait_for_download(self, timeout: float | None = None) -> None:
        pass


class TestFlashCommandIntegration:
    def test_flash_success_logs_audit_entry(self, tmp_path: object) -> None:
        fw_file = tmp_path / "fw.bin"  # type: ignore[operator]
        fw_file.write_bytes(_make_firmware())

        with (
            patch("secure_loader.cli.main.Protocol", _FakeProtocol),
            patch("secure_loader.cli.main.log_flash") as mock_log_flash,
        ):
            result = CliRunner().invoke(
                cli,
                ["flash", "--port", "/dev/ttyUSB0", "--file", str(fw_file), "--yes"],
            )

        assert result.exit_code == 0, result.output
        mock_log_flash.assert_called_once_with("/dev/ttyUSB0", "0x01020304", "success")

    def test_flash_protocol_error_logs_and_exits_nonzero(self, tmp_path: object) -> None:
        fw_file = tmp_path / "fw.bin"  # type: ignore[operator]
        fw_file.write_bytes(_make_firmware())

        class _FailOnDownload(_FakeProtocol):
            def start_download(self, firmware: bytes) -> None:
                raise ProtocolError("device not responding")

        with (
            patch("secure_loader.cli.main.Protocol", _FailOnDownload),
            patch("secure_loader.cli.main.log_flash") as mock_log_flash,
        ):
            result = CliRunner().invoke(
                cli,
                ["flash", "--port", "/dev/ttyUSB0", "--file", str(fw_file), "--yes"],
            )

        assert result.exit_code != 0
        mock_log_flash.assert_called_once()
        _port, _version, outcome = mock_log_flash.call_args[0]
        assert outcome.startswith("error:")

    def test_flash_device_mismatch_exits_nonzero_without_force(self, tmp_path: object) -> None:
        fw_file = tmp_path / "fw.bin"  # type: ignore[operator]
        fw_file.write_bytes(_make_firmware())

        class _WrongDevice(_FakeProtocol):
            def run(self) -> None:
                if self._callbacks and self._callbacks.on_device_info:
                    self._callbacks.on_device_info(
                        DeviceInfo(
                            bootloader_version=0xDEADBEEF,  # mismatches firmware protocol_version
                            product_id=0xAABBCCDD11223344,
                            flash_page_size=1024,
                        )
                    )
                self._stopped.wait()

        with patch("secure_loader.cli.main.Protocol", _WrongDevice):
            result = CliRunner().invoke(
                cli,
                ["flash", "--port", "/dev/ttyUSB0", "--file", str(fw_file), "--yes"],
            )

        assert result.exit_code != 0
        combined = (result.output + str(result.exception)).lower()
        assert "mismatch" in combined or "does not match" in combined

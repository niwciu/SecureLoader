"""Tests for LocalFirmwareSource."""

from __future__ import annotations

import pytest

from secure_loader.core.sources.base import FirmwareIdentifier, FirmwareSourceError
from secure_loader.core.sources.local import LocalFirmwareSource


@pytest.fixture
def identifier() -> FirmwareIdentifier:
    return FirmwareIdentifier(license_id="CC", unique_id="3344")


class TestLocalFirmwareSource:
    def test_fetch_latest_returns_file_contents(
        self, tmp_path, identifier: FirmwareIdentifier
    ) -> None:
        fw = tmp_path / "firmware.bin"
        fw.write_bytes(b"\x01\x02\x03\x04")
        src = LocalFirmwareSource(fw)
        assert src.fetch_latest(identifier) == b"\x01\x02\x03\x04"

    def test_fetch_latest_raises_on_missing_file(
        self, tmp_path, identifier: FirmwareIdentifier
    ) -> None:
        src = LocalFirmwareSource(tmp_path / "nonexistent.bin")
        with pytest.raises(FirmwareSourceError, match="cannot read"):
            src.fetch_latest(identifier)

    def test_progress_callback_called(self, tmp_path, identifier: FirmwareIdentifier) -> None:
        fw = tmp_path / "firmware.bin"
        fw.write_bytes(b"x" * 256)
        src = LocalFirmwareSource(fw)
        calls: list[tuple[int, int]] = []
        src.fetch_latest(identifier, progress=lambda r, t: calls.append((r, t)))
        assert calls == [(256, 256)]

    def test_fetch_previous_returns_same_file(
        self, tmp_path, identifier: FirmwareIdentifier
    ) -> None:
        fw = tmp_path / "firmware.bin"
        fw.write_bytes(b"\xde\xad\xbe\xef")
        src = LocalFirmwareSource(fw)
        assert src.fetch_previous(identifier) == src.fetch_latest(identifier)

    def test_accepts_string_path(self, tmp_path, identifier: FirmwareIdentifier) -> None:
        fw = tmp_path / "firmware.bin"
        fw.write_bytes(b"\xff")
        src = LocalFirmwareSource(str(fw))
        assert src.fetch_latest(identifier) == b"\xff"

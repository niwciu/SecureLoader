"""Firmware source that reads from the local filesystem."""

from __future__ import annotations

from pathlib import Path

from .base import FirmwareIdentifier, FirmwareSource, FirmwareSourceError, ProgressCallback


class LocalFirmwareSource(FirmwareSource):
    """Return the contents of a fixed .bin file on disk.

    Useful for CLI flows that already have the firmware locally and for
    deterministic testing.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        del identifier
        try:
            data = self._path.read_bytes()
        except OSError as e:
            raise FirmwareSourceError(f"cannot read {self._path}: {e}") from e
        if progress is not None:
            progress(len(data), len(data))
        return data

    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        # Local source doesn't have a concept of "previous" — the same file
        # is returned for symmetry with the interface.
        return self.fetch_latest(identifier, progress)

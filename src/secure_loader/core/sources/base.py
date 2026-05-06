"""Base types for firmware source providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

ProgressCallback = Callable[[int, int], None]
"""Progress callback receiving ``(bytes_received, bytes_total)``."""


class FirmwareSourceError(RuntimeError):
    """Raised when a firmware source cannot provide the requested blob."""


@dataclass(frozen=True, slots=True)
class FirmwareIdentifier:
    """Keys identifying which firmware image to fetch.

    Consumers derive these from the device's ``productId`` response or from
    a parsed firmware header. Not every field is meaningful for every source;
    providers document which attributes they require.

    The four ``*_id`` fields mirror the product ID byte convention:
    ``custom_id`` (bytes 0–3), ``hw_id`` (byte 4), ``license_id`` (byte 5),
    ``unique_id`` (bytes 6–7).  Which fields are actually used to build a
    download URL is determined by :attr:`HttpFirmwareSource.path_segments`.
    """

    license_id: str
    unique_id: str
    custom_id: str = ""
    hw_id: str = ""
    app_version: str | None = None


class FirmwareSource(ABC):
    """Abstract firmware provider.

    Implementations must be safe to call repeatedly. Long-running operations
    should honour the optional ``progress`` callback so frontends can update
    progress bars.
    """

    @abstractmethod
    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        """Return the current/latest firmware blob for ``identifier``."""

    @abstractmethod
    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        """Return the previous firmware version indicated by ``identifier.app_version``.

        Typically ``identifier.app_version`` will hold the ``prevAppVersion``
        field of the currently installed image so the provider can locate the
        corresponding older release.
        """

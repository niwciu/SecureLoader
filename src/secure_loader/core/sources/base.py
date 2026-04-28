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
    """

    license_id: str
    unique_id: str
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

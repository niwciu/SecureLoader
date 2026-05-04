"""Firmware source abstraction and concrete providers.

The application can obtain a firmware blob from several places:

* The local filesystem (:class:`LocalFirmwareSource`).
* An HTTP server keyed by ``licenseID`` / ``uniqueID``
  (:class:`HttpFirmwareSource`).

:class:`GithubReleasesFirmwareSource` exists in ``github.py`` as a planned
extension but is intentionally excluded from this public API until the
release-asset layout is finalised and the provider is wired to a frontend.

All providers implement the :class:`FirmwareSource` protocol. The GUI and CLI
only depend on that protocol, which keeps frontends decoupled from the
transport.
"""

from .base import (
    FirmwareIdentifier,
    FirmwareSource,
    FirmwareSourceError,
    ProgressCallback,
)
from .http import HttpFirmwareSource
from .local import LocalFirmwareSource

__all__ = [
    "FirmwareIdentifier",
    "FirmwareSource",
    "FirmwareSourceError",
    "HttpFirmwareSource",
    "LocalFirmwareSource",
    "ProgressCallback",
]

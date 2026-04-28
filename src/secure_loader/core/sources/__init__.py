"""Firmware source abstraction and concrete providers.

The application can obtain a firmware blob from several places:

* The local filesystem (:class:`LocalFirmwareSource`).
* An HTTP server keyed by ``licenseID`` / ``uniqueID``
  (:class:`HttpFirmwareSource`).
* A GitHub Releases feed of a private repository
  (:class:`GithubReleasesFirmwareSource`) — scaffolded for the planned
  migration once the release layout is finalised.

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
from .github import GithubReleasesFirmwareSource
from .http import HttpFirmwareSource
from .local import LocalFirmwareSource

__all__ = [
    "FirmwareIdentifier",
    "FirmwareSource",
    "FirmwareSourceError",
    "GithubReleasesFirmwareSource",
    "HttpFirmwareSource",
    "LocalFirmwareSource",
    "ProgressCallback",
]

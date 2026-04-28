"""HTTP firmware source.

Two-step download flow:

1. GET ``{base_url}/{license_id}/{unique_id}/info.txt`` — plaintext version tag.
2. GET ``{base_url}/{license_id}/{unique_id}/{version}.bin`` — the firmware.

Optional HTTP basic authentication is supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

import requests

from .base import FirmwareIdentifier, FirmwareSource, FirmwareSourceError, ProgressCallback

DEFAULT_BASE_URL: str = ""
DEFAULT_TIMEOUT_S: float = 30.0
_CHUNK_SIZE: int = 64 * 1024


@dataclass(frozen=True, slots=True)
class HttpCredentials:
    login: str
    password: str


class HttpFirmwareSource(FirmwareSource):
    """Firmware provider for the legacy HTTP server layout."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        credentials: HttpCredentials | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._credentials = credentials
        self._timeout_s = timeout_s
        self._session = session or requests.Session()

    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        version = self._get_info(identifier)
        return self._get_binary(identifier, version, progress)

    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        if not identifier.app_version:
            raise FirmwareSourceError(
                "fetch_previous requires FirmwareIdentifier.app_version to be set"
            )
        return self._get_binary(identifier, identifier.app_version, progress)

    # ---------------------------------------------------------------- helpers

    def _auth(self) -> tuple[str, str] | None:
        if self._credentials is None:
            return None
        return (self._credentials.login, self._credentials.password)

    def _url(self, identifier: FirmwareIdentifier, filename: str) -> str:
        return (
            f"{self._base_url}/"
            f"{quote(identifier.license_id, safe='')}/"
            f"{quote(identifier.unique_id, safe='')}/"
            f"{quote(filename, safe='.')}"
        )

    def _get_info(self, identifier: FirmwareIdentifier) -> str:
        url = self._url(identifier, "info.txt")
        try:
            response = self._session.get(url, auth=self._auth(), timeout=self._timeout_s)
            response.raise_for_status()
        except requests.RequestException as e:
            raise FirmwareSourceError(f"cannot fetch {url}: {e}") from e
        return response.text.strip()

    def _get_binary(
        self,
        identifier: FirmwareIdentifier,
        version: str,
        progress: ProgressCallback | None,
    ) -> bytes:
        url = self._url(identifier, f"{version}.bin")
        try:
            response = self._session.get(
                url,
                auth=self._auth(),
                stream=True,
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            buf = bytearray()
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                if chunk:
                    buf.extend(chunk)
                    if progress is not None and total:
                        progress(len(buf), total)
            if progress is not None and total == 0:
                progress(len(buf), len(buf))
            return bytes(buf)
        except requests.RequestException as e:
            raise FirmwareSourceError(f"cannot download {url}: {e}") from e

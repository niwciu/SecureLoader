"""HTTP firmware source.

Two-step download flow:

1. GET ``{base_url}/{path}/info.txt`` — plaintext version tag.
2. GET ``{base_url}/{path}/{version}.bin`` — the firmware binary.

``{path}`` is built from the product-ID fields listed in ``path_segments``
(default: ``["license_id", "unique_id"]``).  Each element names an attribute
of :class:`~secure_loader.core.sources.base.FirmwareIdentifier`; the values
are joined with ``/`` and percent-encoded.

Optional HTTP basic authentication is supported.

Plain HTTP URLs and disabled TLS certificate verification are **rejected by
default**.  Pass ``allow_insecure=True`` to the constructor (or the
``--allow-insecure`` CLI flag) to explicitly acknowledge and accept the
associated security risks.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote

import requests

from .base import FirmwareIdentifier, FirmwareSource, FirmwareSourceError, ProgressCallback

_VERSION_RE = re.compile(r"[A-Za-z0-9._-]+$")

log = logging.getLogger(__name__)

DEFAULT_BASE_URL: str = ""
DEFAULT_TIMEOUT_S: float = 30.0
DEFAULT_PATH_SEGMENTS: list[str] = ["license_id", "unique_id"]
_CHUNK_SIZE: int = 64 * 1024
_MAX_FIRMWARE_BYTES: int = 100 * 1024 * 1024  # 100 MB hard cap


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
        tls_verify: bool | str = True,
        allow_insecure: bool = False,
        path_segments: list[str] | None = None,
    ) -> None:
        if tls_verify is False and not allow_insecure:
            raise FirmwareSourceError(
                "TLS certificate verification cannot be disabled without explicitly passing "
                "allow_insecure=True. Only do this in controlled test environments."
            )
        self._base_url = base_url.rstrip("/")
        self._credentials = credentials
        self._timeout_s = timeout_s
        self._allow_insecure = allow_insecure
        self._path_segments = (
            list(path_segments) if path_segments is not None else list(DEFAULT_PATH_SEGMENTS)
        )
        self._session = session or requests.Session()
        self._session.verify = tls_verify
        if tls_verify is False:
            log.error("TLS certificate verification is DISABLED — this is a security risk.")

    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        log.debug("fetch_latest: base_url=%s path_segments=%s", self._base_url, self._path_segments)
        self._check_base_url()
        version = self._get_info(identifier)
        log.debug("fetch_latest: resolved version=%s", version)
        return self._get_binary(identifier, version, progress)

    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        log.debug(
            "fetch_previous: base_url=%s app_version=%s path_segments=%s",
            self._base_url,
            identifier.app_version,
            self._path_segments,
        )
        self._check_base_url()
        if not identifier.app_version:
            raise FirmwareSourceError(
                "fetch_previous requires FirmwareIdentifier.app_version to be set"
            )
        return self._get_binary(identifier, identifier.app_version, progress)

    # ---------------------------------------------------------------- helpers

    def _check_base_url(self) -> None:
        if not self._base_url:
            raise FirmwareSourceError(
                "http.base_url is not configured — set it with "
                "`sld config set http.base_url <url>` or pass --base-url"
            )
        if self._base_url.startswith("http://"):
            if not self._allow_insecure:
                raise FirmwareSourceError(
                    f"plain HTTP is not permitted ({self._base_url}). "
                    "Use HTTPS, or enable 'Allow plain HTTP' in Server settings."
                )
            log.warning(
                "Fetching firmware over plain HTTP (%s) — credentials and firmware "
                "are transmitted in cleartext.",
                self._base_url,
            )

    def _auth(self) -> tuple[str, str] | None:
        if self._credentials is None:
            return None
        return (self._credentials.login, self._credentials.password)

    def _url(self, identifier: FirmwareIdentifier, filename: str) -> str:
        parts = [
            quote(str(getattr(identifier, seg, "") or ""), safe="")
            for seg in self._path_segments
            if getattr(identifier, seg, "")
        ]
        parts.append(quote(filename, safe="."))
        url = self._base_url + "/" + "/".join(parts)
        log.debug("_url: %s", url)
        return url

    def _get_info(self, identifier: FirmwareIdentifier) -> str:
        url = self._url(identifier, "info.txt")
        log.debug("GET %s", url)
        try:
            response = self._session.get(url, auth=self._auth(), timeout=self._timeout_s)
            log.debug("response: HTTP %s", response.status_code)
            response.raise_for_status()
        except requests.RequestException as e:
            raise FirmwareSourceError(f"cannot fetch {url}: {e}") from e
        version = response.text.strip()
        log.debug("info.txt content: %r", version)
        if not _VERSION_RE.match(version):
            raise FirmwareSourceError(
                f"server returned an invalid version string {version!r}; "
                "expected only alphanumeric characters, dots, hyphens, and underscores"
            )
        return version

    def _get_binary(
        self,
        identifier: FirmwareIdentifier,
        version: str,
        progress: ProgressCallback | None,
    ) -> bytes:
        url = self._url(identifier, f"{version}.bin")
        log.debug("GET %s", url)
        try:
            response = self._session.get(
                url,
                auth=self._auth(),
                stream=True,
                timeout=self._timeout_s,
            )
            log.debug("response: HTTP %s  Content-Length: %s", response.status_code, response.headers.get("Content-Length", "unknown"))
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            buf = bytearray()
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                if chunk:
                    buf.extend(chunk)
                    if len(buf) > _MAX_FIRMWARE_BYTES:
                        raise FirmwareSourceError(
                            f"firmware download exceeded {_MAX_FIRMWARE_BYTES // (1024 * 1024)} MB limit"
                        )
                    if progress is not None and total:
                        progress(len(buf), total)
            if progress is not None and total == 0:
                progress(len(buf), len(buf))
            log.debug("download complete: %d bytes", len(buf))
            return bytes(buf)
        except requests.RequestException as e:
            raise FirmwareSourceError(f"cannot download {url}: {e}") from e

"""GitHub Releases firmware source (scaffolding).

This provider is intended for the planned migration away from the legacy
HTTP server: the firmware GitHub Actions workflow publishes releases on a
*private* GitHub repository, and this class downloads the appropriate asset.

The implementation is **intentionally kept as a well-documented skeleton**
until the release-asset layout is finalised. Once it is, filling in the
three TODO sections below will complete the provider.

Design notes
------------

* Authentication: the GitHub REST API supports three token types that grant
  access to release assets on private repos:

  - Classic PAT with ``repo`` scope;
  - Fine-grained PAT with ``Contents: read`` on the target repo;
  - GitHub App installation token.

  All three are used the same way — as a bearer token in the
  ``Authorization`` header. The class deliberately accepts an opaque
  ``token`` string so any of the above can be supplied.

* Asset download: for private repos, the asset URL must be the **API URL**
  (``/releases/assets/{id}``) with ``Accept: application/octet-stream``.
  The plain ``browser_download_url`` returns an HTML login page instead of
  the binary.

* Version selection: ``fetch_latest`` uses ``/releases/latest``.
  ``fetch_previous`` looks up a release whose tag matches
  ``identifier.app_version``, using the device's ``prevAppVersion``
  as the tag stem.

* Asset selection: not yet decided — see module-level TODO. Until the GHA
  workflow finalises its naming convention, this class resolves the asset
  through :meth:`_select_asset`, which is the single hook to update once
  the layout is known.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import requests

from .base import FirmwareIdentifier, FirmwareSource, FirmwareSourceError, ProgressCallback

GITHUB_API_BASE: str = "https://api.github.com"
DEFAULT_TIMEOUT_S: float = 30.0
_CHUNK_SIZE: int = 64 * 1024


@dataclass(frozen=True, slots=True)
class GithubConfig:
    owner: str
    repo: str
    token: str
    api_base: str = GITHUB_API_BASE


class GithubReleasesFirmwareSource(FirmwareSource):
    """Fetch firmware from a private GitHub repository's releases.

    The implementation is in skeleton form: the HTTP plumbing is complete,
    but :meth:`_select_asset` (the policy that picks which asset within a
    release corresponds to a given :class:`FirmwareIdentifier`) must be
    finalised before the provider is wired up in production.
    """

    def __init__(
        self,
        config: GithubConfig,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        session: requests.Session | None = None,
    ) -> None:
        self._config = config
        self._timeout_s = timeout_s
        self._session = session or requests.Session()

    def fetch_latest(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        release = self._get_json(f"/repos/{self._config.owner}/{self._config.repo}/releases/latest")
        asset = self._select_asset(release.get("assets", []), identifier)
        return self._download_asset(asset, progress)

    def fetch_previous(
        self,
        identifier: FirmwareIdentifier,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        if not identifier.app_version:
            raise FirmwareSourceError(
                "fetch_previous requires FirmwareIdentifier.app_version to be set"
            )
        tag = identifier.app_version
        release = self._get_json(
            f"/repos/{self._config.owner}/{self._config.repo}/releases/tags/{tag}"
        )
        asset = self._select_asset(release.get("assets", []), identifier)
        return self._download_asset(asset, progress)

    # ---------------------------------------------------------- customisation

    def _select_asset(
        self,
        assets: Iterable[dict[str, Any]],
        identifier: FirmwareIdentifier,
    ) -> dict[str, Any]:
        """Pick the asset within a release that corresponds to ``identifier``.

        TODO(release-layout): replace this placeholder with the actual naming
        convention produced by the GHA workflow. The current placeholder
        matches any asset whose ``name`` contains both the license ID and
        the unique ID, which is a reasonable default but not yet confirmed.

        Raises :class:`FirmwareSourceError` when no suitable asset is found.
        """
        lic = identifier.license_id.lower()
        uid = identifier.unique_id.lower()
        candidates = [a for a in assets if lic in a["name"].lower() and uid in a["name"].lower()]
        if not candidates:
            names = sorted(a["name"] for a in assets)
            raise FirmwareSourceError(
                f"no release asset matches license={identifier.license_id!r}, "
                f"unique={identifier.unique_id!r}; available: {names}"
            )
        # Prefer exact ``{license}_{unique}.bin`` if present; otherwise take
        # the first match. This heuristic is explicitly temporary.
        preferred = f"{lic}_{uid}.bin"
        for a in candidates:
            if a["name"].lower() == preferred:
                return a
        return candidates[0]

    # --------------------------------------------------------------- internal

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._config.token}",
            "Accept": accept,
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self._config.api_base}{path}"
        try:
            response = self._session.get(url, headers=self._headers(), timeout=self._timeout_s)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise FirmwareSourceError(f"unexpected response shape from {url}")
            return data
        except requests.RequestException as e:
            raise FirmwareSourceError(f"GitHub API request failed: {e}") from e

    def _download_asset(
        self,
        asset: dict[str, Any],
        progress: ProgressCallback | None,
    ) -> bytes:
        asset_url = asset.get("url")
        if not asset_url:
            raise FirmwareSourceError(f"asset missing API url: {asset}")
        try:
            response = self._session.get(
                asset_url,
                headers=self._headers(accept="application/octet-stream"),
                stream=True,
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", asset.get("size", 0)))
            buf = bytearray()
            for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
                if chunk:
                    buf.extend(chunk)
                    if progress is not None and total:
                        progress(len(buf), total)
            return bytes(buf)
        except requests.RequestException as e:
            raise FirmwareSourceError(f"cannot download asset {asset.get('name')}: {e}") from e

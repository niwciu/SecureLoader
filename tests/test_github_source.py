"""Tests for GithubReleasesFirmwareSource."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from secure_loader.core.sources.base import FirmwareIdentifier, FirmwareSourceError
from secure_loader.core.sources.github import GithubConfig, GithubReleasesFirmwareSource


@pytest.fixture
def config() -> GithubConfig:
    return GithubConfig(owner="acme", repo="firmware", token="ghp_test")


@pytest.fixture
def source(config: GithubConfig) -> GithubReleasesFirmwareSource:
    return GithubReleasesFirmwareSource(config=config)


@pytest.fixture
def identifier() -> FirmwareIdentifier:
    return FirmwareIdentifier(license_id="CC", unique_id="3344")


def _json_response(data: object, status: int = 200) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.json.return_value = data
    r.headers = {"Content-Length": "0"}
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    return r


def _binary_response(content: bytes) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.headers = {"Content-Length": str(len(content))}
    r.iter_content.return_value = iter([content])
    r.raise_for_status.return_value = None
    return r


class TestSelectAsset:
    def test_exact_name_preferred(self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier) -> None:
        assets = [
            {"name": "cc_3344.bin", "url": "https://api.github.com/assets/1"},
            {"name": "cc_3344_extra.bin", "url": "https://api.github.com/assets/2"},
        ]
        selected = source._select_asset(assets, identifier)
        assert selected["url"] == "https://api.github.com/assets/1"

    def test_fallback_to_first_match(self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier) -> None:
        assets = [
            {"name": "cc_3344_v2.bin", "url": "https://api.github.com/assets/2"},
        ]
        selected = source._select_asset(assets, identifier)
        assert selected["url"] == "https://api.github.com/assets/2"

    def test_raises_when_no_match(self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier) -> None:
        assets = [{"name": "other.bin", "url": "https://api.github.com/assets/3"}]
        with pytest.raises(FirmwareSourceError, match="no release asset"):
            source._select_asset(assets, identifier)

    def test_raises_when_no_assets(self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier) -> None:
        with pytest.raises(FirmwareSourceError, match="no release asset"):
            source._select_asset([], identifier)


class TestFetchLatest:
    def test_fetches_latest_release(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        payload = b"\x01\x02\x03\x04"
        asset = {"name": "cc_3344.bin", "url": "https://api.github.com/assets/1", "size": len(payload)}
        release_resp = _json_response({"assets": [asset]})
        binary_resp = _binary_response(payload)

        source._session = MagicMock()
        source._session.get.side_effect = [release_resp, binary_resp]

        result = source.fetch_latest(identifier)
        assert result == payload

    def test_raises_on_api_error(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        source._session = MagicMock()
        source._session.get.side_effect = requests.ConnectionError("no network")
        with pytest.raises(FirmwareSourceError, match="GitHub API request failed"):
            source.fetch_latest(identifier)

    def test_raises_when_response_not_dict(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        r = MagicMock(spec=requests.Response)
        r.json.return_value = ["not", "a", "dict"]
        r.raise_for_status.return_value = None
        source._session = MagicMock()
        source._session.get.return_value = r
        with pytest.raises(FirmwareSourceError, match="unexpected response"):
            source.fetch_latest(identifier)


class TestFetchPrevious:
    def test_fetches_by_tag(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        ident = FirmwareIdentifier(license_id="CC", unique_id="3344", app_version="1.0.0")
        payload = b"\xDE\xAD"
        asset = {"name": "cc_3344.bin", "url": "https://api.github.com/assets/5", "size": 2}
        release_resp = _json_response({"assets": [asset]})
        binary_resp = _binary_response(payload)

        source._session = MagicMock()
        source._session.get.side_effect = [release_resp, binary_resp]

        result = source.fetch_previous(ident)
        assert result == payload
        url_called = source._session.get.call_args_list[0][0][0]
        assert "tags/1.0.0" in url_called

    def test_raises_when_app_version_missing(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        with pytest.raises(FirmwareSourceError, match="app_version"):
            source.fetch_previous(identifier)


class TestDownloadAsset:
    def test_raises_when_url_missing(self, source: GithubReleasesFirmwareSource) -> None:
        with pytest.raises(FirmwareSourceError, match="asset missing API url"):
            source._download_asset({}, progress=None)

    def test_progress_callback_called(
        self, source: GithubReleasesFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        payload = b"x" * 256
        asset = {"name": "cc_3344.bin", "url": "https://api.github.com/assets/7", "size": len(payload)}
        release_resp = _json_response({"assets": [asset]})
        binary_resp = _binary_response(payload)

        source._session = MagicMock()
        source._session.get.side_effect = [release_resp, binary_resp]

        calls: list[tuple[int, int]] = []
        source.fetch_latest(identifier, progress=lambda r, t: calls.append((r, t)))
        assert calls
        assert calls[-1][0] == len(payload)

"""Tests for HttpFirmwareSource."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest
import requests

from secure_loader.core.sources.base import FirmwareIdentifier, FirmwareSourceError
from secure_loader.core.sources.http import HttpCredentials, HttpFirmwareSource


def _make_response(text: str | None = None, content: bytes = b"", status: int = 200) -> MagicMock:
    r = MagicMock(spec=requests.Response)
    r.text = text or ""
    r.content = content
    r.headers = {"Content-Length": str(len(content))}
    r.iter_content = MagicMock(return_value=[content] if content else [])
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(response=r)
    else:
        r.raise_for_status.return_value = None
    return r


@pytest.fixture
def identifier() -> FirmwareIdentifier:
    return FirmwareIdentifier(license_id="CC", unique_id="3344")


@pytest.fixture
def source() -> HttpFirmwareSource:
    return HttpFirmwareSource(base_url="https://firmware.example.com")


class TestCheckBaseUrl:
    def test_raises_when_base_url_empty(self, identifier: FirmwareIdentifier) -> None:
        src = HttpFirmwareSource(base_url="")
        with pytest.raises(FirmwareSourceError, match=r"http\.base_url is not configured"):
            src.fetch_latest(identifier)

    def test_raises_when_http_without_allow_insecure(self, identifier: FirmwareIdentifier) -> None:
        src = HttpFirmwareSource(base_url="http://insecure.example.com")
        with pytest.raises(FirmwareSourceError, match="plain HTTP is not permitted"):
            src.fetch_latest(identifier)

    def test_http_allowed_and_warns_when_allow_insecure(
        self, identifier: FirmwareIdentifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = HttpFirmwareSource(base_url="http://insecure.example.com", allow_insecure=True)
        session_mock = MagicMock()
        session_mock.get.side_effect = requests.ConnectionError("no server")
        src._session = session_mock
        with caplog.at_level(logging.WARNING, logger="secure_loader.core.sources.http"), pytest.raises(FirmwareSourceError):
            src.fetch_latest(identifier)
        assert any("cleartext" in r.message.lower() for r in caplog.records)

    def test_no_warning_when_https(
        self, identifier: FirmwareIdentifier, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = HttpFirmwareSource(base_url="https://secure.example.com")
        session_mock = MagicMock()
        session_mock.get.side_effect = requests.ConnectionError("no server")
        src._session = session_mock
        with caplog.at_level(logging.WARNING, logger="secure_loader.core.sources.http"), pytest.raises(FirmwareSourceError):
            src.fetch_latest(identifier)
        assert not any("cleartext" in r.message.lower() for r in caplog.records)


class TestVersionStringValidation:
    def test_valid_version_string_passes(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        payload = b"\x01" * 64
        source._session = MagicMock()
        source._session.get.side_effect = [
            _make_response(text="1.2.3-beta"),
            _make_response(content=payload),
        ]
        result = source.fetch_latest(identifier)
        assert result == payload

    def test_traversal_version_string_rejected(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        source._session = MagicMock()
        source._session.get.return_value = _make_response(text="../../../etc/passwd")
        with pytest.raises(FirmwareSourceError, match="invalid version string"):
            source.fetch_latest(identifier)

    def test_empty_version_string_rejected(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        source._session = MagicMock()
        source._session.get.return_value = _make_response(text="")
        with pytest.raises(FirmwareSourceError, match="invalid version string"):
            source.fetch_latest(identifier)

    def test_version_with_spaces_rejected(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        source._session = MagicMock()
        source._session.get.return_value = _make_response(text="1.0 evil")
        with pytest.raises(FirmwareSourceError, match="invalid version string"):
            source.fetch_latest(identifier)


class TestFetchLatest:
    def test_fetches_info_then_binary(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        payload = b"\xDE\xAD\xBE\xEF" * 16
        info_resp = _make_response(text="1.2.3")
        bin_resp = _make_response(content=payload)
        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]

        result = source.fetch_latest(identifier)
        assert result == payload

    def test_raises_on_info_http_error(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        source._session = MagicMock()
        source._session.get.return_value = _make_response(status=404)
        with pytest.raises(FirmwareSourceError, match="cannot fetch"):
            source.fetch_latest(identifier)

    def test_raises_on_binary_http_error(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        info_resp = _make_response(text="1.0.0")
        bin_resp = _make_response(status=404)
        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]
        with pytest.raises(FirmwareSourceError, match="cannot download"):
            source.fetch_latest(identifier)

    def test_progress_callback_called(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        payload = b"x" * 1024
        info_resp = _make_response(text="2.0.0")
        bin_resp = _make_response(content=payload)
        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]

        calls: list[tuple[int, int]] = []
        source.fetch_latest(identifier, progress=lambda r, t: calls.append((r, t)))
        assert calls
        assert calls[-1][0] == len(payload)

    def test_url_encodes_special_characters(self, source: HttpFirmwareSource) -> None:
        ident = FirmwareIdentifier(license_id="A B", unique_id="C/D")
        source._session = MagicMock()
        source._session.get.side_effect = requests.ConnectionError()
        with pytest.raises(FirmwareSourceError):
            source.fetch_latest(ident)
        url = source._session.get.call_args[0][0]
        # Spaces and path-unsafe characters must be percent-encoded.
        assert " " not in url
        assert "%20" in url  # space in license_id
        assert "%2F" in url  # slash in unique_id


class TestFetchPrevious:
    def test_fetches_named_version(self, source: HttpFirmwareSource) -> None:
        payload = b"\x01\x02\x03"
        ident = FirmwareIdentifier(license_id="AA", unique_id="BBBB", app_version="0.9.1")
        bin_resp = _make_response(content=payload)
        source._session = MagicMock()
        source._session.get.return_value = bin_resp
        result = source.fetch_previous(ident)
        assert result == payload
        # Must not call info.txt — goes straight to .bin
        url = source._session.get.call_args[0][0]
        assert "0.9.1.bin" in url

    def test_raises_when_app_version_missing(self, source: HttpFirmwareSource) -> None:
        ident = FirmwareIdentifier(license_id="AA", unique_id="BBBB")
        with pytest.raises(FirmwareSourceError, match="app_version"):
            source.fetch_previous(ident)


class TestDownloadSizeCap:
    def test_oversized_response_raises(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        from secure_loader.core.sources.http import _MAX_FIRMWARE_BYTES

        big_chunk = b"X" * (_MAX_FIRMWARE_BYTES + 1)
        info_resp = _make_response(text="1.0.0")
        bin_resp = MagicMock()
        bin_resp.headers = {"Content-Length": str(len(big_chunk))}
        bin_resp.iter_content.return_value = iter([big_chunk])
        bin_resp.raise_for_status.return_value = None

        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]

        with pytest.raises(FirmwareSourceError, match="exceeded"):
            source.fetch_latest(identifier)

    def test_exactly_at_limit_passes(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        from secure_loader.core.sources.http import _MAX_FIRMWARE_BYTES

        ok_chunk = b"X" * _MAX_FIRMWARE_BYTES
        info_resp = _make_response(text="1.0.0")
        bin_resp = MagicMock()
        bin_resp.headers = {"Content-Length": str(len(ok_chunk))}
        bin_resp.iter_content.return_value = iter([ok_chunk])
        bin_resp.raise_for_status.return_value = None

        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]

        result = source.fetch_latest(identifier)
        assert len(result) == _MAX_FIRMWARE_BYTES


class TestTlsVerify:
    def test_tls_verify_false_raises_without_allow_insecure(self) -> None:
        with pytest.raises(FirmwareSourceError, match="TLS certificate verification cannot be disabled"):
            HttpFirmwareSource(base_url="https://firmware.example.com", tls_verify=False)

    def test_tls_verify_false_allowed_with_allow_insecure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR, logger="secure_loader.core.sources.http"):
            HttpFirmwareSource(
                base_url="https://firmware.example.com",
                tls_verify=False,
                allow_insecure=True,
            )
        assert any("DISABLED" in r.message for r in caplog.records)

    def test_tls_verify_true_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="secure_loader.core.sources.http"):
            HttpFirmwareSource(base_url="https://firmware.example.com", tls_verify=True)
        assert not any("TLS" in r.message for r in caplog.records)

    def test_tls_verify_applied_to_session(self) -> None:
        src = HttpFirmwareSource(
            base_url="https://firmware.example.com",
            tls_verify=False,
            allow_insecure=True,
        )
        assert src._session.verify is False


class TestAuth:
    def test_credentials_passed_to_session(self, identifier: FirmwareIdentifier) -> None:
        creds = HttpCredentials(login="user", password="pw")
        src = HttpFirmwareSource(
            base_url="https://firmware.example.com", credentials=creds
        )
        info_resp = _make_response(text="1.0.0")
        bin_resp = _make_response(content=b"data")
        src._session = MagicMock()
        src._session.get.side_effect = [info_resp, bin_resp]

        src.fetch_latest(identifier)
        first_kwargs = src._session.get.call_args_list[0][1]
        assert first_kwargs["auth"] == ("user", "pw")

    def test_no_credentials_passes_none(
        self, source: HttpFirmwareSource, identifier: FirmwareIdentifier
    ) -> None:
        info_resp = _make_response(text="1.0.0")
        bin_resp = _make_response(content=b"data")
        source._session = MagicMock()
        source._session.get.side_effect = [info_resp, bin_resp]

        source.fetch_latest(identifier)
        first_kwargs = source._session.get.call_args_list[0][1]
        assert first_kwargs["auth"] is None

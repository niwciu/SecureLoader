"""Unit tests for the firmware header parser."""

from __future__ import annotations

import pytest

from secure_loader.core.firmware import (
    DEVICE_HEADER_SIZE,
    HEADER_SIZE,
    FirmwareFormatError,
    build_device_header,
    parse_header,
    split_pages,
)


class TestParseHeader:
    def test_round_trips_known_values(self, sample_header_bytes: bytes) -> None:
        header = parse_header(sample_header_bytes)
        assert header.protocol_version == 0x00010002
        assert header.product_id == 0xAABBCCDD11223344
        assert header.product_id_msb == 0xAABBCCDD
        assert header.product_id_lsb == 0x11223344
        assert header.app_version == 0x01020304
        assert header.prev_app_version == 0x01020300
        assert header.page_count == 4
        assert header.flash_page_size == 256
        assert header.iv == bytes(range(16))
        assert header.crc32 == 0xDEADBEEF

    def test_payload_size_is_pages_times_pagesize(self, sample_header_bytes: bytes) -> None:
        assert parse_header(sample_header_bytes).payload_size == 4 * 256

    def test_license_id_matches_original_slice(self, sample_header_bytes: bytes) -> None:
        # product_id hex: AABBCCDD11223344 -> license = chars [4:6] = "CC"
        assert parse_header(sample_header_bytes).license_id == "CC"

    def test_unique_id_matches_original_slice(self, sample_header_bytes: bytes) -> None:
        # product_id hex: AABBCCDD11223344 -> unique = chars [12:16] = "3344"
        assert parse_header(sample_header_bytes).unique_id == "3344"

    def test_hex_formatting_is_upper_case_and_zero_padded(self, sample_header_bytes: bytes) -> None:
        header = parse_header(sample_header_bytes)
        assert header.format_protocol_version() == "0x00010002"
        assert header.format_product_id() == "0xAABBCCDD11223344"
        assert header.format_app_version() == "0x01020304"
        assert header.format_prev_app_version() == "0x01020300"

    def test_rejects_short_buffers(self) -> None:
        with pytest.raises(FirmwareFormatError):
            parse_header(b"\x00" * (HEADER_SIZE - 1))

    def test_accepts_extra_trailing_bytes(self, sample_header_bytes: bytes) -> None:
        padded = sample_header_bytes + b"payload-bytes-here"
        header = parse_header(padded)
        assert header.protocol_version == 0x00010002


class TestBuildDeviceHeader:
    def test_strips_prev_app_version_field(self, sample_firmware: bytes) -> None:
        wire = build_device_header(sample_firmware)
        assert len(wire) == DEVICE_HEADER_SIZE
        # First 16 bytes of the file are transmitted verbatim.
        assert wire[:16] == sample_firmware[:16]
        # Then comes [20:48] — the 4 bytes at [16:20] (prevAppVersion) are skipped.
        assert wire[16:] == sample_firmware[20:HEADER_SIZE]

    def test_rejects_short_blobs(self) -> None:
        with pytest.raises(FirmwareFormatError):
            build_device_header(b"\x00" * 10)


class TestSplitPages:
    def test_full_pages_only(self) -> None:
        payload = b"\x00" * 1024
        pages = split_pages(payload, page_size=256)
        assert len(pages) == 4
        assert all(len(p) == 256 for p in pages)

    def test_truncates_partial_trailing_page(self) -> None:
        payload = b"\x00" * (256 + 100)
        pages = split_pages(payload, page_size=256)
        assert len(pages) == 1  # trailing 100 bytes are dropped, per C++ behaviour

    def test_rejects_zero_page_size(self) -> None:
        with pytest.raises(ValueError):
            split_pages(b"\x00" * 10, page_size=0)

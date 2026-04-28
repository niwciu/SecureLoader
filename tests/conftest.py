"""Shared fixtures for unit tests."""

from __future__ import annotations

import struct

import pytest

from secure_loader.core.firmware import HEADER_SIZE

_HEADER = struct.Struct("<IIIIIII16sI")
assert _HEADER.size == HEADER_SIZE


@pytest.fixture
def sample_header_bytes() -> bytes:
    """Build a deterministic, known-valid firmware header.

    Fields encode to easy-to-recognise hex values so failures are legible:
        protocolVersion = 0x00010002
        productId_MSB   = 0xAABBCCDD
        productId_LSB   = 0x11223344
        appVersion      = 0x01020304
        prevAppVersion  = 0x01020300
        pageCount       = 4
        flashPageSize   = 256
        IV              = 0x00 .. 0x0F
        crc32           = 0xDEADBEEF
    """
    iv = bytes(range(16))
    return _HEADER.pack(
        0x00010002,
        0xAABBCCDD,
        0x11223344,
        0x01020304,
        0x01020300,
        4,
        256,
        iv,
        0xDEADBEEF,
    )


@pytest.fixture
def sample_firmware(sample_header_bytes: bytes) -> bytes:
    """A complete firmware blob: header + 4 pages x 256 bytes."""
    payload = bytes(i & 0xFF for i in range(4 * 256))
    return sample_header_bytes + payload

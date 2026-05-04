"""Firmware binary format parser.

Layout of an encrypted .bin file (little-endian):

    +--------+----------------------+---------+
    | Offset | Field                | Size    |
    +========+======================+=========+
    |   0    | protocolVersion      | u32     |
    |   4    | productId (MSB)      | u32     |
    |   8    | productId (LSB)      | u32     |
    |  12    | appVersion           | u32     |
    |  16    | prevAppVersion       | u32     |
    |  20    | pageCount            | u32     |
    |  24    | flashPageSize        | u32     |
    |  28    | IV                   | 16 B    |
    |  44    | crc32                | u32     |
    |  48    | encrypted payload    | variable|
    +--------+----------------------+---------+

The 64-bit productId is reconstructed as ``(MSB << 32) | LSB``.

The header that the device actually receives during a firmware update does
**not** contain ``prevAppVersion`` — that field is stripped before transmission
(see :class:`DeviceHeader`). ``prevAppVersion`` is only used by the host-side
downloader to request the previous version from a remote source.
"""

from __future__ import annotations

import logging
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

HEADER_SIZE: int = 48
"""Total size of the firmware header in bytes."""

DEVICE_HEADER_SIZE: int = 44
"""Size of the header sent to the device (header without ``prevAppVersion``)."""

IV_SIZE: int = 16
"""Size of the initialization vector in bytes."""

_HEADER_STRUCT = struct.Struct("<IIIIIII16sI")
assert _HEADER_STRUCT.size == HEADER_SIZE


class FirmwareFormatError(ValueError):
    """Raised when a firmware blob cannot be parsed."""


@dataclass(frozen=True, slots=True)
class FirmwareHeader:
    """Parsed representation of a firmware header.

    All integer fields are interpreted as unsigned little-endian.
    ``product_id`` is the 64-bit value assembled from the two 32-bit halves
    present on the wire.
    """

    protocol_version: int
    product_id: int
    app_version: int
    prev_app_version: int
    page_count: int
    flash_page_size: int
    iv: bytes
    crc32: int

    @property
    def product_id_msb(self) -> int:
        return (self.product_id >> 32) & 0xFFFFFFFF

    @property
    def product_id_lsb(self) -> int:
        return self.product_id & 0xFFFFFFFF

    @property
    def payload_size(self) -> int:
        """Expected size of the encrypted payload in bytes."""
        return self.page_count * self.flash_page_size

    @property
    def license_id(self) -> str:
        """License ID derived from the product ID.

        Characters ``[4:6]`` of the 16-hex-digit representation of ``productId``.
        """
        hex_id = f"{self.product_id:016X}"
        return hex_id[4:6]

    @property
    def unique_id(self) -> str:
        """Unique ID derived from the product ID.

        Characters ``[12:16]`` of the 16-hex-digit representation of ``productId``.
        """
        hex_id = f"{self.product_id:016X}"
        return hex_id[12:16]

    def format_protocol_version(self) -> str:
        return f"0x{self.protocol_version:08X}"

    def format_product_id(self) -> str:
        return f"0x{self.product_id:016X}"

    def format_app_version(self) -> str:
        return f"0x{self.app_version:08X}"

    def format_prev_app_version(self) -> str:
        return f"0x{self.prev_app_version:08X}"


def parse_header(data: bytes | bytearray | memoryview) -> FirmwareHeader:
    """Parse a firmware header from the first :data:`HEADER_SIZE` bytes of ``data``.

    Raises :class:`FirmwareFormatError` if ``data`` is too short.
    """
    if len(data) < HEADER_SIZE:
        raise FirmwareFormatError(
            f"firmware too short: need at least {HEADER_SIZE} bytes, got {len(data)}"
        )

    (
        protocol_version,
        product_id_msb,
        product_id_lsb,
        app_version,
        prev_app_version,
        page_count,
        flash_page_size,
        iv,
        crc32,
    ) = _HEADER_STRUCT.unpack_from(data, 0)

    product_id = (product_id_msb << 32) | product_id_lsb
    return FirmwareHeader(
        protocol_version=protocol_version,
        product_id=product_id,
        app_version=app_version,
        prev_app_version=prev_app_version,
        page_count=page_count,
        flash_page_size=flash_page_size,
        iv=bytes(iv),
        crc32=crc32,
    )


def validate_firmware(data: bytes | bytearray) -> FirmwareHeader:
    """Parse and fully validate a firmware blob.

    Checks:
    * Buffer is at least :data:`HEADER_SIZE` bytes (via :func:`parse_header`).
    * Payload length matches ``page_count x flash_page_size``.
    * CRC32 of the payload matches the value stored in the header.

    Returns the parsed :class:`FirmwareHeader` on success; raises
    :class:`FirmwareFormatError` on any validation failure.
    """
    header = parse_header(data)
    payload = data[HEADER_SIZE:]
    expected_len = header.page_count * header.flash_page_size
    if len(payload) < expected_len:
        raise FirmwareFormatError(
            f"payload too short: header declares {header.page_count} pages x "
            f"{header.flash_page_size} B = {expected_len} B, "
            f"but only {len(payload)} B follow the header"
        )
    actual_crc = zlib.crc32(payload[:expected_len]) & 0xFFFFFFFF
    if actual_crc != header.crc32:
        raise FirmwareFormatError(
            f"CRC32 mismatch: header says 0x{header.crc32:08X}, "
            f"computed 0x{actual_crc:08X} — file is corrupt or tampered"
        )
    return header


def load_firmware(path: str | Path) -> tuple[FirmwareHeader, bytes]:
    """Read a firmware file from disk, parse, and validate it.

    Raises :class:`FirmwareFormatError` if the file is too short, the payload
    length does not match the declared page count, or the CRC32 does not match.
    Raises :class:`OSError` if the file cannot be read.
    """
    data = Path(path).read_bytes()
    header = validate_firmware(data)
    return header, data


def build_device_header(raw: bytes | bytearray) -> bytes:
    """Build the header that is actually transmitted to the device.

    Wire header = bytes ``[0:16]`` (protocol + productId + appVersion)
    concatenated with bytes ``[20:48]`` (pageCount + pageLen + IV + CRC),
    dropping the 4-byte ``prevAppVersion`` field.
    """
    if len(raw) < HEADER_SIZE:
        raise FirmwareFormatError(
            f"firmware too short: need at least {HEADER_SIZE} bytes, got {len(raw)}"
        )
    first = bytes(raw[0:16])
    second = bytes(raw[20:HEADER_SIZE])
    wire = first + second
    if len(wire) != DEVICE_HEADER_SIZE:
        raise FirmwareFormatError(
            f"built device header is {len(wire)} bytes, expected {DEVICE_HEADER_SIZE}"
        )
    return wire


def split_pages(payload: bytes, page_size: int) -> list[bytes]:
    """Split the encrypted payload into fixed-size pages.

    Matches the C++ semantics: full pages are sent; a trailing partial page
    is **not** transmitted (the device will stop when pages run out).
    """
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    full = len(payload) // page_size
    if len(payload) % page_size:
        log.warning(
            "split_pages: payload length %d is not a multiple of page_size %d; "
            "trailing %d bytes will not be transmitted",
            len(payload),
            page_size,
            len(payload) % page_size,
        )
    return [payload[i * page_size : (i + 1) * page_size] for i in range(full)]

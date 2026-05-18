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

The wire header sent to the device during ``CMD_START`` is **44 bytes** —
``prevAppVersion`` is read from the file but **not** forwarded to the
bootloader (compatible with bootloader v1.1+).  The bootloader ``header_t``
struct no longer contains ``prevAppVersion``; all fields after ``appVersion``
shift down by 4 bytes compared to the file layout.
"""

from __future__ import annotations

import logging
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .id_sections import IdSectionDef

log = logging.getLogger(__name__)

HEADER_SIZE: int = 48
"""Total size of the firmware header in bytes."""

DEVICE_HEADER_SIZE: int = 44
"""Size of the header sent to the device over UART (44 bytes — prevAppVersion stripped)."""

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
    def custom_id(self) -> str:
        """Custom field (bytes 0-3): characters ``[0:8]`` of the 16-hex-digit product ID."""
        return f"{self.product_id:016X}"[0:8]

    @property
    def hw_id(self) -> str:
        """HW ID (byte 4): characters ``[8:10]`` of the 16-hex-digit product ID."""
        return f"{self.product_id:016X}"[8:10]

    @property
    def license_id(self) -> str:
        """License ID (byte 5): characters ``[10:12]`` of the 16-hex-digit product ID."""
        return f"{self.product_id:016X}"[10:12]

    @property
    def unique_id(self) -> str:
        """Unique ID (bytes 6-7): characters ``[12:16]`` of the 16-hex-digit product ID."""
        return f"{self.product_id:016X}"[12:16]

    def format_protocol_version(self) -> str:
        return f"0x{self.protocol_version:08X}"

    def format_product_id(self) -> str:
        return f"0x{self.product_id:016X}"

    def format_app_version(self) -> str:
        return f"0x{self.app_version:08X}"

    def format_prev_app_version(self) -> str:
        return f"0x{self.prev_app_version:08X}"

    def get_sections(self, defs: list[IdSectionDef]) -> dict[str, str]:
        """Extract section values from ``productId`` using ``defs``.

        Returns a ``{name: hex_value}`` dict where each value is the uppercase
        hex substring of the 16-char product ID at the range given by the
        corresponding :class:`~secure_loader.core.id_sections.IdSectionDef`.
        """
        hex_id = f"{self.product_id:016X}"
        return {d.name: d.extract(hex_id) for d in defs}


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
    """Parse and fully validate a firmware blob that contains an *unencrypted* payload.

    Checks:
    * Buffer is at least :data:`HEADER_SIZE` bytes (via :func:`parse_header`).
    * Payload length matches ``page_count x flash_page_size``.
    * CRC32 of the payload matches the value stored in the header.

    .. warning::
        Do **not** call this on EncryptBIN-produced files.  EncryptBIN computes
        the CRC over the *plaintext* payload and then encrypts it; the file on
        disk contains the *encrypted* payload, so the CRC will never match.
        This function is only valid for unencrypted test blobs.

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
    """Read a firmware file from disk, parse the header, and check payload length.

    Raises :class:`FirmwareFormatError` if the file is too short to contain a
    valid header or if the file does not contain the number of encrypted bytes
    declared in the header (``page_count x flash_page_size``).
    Raises :class:`OSError` if the file cannot be read.

    CRC validation is intentionally not performed here.  The CRC stored in the
    header is computed by EncryptBIN over the *unencrypted* payload before
    encryption; SecureLoader only ever sees the *encrypted* form and cannot
    reproduce that value.  CRC verification is performed by the device
    bootloader after decryption.
    """
    data = Path(path).read_bytes()
    header = parse_header(data)
    payload = data[HEADER_SIZE:]
    expected_len = header.page_count * header.flash_page_size
    if len(payload) < expected_len:
        raise FirmwareFormatError(
            f"payload too short: header declares {header.page_count} pages x "
            f"{header.flash_page_size} B = {expected_len} B, "
            f"but only {len(payload)} B follow the header"
        )
    return header, data


def build_device_header(raw: bytes | bytearray) -> bytes:
    """Return the 44-byte wire header transmitted to the device during CMD_START.

    ``prevAppVersion`` (file bytes [16:20]) is read by the host but **not**
    forwarded.  The returned buffer matches the bootloader v1.1+ ``header_t``
    layout exactly: file bytes [0:16] followed by file bytes [20:48].
    """
    if len(raw) < HEADER_SIZE:
        raise FirmwareFormatError(
            f"firmware too short: need at least {HEADER_SIZE} bytes, got {len(raw)}"
        )
    return bytes(raw[0:16]) + bytes(raw[20:HEADER_SIZE])


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

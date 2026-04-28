"""High-level update orchestration.

Glues together a :class:`~secure_loader.core.protocol.Protocol`
instance with a :class:`~secure_loader.core.firmware.FirmwareHeader`
and exposes helpers to validate that a firmware image matches the connected
device before starting the transfer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .firmware import FirmwareHeader
from .protocol import DeviceInfo


class DeviceMismatchError(ValueError):
    """Raised when a firmware does not match the connected device."""


@dataclass(frozen=True, slots=True)
class MismatchReason:
    """Structured reason describing why a firmware does not match a device."""

    bootloader_mismatch: bool
    product_mismatch: bool

    def __bool__(self) -> bool:
        return self.bootloader_mismatch or self.product_mismatch

    def describe(self) -> str:
        parts = []
        if self.bootloader_mismatch:
            parts.append("bootloader protocol version")
        if self.product_mismatch:
            parts.append("product ID")
        return ", ".join(parts) if parts else ""


def check_device_matches_firmware(device: DeviceInfo, firmware: FirmwareHeader) -> MismatchReason:
    """Return a :class:`MismatchReason` describing the compatibility of the pair.

    The ``MismatchReason`` is *falsy* when the firmware is compatible, which
    lets callers write ``if (reason := check_device_matches_firmware(...)):``.
    """
    return MismatchReason(
        bootloader_mismatch=device.bootloader_version != firmware.protocol_version,
        product_mismatch=device.product_id != firmware.product_id,
    )

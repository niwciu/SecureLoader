"""Unit tests for the device/firmware compatibility checker."""

from __future__ import annotations

from secure_loader.core.firmware import parse_header
from secure_loader.core.protocol import DeviceInfo
from secure_loader.core.updater import check_device_matches_firmware


class TestCompatibility:
    def test_matching_device_is_compatible(self, sample_firmware: bytes) -> None:
        header = parse_header(sample_firmware)
        device = DeviceInfo(
            bootloader_version=header.protocol_version,
            product_id=header.product_id,
            flash_page_size=header.flash_page_size,
        )
        reason = check_device_matches_firmware(device, header)
        assert not reason

    def test_product_mismatch_is_flagged(self, sample_firmware: bytes) -> None:
        header = parse_header(sample_firmware)
        device = DeviceInfo(
            bootloader_version=header.protocol_version,
            product_id=header.product_id + 1,
            flash_page_size=header.flash_page_size,
        )
        reason = check_device_matches_firmware(device, header)
        assert reason
        assert reason.product_mismatch
        assert not reason.bootloader_mismatch
        assert "product ID" in reason.describe()

    def test_bootloader_mismatch_is_flagged(self, sample_firmware: bytes) -> None:
        header = parse_header(sample_firmware)
        device = DeviceInfo(
            bootloader_version=header.protocol_version + 1,
            product_id=header.product_id,
            flash_page_size=header.flash_page_size,
        )
        reason = check_device_matches_firmware(device, header)
        assert reason
        assert reason.bootloader_mismatch
        assert "bootloader" in reason.describe()

    def test_page_size_mismatch_is_flagged(self, sample_firmware: bytes) -> None:
        header = parse_header(sample_firmware)
        device = DeviceInfo(
            bootloader_version=header.protocol_version,
            product_id=header.product_id,
            flash_page_size=header.flash_page_size * 2,
        )
        reason = check_device_matches_firmware(device, header)
        assert reason
        assert reason.page_size_mismatch
        assert "flash page size" in reason.describe()

    def test_zero_page_size_not_flagged(self, sample_firmware: bytes) -> None:
        """A zero page_size means the device hasn't reported its page size yet."""
        header = parse_header(sample_firmware)
        device = DeviceInfo(
            bootloader_version=header.protocol_version,
            product_id=header.product_id,
            flash_page_size=0,
        )
        reason = check_device_matches_firmware(device, header)
        assert not reason.page_size_mismatch

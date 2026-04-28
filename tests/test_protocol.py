"""Unit tests for the serial protocol state machine.

These tests exercise the state machine by feeding bytes directly into the
:class:`~secure_loader.core.protocol.Protocol` instance through
its private ``_handle_byte`` method. This is preferable to mocking
``pyserial``: the protocol logic is small, pure, and fully covered by
byte-level inputs without involving IO.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from secure_loader.core import protocol as proto
from secure_loader.core.protocol import (
    Command,
    DeviceInfo,
    Parity,
    Protocol,
    ProtocolCallbacks,
    State,
)


def _ack(cmd: Command) -> int:
    return int(cmd) ^ int(Command.OK_MASK)


def _nak(cmd: Command) -> int:
    return int(cmd) ^ int(Command.ERROR_MASK)


@pytest.fixture
def driver() -> Protocol:
    """A Protocol instance with no serial port opened — safe for pure state tests."""
    p = Protocol(port="/dev/null-stub", parity=Parity.NONE)
    # Stub out the serial writer so start_download can run without IO.
    p._write_cmd = MagicMock(return_value=True)  # type: ignore[method-assign]
    p._write_raw = MagicMock()  # type: ignore[method-assign]
    return p


class TestParity:
    def test_from_label_accepts_full_words(self) -> None:
        assert Parity.from_label("None") == Parity.NONE
        assert Parity.from_label("odd") == Parity.ODD
        assert Parity.from_label("EVEN") == Parity.EVEN

    def test_from_label_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            Parity.from_label("crazy")


class TestHandshake:
    def test_ack_then_16_info_bytes_yields_device_info(self, driver: Protocol) -> None:
        received: list[DeviceInfo] = []
        driver._callbacks = ProtocolCallbacks(on_device_info=received.append)
        driver._set_state(State.CONNECTING)

        # ACK for GetVersion.
        driver._handle_byte(_ack(Command.GET_VERSION))
        # 16 bytes of device info: u32 bootloader, u64 productId, u32 pageSize.
        info = struct.pack("<IQI", 0xABCD1234, 0xAABBCCDD11223344, 256)
        for b in info:
            driver._handle_byte(b)

        assert len(received) == 1
        assert received[0].bootloader_version == 0xABCD1234
        assert received[0].product_id == 0xAABBCCDD11223344
        assert received[0].flash_page_size == 256
        assert driver.state == State.CONNECTED

    def test_stray_ack_before_handshake_is_ignored(self, driver: Protocol) -> None:
        driver._set_state(State.CONNECTING)
        # Feed a bogus byte that is neither ACK(GetVersion) nor mid-info.
        driver._handle_byte(0x7F)
        assert driver.state == State.CONNECTING
        assert driver._handshake_tail == 0


class TestDownloadFlow:
    def _prime_connected(self, driver: Protocol, page_size: int = 256) -> None:
        driver._set_state(State.CONNECTING)
        driver._handle_byte(_ack(Command.GET_VERSION))
        info = struct.pack("<IQI", 0x1, 0x2, page_size)
        for b in info:
            driver._handle_byte(b)
        assert driver.state == State.CONNECTED

    def test_full_transfer_completes(self, driver: Protocol, sample_firmware: bytes) -> None:
        pages_seen: list[tuple[int, int]] = []
        done_flag: list[bool] = []
        driver._callbacks = ProtocolCallbacks(
            on_page_sent=lambda s, t: pages_seen.append((s, t)),
            on_download_done=lambda: done_flag.append(True),
        )
        self._prime_connected(driver, page_size=256)

        driver.start_download(sample_firmware)
        assert driver.state == State.STARTING

        driver._handle_byte(_ack(Command.START))  # kicks off first page
        assert driver.state == State.SENDING

        # ACK each subsequent page. 4 pages total; first is sent by the
        # START ACK handler, so 3 more NEXT_BLOCK ACKs trigger the rest, then
        # one final ACK with no remaining payload transitions back to CONNECTED.
        for _ in range(4):
            driver._handle_byte(_ack(Command.NEXT_BLOCK))

        assert driver.state == State.CONNECTED
        assert done_flag == [True]
        # We expect 4 page-sent callbacks for 4 full pages.
        assert len(pages_seen) == 4
        assert pages_seen[-1] == (4, 4)

    def test_device_error_during_start_aborts(
        self, driver: Protocol, sample_firmware: bytes
    ) -> None:
        errors: list[str] = []
        driver._callbacks = ProtocolCallbacks(on_error=errors.append)
        self._prime_connected(driver)

        driver.start_download(sample_firmware)
        driver._handle_byte(_nak(Command.START))

        assert driver.state == State.CONNECTING
        assert errors  # at least one error reported
        assert driver._download_error is not None

    def test_device_error_mid_transfer_aborts(
        self, driver: Protocol, sample_firmware: bytes
    ) -> None:
        driver._callbacks = ProtocolCallbacks()
        self._prime_connected(driver)
        driver.start_download(sample_firmware)
        driver._handle_byte(_ack(Command.START))  # first page sent
        driver._handle_byte(_nak(Command.NEXT_BLOCK))  # device reports error

        assert driver.state == State.CONNECTING
        assert driver._download_error is not None

    def test_start_rejected_when_not_connected(
        self, driver: Protocol, sample_firmware: bytes
    ) -> None:
        # State is IDLE by default.
        with pytest.raises(proto.ProtocolError):
            driver.start_download(sample_firmware)


class TestStateCallbacks:
    def test_state_changed_fires_on_transitions(self, driver: Protocol) -> None:
        seen: list[State] = []
        driver._callbacks = ProtocolCallbacks(on_state_changed=seen.append)
        driver._set_state(State.CONNECTING)
        driver._set_state(State.CONNECTED)
        driver._set_state(State.CONNECTED)  # duplicate, should be suppressed
        driver._set_state(State.IDLE)
        assert seen == [State.CONNECTING, State.CONNECTED, State.IDLE]

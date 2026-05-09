"""Serial protocol driver and state machine.

Wire protocol (1-byte command framing, little-endian payloads):

    Host → Device:
        GetVersion (0x01)            — poll the bootloader
        Start      (0x02) + header   — begin a firmware transfer
        NextPage   (0x03) + page     — transmit one page of payload
        Reset      (0x04)            — soft-reset the device

    Device → Host:
        (cmd XOR 0x40)  → OK acknowledgement
        (cmd XOR 0x80)  → Error acknowledgement
        After GetVersion + OK:
            bootloaderVersion : u32
            productId         : u64
            flashPageSize     : u32
        (16 bytes, little-endian)

The driver exposes a small synchronous API that is easy to drive from a CLI,
and emits callbacks that GUI frontends can hook into. It does not start any
threads on its own — the caller decides whether to run :meth:`Protocol.run`
on a worker thread (Qt) or as a blocking loop (CLI).
"""

from __future__ import annotations

import enum
import logging
import struct
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from serial import Serial, SerialException

from .firmware import (
    DEVICE_HEADER_SIZE,
    HEADER_SIZE,
    build_device_header,
    split_pages,
)

log = logging.getLogger(__name__)


class Command(enum.IntEnum):
    NONE = 0x00
    GET_VERSION = 0x01
    START = 0x02
    NEXT_PAGE = 0x03
    RESET = 0x04  # reserved — not yet issued by the host driver

    OK = 0x40
    ERR = 0x80


class State(enum.Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STARTING = "starting"
    SENDING = "sending"


class Parity(str, enum.Enum):
    NONE = "N"
    ODD = "O"
    EVEN = "E"

    @classmethod
    def from_label(cls, label: str) -> Parity:
        """Parse a parity from the user-facing labels used in the GUI."""
        m = {
            "none": cls.NONE,
            "odd": cls.ODD,
            "even": cls.EVEN,
            "n": cls.NONE,
            "o": cls.ODD,
            "e": cls.EVEN,
        }
        try:
            return m[label.strip().lower()]
        except KeyError as e:
            raise ValueError(f"unknown parity: {label!r}") from e


class ProtocolError(RuntimeError):
    """Raised when the device signals an error during a transfer."""


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Information reported by the bootloader in response to GetVersion."""

    bootloader_version: int
    product_id: int
    flash_page_size: int

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

    def format_bootloader_version(self) -> str:
        return f"0x{self.bootloader_version:08X}"

    def format_product_id(self) -> str:
        return f"0x{self.product_id:016X}"


POLL_INTERVAL_S: float = 0.5
"""Interval at which we re-send GetVersion while idle or connecting."""

CONNECTED_MISSED_POLLS: int = 3
"""Drop CONNECTED → CONNECTING after this many consecutive unanswered GetVersion polls (~1.5 s)."""

ERASE_TIMEOUT_S: float = 30.0
"""Max time to wait for START ACK while the device erases flash (STARTING state)."""

ALIVE_TIMEOUT_S: float = 2.0
"""Margin added on top of calculated page-transmission time for SENDING ACK timeout."""

_BITS_PER_BYTE: int = 10  # 8 data + 1 start + 1 stop (8N1)

BAUD_RATE: int = 115200
STOP_BITS: float = 1.0
DEFAULT_PAGE_SIZE: int = 1024
_DEVICE_INFO_STRUCT = struct.Struct("<IQI")
assert _DEVICE_INFO_STRUCT.size == 16


def _ack(cmd: Command) -> int:
    return int(cmd) ^ int(Command.OK)


def _nak(cmd: Command) -> int:
    return int(cmd) ^ int(Command.ERR)


@dataclass
class ProtocolCallbacks:
    """Hooks for UI frontends. All callbacks are optional."""

    on_state_changed: Callable[[State], None] | None = None
    on_device_info: Callable[[DeviceInfo], None] | None = None
    on_error: Callable[[str], None] | None = None
    on_page_sent: Callable[[int, int], None] | None = None  # (sent, total)
    on_download_done: Callable[[], None] | None = None


class Protocol:
    """Driver for the bootloader protocol.

    The driver owns a :class:`serial.Serial` instance. It is **not** safe to
    share a single :class:`Protocol` between threads — create one per
    connection and drive it from a single worker.
    """

    def __init__(
        self,
        port: str,
        parity: Parity = Parity.NONE,
        baudrate: int = BAUD_RATE,
        stopbits: float = STOP_BITS,
        callbacks: ProtocolCallbacks | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
        alive_timeout_s: float = ALIVE_TIMEOUT_S,
        connected_missed_polls: int = CONNECTED_MISSED_POLLS,
        erase_timeout_s: float = ERASE_TIMEOUT_S,
    ) -> None:
        self._port = port
        self._parity = parity
        self._baudrate = baudrate
        self._stopbits = stopbits
        self._callbacks = callbacks or ProtocolCallbacks()
        self._poll_interval_s = poll_interval_s
        self._alive_timeout_s = alive_timeout_s
        self._connected_missed_polls = connected_missed_polls
        self._erase_timeout_s = erase_timeout_s

        self._ser: Serial | None = None
        self._state: State = State.IDLE
        self._last_alive: float = 0.0
        self._missed_polls: int = 0
        self._pending_payload: bytes = b""
        self._pages_total: int = 0
        self._pages_sent: int = 0
        self._stop = threading.Event()
        self._connected_event = threading.Event()
        self._download_complete = threading.Event()
        self._download_error: str | None = None
        self._download_lock = threading.Lock()
        self._dev_page_size: int = 0
        self._handshake_buf: bytearray = bytearray()
        self._handshake_tail: int = 0

    # ------------------------------------------------------------------ public

    @property
    def state(self) -> State:
        return self._state

    def connect(self) -> None:
        """Open the serial port and flush stale RX data. Does not yet poll the device."""
        if self._ser is not None:
            return
        try:
            self._ser = Serial(
                port=self._port,
                baudrate=self._baudrate,
                parity=self._parity.value,
                bytesize=8,
                stopbits=self._stopbits,
                timeout=0.05,
                write_timeout=2.0,
            )
        except SerialException as e:
            raise ProtocolError(f"cannot open {self._port}: {e}") from e
        self._ser.reset_input_buffer()
        self._set_state(State.CONNECTING)

    def disconnect(self) -> None:
        """Close the serial port and reset internal state."""
        self._stop.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except SerialException:
                log.exception("error closing serial port")
            finally:
                self._ser = None
        self._set_state(State.IDLE)

    def run(self) -> None:
        """Run the polling + receive loop until :meth:`stop` is called.

        This is a blocking call. CLI usage typically wraps it in its own
        event loop; GUI usage should dispatch it to a worker thread.
        """
        if self._ser is None:
            raise ProtocolError("serial port is not open")

        self._stop.clear()
        next_poll = 0.0
        self._last_alive = time.monotonic()

        while not self._stop.is_set():
            now = time.monotonic()

            # CONNECTED: count-based — 3 consecutive unanswered polls → reconnect.
            if self._state == State.CONNECTED and self._missed_polls >= self._connected_missed_polls:
                log.warning("3 consecutive GetVersion polls unanswered — reconnecting")
                self._missed_polls = 0
                self._set_state(State.CONNECTING)

            # STARTING: wait up to erase_timeout_s for START ACK (flash erase can be slow).
            if self._state == State.STARTING and now - self._last_alive >= self._erase_timeout_s:
                log.warning("erase timeout (%.0f s) — reconnecting", self._erase_timeout_s)
                self._set_state(State.CONNECTING)

            # SENDING: timeout = page transmission time at current baud rate + write margin.
            if self._state == State.SENDING:
                page_size = self._dev_page_size or DEFAULT_PAGE_SIZE
                page_tx_s = (page_size * _BITS_PER_BYTE) / self._baudrate
                sending_timeout = page_tx_s + self._alive_timeout_s
                if now - self._last_alive >= sending_timeout:
                    log.warning(
                        "page ACK timeout (tx=%.2f s + margin=%.1f s) — reconnecting",
                        page_tx_s,
                        self._alive_timeout_s,
                    )
                    self._set_state(State.CONNECTING)

            # Periodic GetVersion poll while not in the middle of a transfer.
            if self._state in (State.IDLE, State.CONNECTING, State.CONNECTED) and now >= next_poll:
                self._write_cmd(Command.GET_VERSION)
                if self._state == State.CONNECTED:
                    self._missed_polls += 1
                next_poll = now + self._poll_interval_s

            # Read whatever the device has for us.
            self._drain_rx()
            time.sleep(0.01)

    def stop(self) -> None:
        self._stop.set()

    def start_download(self, firmware: bytes) -> None:
        """Begin a firmware download.

        Must be called after the device has reached :data:`State.CONNECTED`
        (so the flash page size reported by the device is known). The transfer
        itself proceeds asynchronously as :meth:`run` drives the state machine;
        callers that need to block until completion should use
        :meth:`wait_for_download` or the higher-level
        :meth:`download_blocking`.
        """
        wire_header = build_device_header(firmware)
        if len(wire_header) != DEVICE_HEADER_SIZE:
            raise ProtocolError(
                f"device header is {len(wire_header)} bytes, expected {DEVICE_HEADER_SIZE}"
            )

        page_size = self._dev_page_size or DEFAULT_PAGE_SIZE
        # File layout:
        #   [0:16]   protocol + productId + appVersion   (first half of header)
        #   [16:20]  prevAppVersion                      (stripped from wire)
        #   [20:48]  pageCount + pageLen + IV + CRC      (second half of header)
        #   [48:]    encrypted pages
        payload = firmware[HEADER_SIZE:]
        pages = split_pages(payload, page_size)
        with self._download_lock:
            if self._state != State.CONNECTED:
                raise ProtocolError(f"can't start download from state {self._state.name}")
            self._pending_payload = payload
            self._pages_total = len(pages)
            self._pages_sent = 0
            self._download_complete.clear()
            self._download_error = None
            # Transition inside the lock so the driver thread cannot observe a
            # window where payload is set but state is still CONNECTED.
            self._set_state(State.STARTING)
        # Reset the alive clock here so the erase timeout counts from when START
        # is actually sent, not from the last GET_VERSION ACK (up to 500 ms earlier).
        self._last_alive = time.monotonic()
        self._write_cmd(Command.START)
        self._write_raw(wire_header)

    def wait_for_download(self, timeout: float | None = None) -> None:
        """Block until the current download completes or an error occurs."""
        ok = self._download_complete.wait(timeout=timeout)
        if not ok:
            raise ProtocolError("download timed out")
        if self._download_error is not None:
            raise ProtocolError(self._download_error)

    def download_blocking(self, firmware: bytes, timeout: float = 300.0) -> None:
        """Convenience wrapper: drives the protocol loop until the transfer finishes.

        Intended for CLI usage where the caller has no separate event loop.
        """
        driver = threading.Thread(target=self.run, name="secureloader-protocol", daemon=True)
        driver.start()
        try:
            # Wait until the device is CONNECTED via an Event — avoids the TOCTOU
            # race that a busy-wait on _state would introduce.
            handshake_timeout = min(timeout, 30.0)
            if not self._connected_event.wait(timeout=handshake_timeout):
                if not driver.is_alive():
                    raise ProtocolError("protocol loop exited unexpectedly")
                raise ProtocolError("timed out waiting for device handshake")
            # start_download checks _state under its own lock; if the device
            # timed out between our wait() returning and this call, it raises
            # ProtocolError which propagates cleanly.
            self.start_download(firmware)
            self.wait_for_download(timeout=timeout)
        finally:
            self.stop()
            driver.join(timeout=2.0)
            if driver.is_alive():
                log.warning("protocol driver thread did not stop within timeout")

    # --------------------------------------------------------------- internals

    def _set_state(self, state: State) -> None:
        if state == self._state:
            return
        self._state = state
        if state == State.CONNECTED:
            self._connected_event.set()
        elif self._connected_event.is_set():
            self._connected_event.clear()
        if state == State.CONNECTING and (ser := self._ser) is not None:
            ser.reset_input_buffer()
        if self._callbacks.on_state_changed:
            try:
                self._callbacks.on_state_changed(state)
            except Exception:
                log.exception("on_state_changed callback raised")

    def _emit_error(self, msg: str) -> None:
        log.error("protocol error: %s", msg)
        if self._callbacks.on_error:
            try:
                self._callbacks.on_error(msg)
            except Exception:
                log.exception("on_error callback raised")

    def _write_cmd(self, cmd: Command) -> bool:
        ser = self._ser
        if ser is None:
            return False
        try:
            n = ser.write(bytes([int(cmd)]))
            return n == 1
        except SerialException:
            log.exception("serial write failed")
            return False

    def _write_raw(self, data: bytes) -> None:
        ser = self._ser
        if ser is None:
            return
        try:
            ser.write(data)
        except SerialException as e:
            self._emit_error(f"serial write failed: {e}")
            self._stop.set()

    def _drain_rx(self) -> None:
        ser = self._ser
        if ser is None:
            return
        try:
            chunk = ser.read(ser.in_waiting or 1)
        except SerialException as e:
            self._emit_error(f"serial read failed: {e}")
            self._stop.set()
            return
        for byte in chunk:
            self._handle_byte(byte)

    # Byte-by-byte state machine dispatcher.
    def _handle_byte(self, byte: int) -> None:
        state = self._state
        if state in (State.CONNECTING, State.CONNECTED):
            self._handle_handshake_byte(byte)
        elif state == State.STARTING:
            if byte == _ack(Command.START):
                self._pages_sent = 0
                self._last_alive = time.monotonic()
                self._send_next_page()
            elif byte == _nak(Command.START):
                self._on_download_error()
        elif state == State.SENDING:
            if byte == _ack(Command.NEXT_PAGE):
                self._last_alive = time.monotonic()
                self._send_next_page()
            elif byte == _nak(Command.NEXT_PAGE):
                self._on_download_error()
        # IDLE: swallow stray bytes silently.

    def _handle_handshake_byte(self, byte: int) -> None:
        # We expect: one ACK byte, followed by 16 bytes of device info.
        _expected_info_bytes = 16
        if self._handshake_tail:
            self._handshake_buf.append(byte)
            self._handshake_tail -= 1
            if len(self._handshake_buf) > _expected_info_bytes:
                # Belt-and-suspenders: should never happen given the tail counter,
                # but discard and reset so a misbehaving device can't grow the buffer.
                log.warning("handshake buffer exceeded %d bytes — discarding", _expected_info_bytes)
                self._handshake_buf.clear()
                self._handshake_tail = 0
            elif self._handshake_tail == 0:
                info_bytes = bytes(self._handshake_buf)
                self._handshake_buf.clear()
                self._process_device_info(info_bytes)
        elif byte == _ack(Command.GET_VERSION):
            self._handshake_buf.clear()
            self._handshake_tail = 16
            self._last_alive = time.monotonic()
            self._missed_polls = 0

    def _process_device_info(self, info: bytes) -> None:
        bl_version, product_id, page_size = _DEVICE_INFO_STRUCT.unpack(info)
        self._dev_page_size = page_size
        self._set_state(State.CONNECTED)
        dev = DeviceInfo(
            bootloader_version=bl_version,
            product_id=product_id,
            flash_page_size=page_size,
        )
        if self._callbacks.on_device_info:
            try:
                self._callbacks.on_device_info(dev)
            except Exception:
                log.exception("on_device_info callback raised")

    def _send_next_page(self) -> None:
        page_size = self._dev_page_size or DEFAULT_PAGE_SIZE
        with self._download_lock:
            has_page = len(self._pending_payload) >= page_size
            if has_page:
                page, self._pending_payload = (
                    self._pending_payload[:page_size],
                    self._pending_payload[page_size:],
                )
                self._pages_sent += 1
        if has_page:
            self._set_state(State.SENDING)
            self._write_cmd(Command.NEXT_PAGE)
            self._write_raw(page)
            if self._callbacks.on_page_sent:
                try:
                    self._callbacks.on_page_sent(self._pages_sent, self._pages_total)
                except Exception:
                    log.exception("on_page_sent callback raised")
        else:
            self._set_state(State.CONNECTED)
            self._download_complete.set()
            if self._callbacks.on_download_done:
                try:
                    self._callbacks.on_download_done()
                except Exception:
                    log.exception("on_download_done callback raised")

    def _on_download_error(self) -> None:
        self._download_error = "Unexpected error from the device. Download aborted."
        self._download_complete.set()
        self._emit_error(self._download_error)
        self._set_state(State.CONNECTING)

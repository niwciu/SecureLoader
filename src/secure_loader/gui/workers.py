"""Qt thread workers wrapping the core logic.

The core layer is deliberately framework-agnostic: it exposes plain
callbacks (:class:`~secure_loader.core.protocol.ProtocolCallbacks`).
These workers translate those callbacks into Qt signals, and run the
blocking loops on background :class:`QThread` instances so the UI stays
responsive.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..core.firmware import FirmwareHeader, parse_header
from ..core.protocol import (
    DeviceInfo,
    Parity,
    Protocol,
    ProtocolCallbacks,
    ProtocolError,
    State,
)
from ..core.sources import FirmwareIdentifier, FirmwareSource, FirmwareSourceError

log = logging.getLogger(__name__)


class ProtocolWorker(QObject):
    """Runs a :class:`Protocol` instance on a dedicated thread.

    Emits Qt signals for every event the GUI cares about. One instance per
    serial connection; when the connection is closed the worker is stopped
    and discarded.
    """

    state_changed = Signal(State)
    device_info = Signal(DeviceInfo)
    error_occurred = Signal(str)
    page_sent = Signal(int, int)  # sent, total
    download_done = Signal()
    finished = Signal()

    def __init__(self, port: str, parity: Parity, baudrate: int, stopbits: float) -> None:
        super().__init__()
        self._port = port
        self._parity = parity
        self._baudrate = baudrate
        self._stopbits = stopbits
        self._proto: Protocol | None = None

    @Slot()
    def run(self) -> None:
        callbacks = ProtocolCallbacks(
            on_state_changed=lambda s: self.state_changed.emit(s),
            on_device_info=lambda d: self.device_info.emit(d),
            on_error=lambda m: self.error_occurred.emit(m),
            on_page_sent=lambda s, t: self.page_sent.emit(s, t),
            on_download_done=lambda: self.download_done.emit(),
        )
        self._proto = Protocol(
            port=self._port,
            parity=self._parity,
            baudrate=self._baudrate,
            stopbits=self._stopbits,
            callbacks=callbacks,
        )
        try:
            self._proto.connect()
        except ProtocolError as e:
            self.error_occurred.emit(str(e))
            self.finished.emit()
            return
        try:
            self._proto.run()
        except Exception as e:  # pragma: no cover — defensive only
            log.exception("protocol loop crashed")
            self.error_occurred.emit(str(e))
        finally:
            try:
                self._proto.disconnect()
            except Exception:
                log.exception("error during disconnect")
            self._proto = None  # release reference before signalling done
            self.finished.emit()

    @Slot(bytes)
    def start_download(self, firmware: bytes) -> None:
        proto = self._proto
        if proto is None:
            return
        try:
            proto.start_download(firmware)
        except ProtocolError as e:
            self.error_occurred.emit(str(e))

    @Slot()
    def stop(self) -> None:
        proto = self._proto
        if proto is not None:
            proto.stop()


class DownloadWorker(QObject):
    """Fetch a firmware blob from a :class:`FirmwareSource` on a background thread."""

    # second argument is FirmwareHeader | None — Signal() does not support union types
    finished = Signal(bytes, object)
    progress = Signal(int, int)
    error_occurred = Signal(str)

    def __init__(
        self,
        source: FirmwareSource,
        identifier: FirmwareIdentifier,
        *,
        previous: bool = False,
    ) -> None:
        super().__init__()
        self._source = source
        self._identifier = identifier
        self._previous = previous

    @Slot()
    def run(self) -> None:
        try:
            progress_cb = lambda r, t: self.progress.emit(r, t)  # noqa: E731
            if self._previous:
                data = self._source.fetch_previous(self._identifier, progress_cb)
            else:
                data = self._source.fetch_latest(self._identifier, progress_cb)
        except FirmwareSourceError as e:
            self.error_occurred.emit(str(e))
            return
        except Exception as e:
            log.exception("firmware source crashed")
            self.error_occurred.emit(str(e))
            return

        header: FirmwareHeader | None = None
        try:
            header = parse_header(data)
        except Exception:
            log.exception("downloaded blob does not parse as a firmware header")
        self.finished.emit(data, header)


def start_in_thread(worker: QObject, parent: QObject | None = None) -> QThread:
    """Move ``worker`` to a freshly created thread and start it.

    The thread quits when the worker emits ``finished``; both objects are
    scheduled for deletion via ``deleteLater``.
    """
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)  # type: ignore[attr-defined]
    if hasattr(worker, "finished"):
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread


def read_firmware_file(path: str | Path) -> tuple[FirmwareHeader, bytes]:
    """Tiny sync helper so call sites don't need to import ``core.firmware``."""
    from ..core.firmware import load_firmware

    return load_firmware(path)

"""Tests for Qt worker objects (ProtocolWorker, DownloadWorker, start_in_thread)."""

from __future__ import annotations

import struct
import zlib
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _make_firmware() -> bytes:
    payload = bytes(range(256)) * 4
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    header = struct.pack(
        "<IIIIIII16sI",
        0x00010002, 0xAABBCCDD, 0x11223344,
        0x01020304, 0x01020300, 4, 256, bytes(16), crc,
    )
    return header + payload


class TestProtocolWorkerRun:
    def test_run_success_emits_finished(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        finished = []
        worker.finished.connect(lambda: finished.append(True))

        with patch("secure_loader.gui.workers.Protocol") as MockProto:
            inst = MockProto.return_value
            inst.connect.return_value = None
            inst.run.return_value = None
            inst.disconnect.return_value = None
            worker.run()

        assert finished

    def test_run_calls_disconnect_after_run(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        with patch("secure_loader.gui.workers.Protocol") as MockProto:
            inst = MockProto.return_value
            worker.run()
        inst.disconnect.assert_called_once()

    def test_run_connect_error_emits_error_and_finished(self, qapp) -> None:
        from secure_loader.core.protocol import Parity, ProtocolError
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        errors: list[str] = []
        finished: list[bool] = []
        worker.error_occurred.connect(errors.append)
        worker.finished.connect(lambda: finished.append(True))

        with patch("secure_loader.gui.workers.Protocol") as MockProto:
            MockProto.return_value.connect.side_effect = ProtocolError("no device")
            worker.run()

        assert errors
        assert finished

    def test_run_proto_is_none_after_completion(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        with patch("secure_loader.gui.workers.Protocol"):
            worker.run()
        assert worker._proto is None

    def test_start_download_with_proto_delegates(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        mock_proto = MagicMock()
        worker._proto = mock_proto

        worker.start_download(b"\x00" * 48)

        mock_proto.start_download.assert_called_once_with(b"\x00" * 48)

    def test_start_download_protocol_error_emits_error(self, qapp) -> None:
        from secure_loader.core.protocol import Parity, ProtocolError
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        mock_proto = MagicMock()
        mock_proto.start_download.side_effect = ProtocolError("bad state")
        worker._proto = mock_proto

        errors: list[str] = []
        worker.error_occurred.connect(errors.append)
        worker.start_download(b"\x00" * 48)

        assert errors

    def test_stop_with_proto_calls_proto_stop(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        mock_proto = MagicMock()
        worker._proto = mock_proto

        worker.stop()

        mock_proto.stop.assert_called_once()


class TestDownloadWorker:
    def test_init_stores_fields(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        source = MagicMock()
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident, previous=True)

        assert worker._source is source
        assert worker._identifier is ident
        assert worker._previous is True

    def test_run_latest_calls_fetch_latest_and_emits_finished(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        fw = _make_firmware()
        source = MagicMock()
        source.fetch_latest.return_value = fw
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident, previous=False)

        results: list[tuple] = []
        worker.finished.connect(lambda data, hdr: results.append((data, hdr)))
        worker.run()

        source.fetch_latest.assert_called_once()
        assert results
        assert results[0][0] == fw
        assert results[0][1] is not None  # header parsed

    def test_run_previous_calls_fetch_previous(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        source = MagicMock()
        source.fetch_previous.return_value = _make_firmware()
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident, previous=True)

        worker.run()

        source.fetch_previous.assert_called_once()
        source.fetch_latest.assert_not_called()

    def test_run_source_error_emits_error_signal(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier, FirmwareSourceError
        from secure_loader.gui.workers import DownloadWorker

        source = MagicMock()
        source.fetch_latest.side_effect = FirmwareSourceError("server down")
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident)

        errors: list[str] = []
        worker.error_occurred.connect(errors.append)
        worker.run()

        assert errors

    def test_run_generic_exception_emits_error_signal(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        source = MagicMock()
        source.fetch_latest.side_effect = RuntimeError("unexpected crash")
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident)

        errors: list[str] = []
        worker.error_occurred.connect(errors.append)
        worker.run()

        assert errors

    def test_run_unparseable_blob_emits_finished_with_none_header(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        source = MagicMock()
        source.fetch_latest.return_value = b"\x00" * 10
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident)

        results: list = []
        worker.finished.connect(lambda data, hdr: results.append(hdr))
        worker.run()

        assert results
        assert results[0] is None

    def test_run_emits_progress_callback(self, qapp) -> None:
        from secure_loader.core.sources.base import FirmwareIdentifier
        from secure_loader.gui.workers import DownloadWorker

        fw = _make_firmware()

        def fetch_with_progress(ident, progress=None):
            if progress:
                progress(len(fw), len(fw))
            return fw

        source = MagicMock()
        source.fetch_latest.side_effect = fetch_with_progress
        ident = FirmwareIdentifier(license_id="AA", unique_id="1234")
        worker = DownloadWorker(source, ident)

        progress_calls: list[tuple] = []
        worker.progress.connect(lambda r, t: progress_calls.append((r, t)))
        worker.run()

        assert progress_calls



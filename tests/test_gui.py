"""Smoke tests for the GUI layer (offscreen, no display required).

Run with:  QT_QPA_PLATFORM=offscreen pytest tests/test_gui.py
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def main_window(qapp):
    from secure_loader.config import AppConfig
    from secure_loader.gui.main_window import MainWindow

    win = MainWindow(config=AppConfig())
    yield win
    win.close()


@pytest.fixture
def login_dialog(qapp):
    from secure_loader.config import AppConfig
    from secure_loader.gui.login_dialog import LoginDialog

    dlg = LoginDialog(config=AppConfig())
    yield dlg
    dlg.close()


class TestMainWindowSmoke:
    def test_instantiates_without_error(self, main_window) -> None:
        assert main_window is not None

    def test_window_title_is_set(self, main_window) -> None:
        assert main_window.windowTitle() != ""

    def test_connect_button_exists_and_is_enabled(self, main_window) -> None:
        assert main_window.connect_button is not None
        assert main_window.connect_button.isEnabled()

    def test_download_button_disabled_before_connect(self, main_window) -> None:
        assert not main_window.download_button.isEnabled()

    def test_fetch_buttons_disabled_before_connect(self, main_window) -> None:
        assert not main_window.get_firmware_button.isEnabled()
        assert not main_window.get_prev_firmware_button.isEnabled()

    def test_refresh_button_exists(self, main_window) -> None:
        assert main_window.refresh_button is not None

    def test_select_file_button_exists(self, main_window) -> None:
        assert main_window.input_file_button is not None

    def test_download_progress_bar_exists(self, main_window) -> None:
        assert main_window.download_progress is not None

    def test_http_progress_bar_exists(self, main_window) -> None:
        assert main_window.http_progress is not None

    def test_bootloader_edit_starts_empty(self, main_window) -> None:
        assert main_window.bootloader_edit.text() == ""


class TestProtocolWorkerThreadSafety:
    def test_stop_before_run_does_not_crash(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        # Calling stop() before run() must be a safe no-op (_proto is None).
        worker.stop()
        assert worker._proto is None

    def test_start_download_before_run_does_not_crash(self, qapp) -> None:
        from secure_loader.core.protocol import Parity
        from secure_loader.gui.workers import ProtocolWorker

        worker = ProtocolWorker(port="/dev/null", parity=Parity.NONE, baudrate=115200, stopbits=1.0)
        # Calling start_download() before run() must be a safe no-op (_proto is None).
        worker.start_download(b"\x00" * 48)
        assert worker._proto is None


class TestWorkerHelpers:
    def test_read_firmware_file_returns_header_and_bytes(self, tmp_path) -> None:
        import struct
        import zlib

        from secure_loader.gui.workers import read_firmware_file

        payload = bytes(range(256)) * 4
        crc = zlib.crc32(payload) & 0xFFFFFFFF
        header = struct.pack(
            "<IIIIIII16sI",
            0x00010002,
            0xAABBCCDD,
            0x11223344,
            0x01020304,
            0x01020300,
            4,
            256,
            bytes(16),
            crc,
        )
        fw = tmp_path / "test.bin"
        fw.write_bytes(header + payload)
        hdr, data = read_firmware_file(str(fw))
        assert hdr.page_count == 4
        assert data == header + payload


class TestAppMain:
    def test_main_returns_integer(self, qapp) -> None:
        from unittest.mock import patch

        from secure_loader.gui.app import main

        with (
            patch("secure_loader.gui.app.QApplication.exec", return_value=0),
            patch("secure_loader.gui.app.QApplication", return_value=qapp),
        ):
            result = main(argv=[])
        assert isinstance(result, int)


class TestLoginDialogSmoke:
    def test_instantiates_without_error(self, login_dialog) -> None:
        assert login_dialog is not None

    def test_window_title_is_set(self, login_dialog) -> None:
        assert login_dialog.windowTitle() != ""

    def test_login_field_starts_empty(self, login_dialog) -> None:
        assert login_dialog._login.text() == ""

    def test_password_field_starts_empty(self, login_dialog) -> None:
        assert login_dialog._password.text() == ""

    def test_password_is_masked_by_default(self, login_dialog) -> None:
        from PySide6.QtWidgets import QLineEdit

        assert login_dialog._password.echoMode() == QLineEdit.EchoMode.Password

    def test_show_password_button_exists(self, login_dialog) -> None:
        assert login_dialog._show_button is not None

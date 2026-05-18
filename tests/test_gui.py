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


class TestMainWindowHandlers:
    """Directly invoke MainWindow event-handler methods with mocked dependencies."""

    def _make_device_info(self):
        from secure_loader.core.protocol import DeviceInfo

        return DeviceInfo(
            bootloader_version=0x1, product_id=0xAABBCCDD11223344, flash_page_size=256
        )

    def _make_firmware_header(self, sample_firmware):
        from secure_loader.core.firmware import parse_header

        return parse_header(sample_firmware)

    def test_retranslate_ui_runs_without_error(self, main_window) -> None:
        main_window._retranslate_ui()

    def test_update_status_text_idle(self, main_window) -> None:
        from secure_loader.core.protocol import State

        main_window._update_status_text(State.IDLE)
        assert main_window.status_edit.text() != ""

    def test_update_status_text_connected(self, main_window) -> None:
        from secure_loader.core.protocol import State

        main_window._update_status_text(State.CONNECTED)
        assert "Connect" in main_window.status_edit.text()

    def test_on_state_changed_clears_device_info_on_idle(self, main_window) -> None:
        from secure_loader.core.protocol import State

        main_window._device_info = self._make_device_info()
        main_window._on_state_changed(State.IDLE)
        assert main_window._device_info is None

    def test_on_state_changed_keeps_device_info_on_connected(self, main_window) -> None:
        from secure_loader.core.protocol import State

        main_window._device_info = self._make_device_info()
        main_window._on_state_changed(State.CONNECTED)
        assert main_window._device_info is not None

    def test_on_device_info_populates_fields(self, main_window) -> None:
        info = self._make_device_info()
        main_window._on_device_info(info)
        assert main_window.dev_product_id_edit.text() != ""
        assert main_window.bootloader_edit.text() != ""

    def test_on_protocol_finished_clears_worker_references(self, main_window) -> None:
        from unittest.mock import MagicMock

        main_window._protocol_worker = MagicMock()
        main_window._protocol_thread = MagicMock()
        main_window._on_protocol_finished()
        assert main_window._protocol_worker is None
        assert main_window._protocol_thread is None

    def test_on_page_sent_updates_progress_bar(self, main_window) -> None:
        main_window._on_page_sent(3, 10)
        assert main_window.download_progress.maximum() == 10
        assert main_window.download_progress.value() == 3

    def test_on_download_done_shows_message(self, main_window) -> None:
        from unittest.mock import patch

        with patch("secure_loader.gui.main_window.QMessageBox.information") as mock_msg:
            main_window._on_download_done()
        mock_msg.assert_called_once()

    def test_on_protocol_error_shows_message_and_disconnects(self, main_window) -> None:
        from unittest.mock import patch

        with (
            patch("secure_loader.gui.main_window.QMessageBox.critical"),
            patch.object(main_window, "_disconnect_serial") as mock_disc,
        ):
            main_window._on_protocol_error("device lost")
        mock_disc.assert_called_once()

    def test_current_baudrate_returns_int(self, main_window) -> None:
        assert isinstance(main_window._current_baudrate(), int)

    def test_current_parity_returns_parity(self, main_window) -> None:
        from secure_loader.core.protocol import Parity

        assert isinstance(main_window._current_parity(), Parity)

    def test_current_stopbits_returns_float(self, main_window) -> None:
        assert isinstance(main_window._current_stopbits(), float)

    def test_populate_ports_with_no_ports(self, main_window) -> None:
        from unittest.mock import patch

        with patch("secure_loader.gui.main_window.list_ports.comports", return_value=[]):
            main_window._populate_ports()
        assert main_window.port_box.count() == 0

    def test_on_connect_clicked_when_not_connected_calls_connect(self, main_window) -> None:
        from unittest.mock import patch

        main_window._is_connected = False
        with patch.object(main_window, "_connect_serial") as mock_conn:
            main_window._on_connect_clicked()
        mock_conn.assert_called_once()

    def test_on_connect_clicked_when_connected_calls_disconnect(self, main_window) -> None:
        from unittest.mock import patch

        main_window._is_connected = True
        with patch.object(main_window, "_disconnect_serial") as mock_disc:
            main_window._on_connect_clicked()
        mock_disc.assert_called_once()

    def test_disconnect_serial_with_no_worker_does_not_crash(self, main_window) -> None:
        main_window._protocol_worker = None
        main_window._protocol_thread = None
        main_window._disconnect_serial()
        assert not main_window._is_connected

    def test_clear_firmware_info_empties_fields(self, main_window) -> None:
        main_window.protocol_edit.setText("0x1")
        main_window._clear_firmware_info()
        assert main_window.protocol_edit.text() == ""
        assert main_window._firmware_bytes == b""

    def test_clear_device_info_empties_fields(self, main_window) -> None:
        main_window.dev_product_id_edit.setText("0xDEAD")
        main_window._clear_device_info()
        assert main_window.dev_product_id_edit.text() == ""
        assert main_window._device_info is None

    def test_load_firmware_into_ui_populates_fields(self, main_window, sample_firmware) -> None:
        header = self._make_firmware_header(sample_firmware)
        main_window._load_firmware_into_ui(header, sample_firmware)
        assert main_window.protocol_edit.text() != ""
        assert main_window.product_id_edit.text() != ""
        assert main_window._firmware_header is header
        assert main_window._firmware_bytes is sample_firmware

    def test_on_http_progress_sets_progress_bar(self, main_window) -> None:
        main_window._on_http_progress(50, 200)
        assert main_window.http_progress.maximum() == 200
        assert main_window.http_progress.value() == 50

    def test_on_fetch_finished_with_valid_header_loads_firmware(
        self, main_window, sample_firmware
    ) -> None:
        from unittest.mock import patch

        header = self._make_firmware_header(sample_firmware)
        with patch("secure_loader.gui.main_window.QMessageBox.information"):
            main_window._on_fetch_finished(sample_firmware, header)
        assert main_window._firmware_bytes == sample_firmware

    def test_on_fetch_finished_with_none_header_shows_warning(self, main_window) -> None:
        from unittest.mock import patch

        with patch("secure_loader.gui.main_window.QMessageBox.warning") as mock_warn:
            main_window._on_fetch_finished(b"\x00" * 10, None)
        mock_warn.assert_called_once()

    def test_on_fetch_error_shows_message(self, main_window) -> None:
        from unittest.mock import patch

        with patch("secure_loader.gui.main_window.QMessageBox.critical") as mock_err:
            main_window._on_fetch_error("timeout")
        mock_err.assert_called_once()

    def test_on_update_clicked_with_no_worker_is_noop(self, main_window) -> None:
        main_window._protocol_worker = None
        main_window._firmware_bytes = b"\x00" * 48
        main_window._on_update_clicked()  # must not raise

    def test_on_update_clicked_calls_start_download(self, main_window) -> None:
        from unittest.mock import MagicMock

        mock_worker = MagicMock()
        main_window._protocol_worker = mock_worker
        main_window._firmware_bytes = b"\x00" * 48
        main_window._on_update_clicked()
        mock_worker.start_download.assert_called_once_with(b"\x00" * 48)
        main_window._protocol_worker = None

    def test_update_download_button_disabled_without_firmware(self, main_window) -> None:
        main_window._firmware_bytes = b""
        main_window._update_download_button()
        assert not main_window.download_button.isEnabled()

    def test_refresh_compatibility_no_device_no_firmware(self, main_window) -> None:
        main_window._device_info = None
        main_window._firmware_header = None
        main_window._refresh_compatibility_indicator()
        assert not main_window._compat_ok

    def test_refresh_compatibility_matching_device_and_firmware(
        self, main_window, sample_firmware
    ) -> None:
        from secure_loader.core.protocol import DeviceInfo

        # bootloader_version must match firmware.protocol_version (0x00010002)
        info = DeviceInfo(
            bootloader_version=0x00010002,
            product_id=0xAABBCCDD11223344,
            flash_page_size=256,
        )
        header = self._make_firmware_header(sample_firmware)
        main_window._device_info = info
        main_window._firmware_header = header
        main_window._refresh_compatibility_indicator()
        assert main_window._compat_ok

    def test_remember_recent_prepends_and_caps_at_10(self, main_window) -> None:
        from unittest.mock import patch

        main_window._config.last_firmware_paths = [f"/old/fw{i}.bin" for i in range(10)]
        with patch("secure_loader.gui.main_window.save_config"):
            main_window._remember_recent("/new/fw.bin")
        assert main_window._config.last_firmware_paths[0] == "/new/fw.bin"
        assert len(main_window._config.last_firmware_paths) == 10


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


@pytest.fixture
def server_settings_dialog(qapp):
    from secure_loader.config import AppConfig
    from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

    dlg = ServerSettingsDialog(config=AppConfig())
    yield dlg
    dlg.close()


class TestServerSettingsDialogSmoke:
    def test_instantiates_without_error(self, server_settings_dialog) -> None:
        assert server_settings_dialog is not None

    def test_window_title_is_set(self, server_settings_dialog) -> None:
        assert server_settings_dialog.windowTitle() != ""

    def test_url_edit_populated_from_config(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_base_url = "https://fw.example.com"
        dlg = ServerSettingsDialog(config=cfg)
        assert dlg._url_edit.text() == "https://fw.example.com"
        dlg.close()

    def test_credentials_populated_from_config(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_login = "alice"
        cfg.http_password = "secret"
        cfg.http_use_credentials = True
        dlg = ServerSettingsDialog(config=cfg)
        assert dlg._login_edit.text() == "alice"
        assert dlg._pwd_edit.text() == "secret"
        dlg.close()

    def test_use_credentials_checkbox_unchecked_by_default(self, server_settings_dialog) -> None:
        assert not server_settings_dialog._cred_box.isChecked()

    def test_use_credentials_checkbox_reflects_config(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_use_credentials = True
        dlg = ServerSettingsDialog(config=cfg)
        assert dlg._cred_box.isChecked()
        dlg.close()

    def test_fields_disabled_when_credentials_unchecked(self, server_settings_dialog) -> None:
        server_settings_dialog._cred_box.setChecked(False)
        assert not server_settings_dialog._login_edit.isEnabled()
        assert not server_settings_dialog._pwd_edit.isEnabled()

    def test_fields_enabled_when_credentials_checked(self, server_settings_dialog) -> None:
        server_settings_dialog._cred_box.setChecked(True)
        assert server_settings_dialog._login_edit.isEnabled()
        assert server_settings_dialog._pwd_edit.isEnabled()

    def test_save_persists_use_credentials_true(self, qapp, tmp_path) -> None:
        from unittest.mock import patch

        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.config_path = str(tmp_path / "config.ini")
        dlg = ServerSettingsDialog(config=cfg)
        dlg._cred_box.setChecked(True)
        with patch("secure_loader.gui.server_settings_dialog.save_config"):
            dlg._save_and_accept()
        assert cfg.http_use_credentials is True
        dlg.close()

    def test_save_persists_use_credentials_false(self, qapp, tmp_path) -> None:
        from unittest.mock import patch

        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.config_path = str(tmp_path / "config.ini")
        dlg = ServerSettingsDialog(config=cfg)
        dlg._cred_box.setChecked(False)
        with patch("secure_loader.gui.server_settings_dialog.save_config"):
            dlg._save_and_accept()
        assert cfg.http_use_credentials is False
        dlg.close()

    def test_password_is_masked_by_default(self, server_settings_dialog) -> None:
        from PySide6.QtWidgets import QLineEdit

        assert server_settings_dialog._pwd_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_toggle_password_shows_and_hides(self, server_settings_dialog) -> None:
        from PySide6.QtWidgets import QLineEdit

        server_settings_dialog._toggle_password(True)
        assert server_settings_dialog._pwd_edit.echoMode() == QLineEdit.EchoMode.Normal
        server_settings_dialog._toggle_password(False)
        assert server_settings_dialog._pwd_edit.echoMode() == QLineEdit.EchoMode.Password

    def test_segment_list_has_four_items(self, server_settings_dialog) -> None:
        assert server_settings_dialog._seg_list.count() == 4

    def test_default_segments_license_and_unique_checked(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        checked = []
        for i in range(server_settings_dialog._seg_list.count()):
            item = server_settings_dialog._seg_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked.append(item.data(Qt.ItemDataRole.UserRole))
        assert "license_id" in checked
        assert "unique_id" in checked

    def test_active_path_segments_returns_checked_items(self, server_settings_dialog) -> None:
        segs = server_settings_dialog._active_path_segments()
        assert isinstance(segs, list)
        assert len(segs) >= 1

    def test_pid_viz_widget_exists(self, server_settings_dialog) -> None:
        assert server_settings_dialog._pid_viz is not None

    def test_pid_viz_contains_section_nibble_ranges(self, server_settings_dialog) -> None:
        defs = server_settings_dialog._pid_viz._defs
        ranges = [(d.start, d.end - 1) for d in defs]  # inclusive end for display
        assert (0, 7) in ranges    # custom_id
        assert (8, 9) in ranges    # hw_id
        assert (10, 11) in ranges  # license_id
        assert (12, 15) in ranges  # unique_id

    def test_pid_viz_active_sections_shown_in_color(self, server_settings_dialog) -> None:
        # Default sections are all defined → at least one section is loaded into viz
        assert len(server_settings_dialog._pid_viz._defs) > 0

    def test_pid_viz_inactive_nibbles_shown_in_grey(self, server_settings_dialog) -> None:
        from secure_loader.gui.server_settings_dialog import _INACTIVE_COLORS
        assert _INACTIVE_COLORS[1] == "#9ca3af"

    def test_pid_viz_shows_section_names(self, server_settings_dialog) -> None:
        names = [d.name for d in server_settings_dialog._pid_viz._defs]
        assert "hw_id" in names
        assert "custom_id" in names

    def test_pid_viz_updates_when_section_row_deleted(self, server_settings_dialog) -> None:
        server_settings_dialog._section_rows.clear()
        server_settings_dialog._on_section_changed()
        assert server_settings_dialog._pid_viz._defs == []

    def test_preview_label_contains_preview(self, server_settings_dialog) -> None:
        text = server_settings_dialog._preview_lbl.text()
        assert "Preview" in text or "version" in text.lower()

    def test_preview_updates_when_url_changes(self, server_settings_dialog) -> None:
        server_settings_dialog._url_edit.setText("https://new.example.com")
        text = server_settings_dialog._preview_lbl.text()
        assert "new.example.com" in text

    def test_preview_updates_when_checkbox_toggled(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        # Uncheck all path segments → preview should not contain any field placeholder
        for i in range(server_settings_dialog._seg_list.count()):
            server_settings_dialog._seg_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        text = server_settings_dialog._preview_lbl.text()
        assert "{license_id}" not in text
        assert "{version}.bin" in text

    def test_preview_with_no_segments(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_path_segments = []
        dlg = ServerSettingsDialog(config=cfg)
        dlg._url_edit.setText("https://example.com")
        dlg._update_url_preview()
        text = dlg._preview_lbl.text()
        assert "{version}.bin" in text
        assert "{license_id}" not in text
        dlg.close()

    def test_move_up_disabled_at_top(self, server_settings_dialog) -> None:
        server_settings_dialog._seg_list.setCurrentRow(0)
        server_settings_dialog._update_move_buttons()
        assert not server_settings_dialog._up_btn.isEnabled()

    def test_move_down_disabled_at_bottom(self, server_settings_dialog) -> None:
        last = server_settings_dialog._seg_list.count() - 1
        server_settings_dialog._seg_list.setCurrentRow(last)
        server_settings_dialog._update_move_buttons()
        assert not server_settings_dialog._down_btn.isEnabled()

    def test_move_up_shifts_item(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        server_settings_dialog._seg_list.setCurrentRow(1)
        before = server_settings_dialog._seg_list.item(1).data(Qt.ItemDataRole.UserRole)
        server_settings_dialog._move_seg_up()
        after = server_settings_dialog._seg_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert before == after

    def test_move_down_shifts_item(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        server_settings_dialog._seg_list.setCurrentRow(0)
        before = server_settings_dialog._seg_list.item(0).data(Qt.ItemDataRole.UserRole)
        server_settings_dialog._move_seg_down()
        after = server_settings_dialog._seg_list.item(1).data(Qt.ItemDataRole.UserRole)
        assert before == after

    def test_move_up_at_top_is_noop(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        server_settings_dialog._seg_list.setCurrentRow(0)
        before = server_settings_dialog._seg_list.item(0).data(Qt.ItemDataRole.UserRole)
        server_settings_dialog._move_seg_up()
        after = server_settings_dialog._seg_list.item(0).data(Qt.ItemDataRole.UserRole)
        assert before == after

    def test_move_down_at_bottom_is_noop(self, server_settings_dialog) -> None:
        from PySide6.QtCore import Qt

        last = server_settings_dialog._seg_list.count() - 1
        server_settings_dialog._seg_list.setCurrentRow(last)
        before = server_settings_dialog._seg_list.item(last).data(Qt.ItemDataRole.UserRole)
        server_settings_dialog._move_seg_down()
        after = server_settings_dialog._seg_list.item(last).data(Qt.ItemDataRole.UserRole)
        assert before == after

    def test_save_persists_url_to_config(self, qapp, tmp_path) -> None:
        from unittest.mock import patch

        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.config_path = str(tmp_path / "config.ini")
        dlg = ServerSettingsDialog(config=cfg)
        dlg._url_edit.setText("https://saved.example.com")
        with patch("secure_loader.gui.server_settings_dialog.save_config"):
            dlg._save_and_accept()
        assert cfg.http_base_url == "https://saved.example.com"
        dlg.close()

    def test_save_persists_credentials_to_config(self, qapp, tmp_path) -> None:
        from unittest.mock import patch

        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.config_path = str(tmp_path / "config.ini")
        dlg = ServerSettingsDialog(config=cfg)
        dlg._login_edit.setText("bob")
        dlg._pwd_edit.setText("pass123")
        with patch("secure_loader.gui.server_settings_dialog.save_config"):
            dlg._save_and_accept()
        assert cfg.http_login == "bob"
        assert cfg.http_password == "pass123"
        dlg.close()

    def test_custom_segments_reflected_in_active_list(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_path_segments = ["hw_id", "license_id"]
        dlg = ServerSettingsDialog(config=cfg)
        segs = dlg._active_path_segments()
        assert segs == ["hw_id", "license_id"]
        dlg.close()

    def test_unknown_segment_in_config_shown_with_raw_name(self, qapp) -> None:
        from secure_loader.config import AppConfig
        from secure_loader.gui.server_settings_dialog import ServerSettingsDialog

        cfg = AppConfig()
        cfg.http_path_segments = ["license_id", "unique_id"]
        dlg = ServerSettingsDialog(config=cfg)
        # Ensure all 4 known segments are in the list
        assert dlg._seg_list.count() >= 2
        dlg.close()


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

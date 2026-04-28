"""Main window.

Grid layout: left column — labels; center column — editable displays and
progress bars; right column — action buttons.

All business logic is delegated to the core and the workers in
:mod:`.workers`; this module is just widget wiring.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports

from .. import __app_name__, __version__
from ..config import AppConfig, load_config, save_config
from ..core.firmware import FirmwareHeader
from ..core.protocol import DeviceInfo, Parity, State
from ..core.sources import FirmwareIdentifier
from ..core.sources.http import HttpFirmwareSource
from ..core.updater import check_device_matches_firmware
from ..i18n import _, get_language, set_language
from .login_dialog import LoginDialog
from .workers import DownloadWorker, ProtocolWorker, read_firmware_file, start_in_thread

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

ERROR_STYLE = "QLineEdit{border: 2px solid red}"

_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("it", "Italiano"),
    ("pl", "Polski"),
]


class MainWindow(QMainWindow):
    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self._config = config or load_config()

        self._protocol_worker: ProtocolWorker | None = None
        self._protocol_thread: QThread | None = None
        self._download_thread: QThread | None = None

        self._firmware_header: FirmwareHeader | None = None
        self._firmware_bytes: bytes = b""
        self._device_info: DeviceInfo | None = None
        self._is_connected: bool = False
        self._current_state: State = State.IDLE
        self._compat_ok: bool = False

        self.setWindowTitle(__app_name__)
        self._set_window_icon()
        self._build_ui()
        self._build_menu()
        self._populate_ports()
        self._update_download_button()

        # Explicitly load the last-used firmware file — addItem on an editable
        # QComboBox does not reliably trigger currentTextChanged at startup.
        initial_path: str = self.input_file_box.itemData(0) or ""
        if initial_path:
            self._on_input_file_changed(initial_path)

    # --------------------------------------------------------------- UI setup

    def _set_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parent / "resources" / "icons" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        grid = QGridLayout(central)

        # ----- Row 0: Port | portBox | Baud
        self._lbl_port = QLabel(_("Port"))
        grid.addWidget(self._lbl_port, 0, 0)
        self.port_box = QComboBox()
        self.port_box.currentIndexChanged.connect(self._on_port_changed)
        grid.addWidget(self.port_box, 0, 1)
        baud_layout = QHBoxLayout()
        self._lbl_baud = QLabel(
            _("Baud"), alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        baud_layout.addWidget(self._lbl_baud)
        self.baud_box = QComboBox()
        self.baud_box.addItems(
            [
                "1200",
                "2400",
                "4800",
                "9600",
                "19200",
                "38400",
                "57600",
                "115200",
                "230400",
                "460800",
                "921600",
            ]
        )
        self.baud_box.setCurrentText("115200")
        self.baud_box.currentIndexChanged.connect(self._on_port_changed)
        baud_layout.addWidget(self.baud_box)
        grid.addLayout(baud_layout, 0, 3)

        # ----- Row 1: Status | statusEdit | Parity
        self._lbl_status = QLabel(_("Status"))
        grid.addWidget(self._lbl_status, 1, 0)
        self.status_edit = QLineEdit()
        self.status_edit.setEnabled(False)
        grid.addWidget(self.status_edit, 1, 1)
        parity_layout = QHBoxLayout()
        self._lbl_parity = QLabel(
            _("Parity"), alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        parity_layout.addWidget(self._lbl_parity)
        self.parity_box = QComboBox()
        self.parity_box.addItems(["None", "Odd", "Even"])
        self.parity_box.currentIndexChanged.connect(self._on_port_changed)
        parity_layout.addWidget(self.parity_box)
        grid.addLayout(parity_layout, 1, 3)

        # ----- Row 2: Device Product ID | Stop bits
        self._lbl_dev_product_id = QLabel(_("Product ID"))
        grid.addWidget(self._lbl_dev_product_id, 2, 0)
        self.dev_product_id_edit = QLineEdit()
        self.dev_product_id_edit.setEnabled(False)
        grid.addWidget(self.dev_product_id_edit, 2, 1)
        stopbits_layout = QHBoxLayout()
        self._lbl_stopbits = QLabel(
            _("Stop bits"), alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        stopbits_layout.addWidget(self._lbl_stopbits)
        self.stopbits_box = QComboBox()
        self.stopbits_box.addItems(["1", "1.5", "2"])
        self.stopbits_box.currentIndexChanged.connect(self._on_port_changed)
        stopbits_layout.addWidget(self.stopbits_box)
        grid.addLayout(stopbits_layout, 2, 3)

        # ----- Row 3: Bootloader Version | Connect + Refresh
        self._lbl_bootloader = QLabel(_("Bootloader Version"))
        grid.addWidget(self._lbl_bootloader, 3, 0)
        self.bootloader_edit = QLineEdit()
        self.bootloader_edit.setEnabled(False)
        grid.addWidget(self.bootloader_edit, 3, 1)
        btn_layout = QHBoxLayout()
        self.connect_button = QPushButton(_("Connect"))
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.refresh_button = QPushButton(_("Refresh ports"))
        self.refresh_button.clicked.connect(self._populate_ports)
        btn_layout.addWidget(self.connect_button)
        btn_layout.addWidget(self.refresh_button)
        grid.addLayout(btn_layout, 3, 3)

        # ----- Row 4: separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        grid.addWidget(line, 4, 0, 1, 4)

        # ----- Row 5: Firmware file selector
        self._lbl_firmware_file = QLabel(_("Firmware file"))
        grid.addWidget(self._lbl_firmware_file, 5, 0)
        self.input_file_box = QComboBox()
        self.input_file_box.setEditable(True)
        # currentTextChanged handles paths typed directly into the line edit.
        self.input_file_box.currentTextChanged.connect(self._on_input_file_changed)
        # activated fires even when the user re-selects the already-displayed item
        # (currentTextChanged is silent in that case — no text change, no signal).
        self.input_file_box.activated.connect(self._on_file_combo_activated)
        # Block signals while populating — currentTextChanged would fire during
        # addItem (editable QComboBox updates the line edit on first insert) but
        # widgets created later in _build_ui (e.g. protocol_edit) don't exist yet.
        self.input_file_box.blockSignals(True)
        for p in self._config.last_firmware_paths:
            self._add_file_combo_item(p)
        self.input_file_box.blockSignals(False)
        grid.addWidget(self.input_file_box, 5, 1)
        self.input_file_button = QPushButton(_("Select file..."))
        self.input_file_button.clicked.connect(self._on_select_file_clicked)
        grid.addWidget(self.input_file_button, 5, 3)

        # ----- Row 6: HTTP download progress | "Fetch from server"
        self._lbl_firmware_dl = QLabel(_("Firmware download"))
        grid.addWidget(self._lbl_firmware_dl, 6, 0)
        self.http_progress = QProgressBar()
        grid.addWidget(self.http_progress, 6, 1)
        self.get_firmware_button = QPushButton(_("Fetch from server"))
        self.get_firmware_button.clicked.connect(lambda: self._start_fetch(previous=False))
        self.get_firmware_button.setEnabled(False)
        grid.addWidget(self.get_firmware_button, 6, 3)

        # ----- Row 7: Product ID (from file)
        self._lbl_product_id = QLabel(_("Product ID"))
        grid.addWidget(self._lbl_product_id, 7, 0)
        self.product_id_edit = QLineEdit()
        self.product_id_edit.setEnabled(False)
        grid.addWidget(self.product_id_edit, 7, 1)

        # ----- Row 8: App Version
        self._lbl_app_version = QLabel(_("App Version"))
        grid.addWidget(self._lbl_app_version, 8, 0)
        self.app_version_edit = QLineEdit()
        self.app_version_edit.setEnabled(False)
        grid.addWidget(self.app_version_edit, 8, 1)

        # ----- Row 9: Previous App Version + "Get Previous Firmware"
        self._lbl_prev_app_version = QLabel(_("Previous App Ver."))
        grid.addWidget(self._lbl_prev_app_version, 9, 0)
        self.prev_app_version_edit = QLineEdit()
        self.prev_app_version_edit.setEnabled(False)
        grid.addWidget(self.prev_app_version_edit, 9, 1)
        self.get_prev_firmware_button = QPushButton(_("Get Previous Firmware"))
        self.get_prev_firmware_button.clicked.connect(lambda: self._start_fetch(previous=True))
        self.get_prev_firmware_button.setEnabled(False)
        grid.addWidget(self.get_prev_firmware_button, 9, 3)

        # ----- Row 11: Protocol
        self._lbl_protocol = QLabel(_("Protocol"))
        grid.addWidget(self._lbl_protocol, 11, 0)
        self.protocol_edit = QLineEdit()
        self.protocol_edit.setEnabled(False)
        grid.addWidget(self.protocol_edit, 11, 1)

        # ----- Row 12: File size | Update button
        self._lbl_file_size = QLabel(_("File Size"))
        grid.addWidget(self._lbl_file_size, 12, 0)
        self.size_edit = QLineEdit()
        self.size_edit.setEnabled(False)
        grid.addWidget(self.size_edit, 12, 1)
        self.download_button = QPushButton(_("Update"))
        self.download_button.setEnabled(False)
        self.download_button.setMinimumHeight(56)
        self.download_button.clicked.connect(self._on_update_clicked)
        grid.addWidget(self.download_button, 12, 3, 2, 1)

        # ----- Row 13: Update progress
        self._lbl_update_progress = QLabel(_("Update progress"))
        grid.addWidget(self._lbl_update_progress, 13, 0)
        self.download_progress = QProgressBar()
        grid.addWidget(self.download_progress, 13, 1)

        # ----- Row 14: separator before transfer section
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        grid.addWidget(line2, 14, 0, 1, 4)

        # ----- Trailing vertical spacer
        grid.setRowStretch(19, 1)

        self.statusBar()

    def _build_menu(self) -> None:
        self._menu_help = self.menuBar().addMenu(_("&Help"))
        self._act_instr = QAction(_("Update instruction..."), self)
        self._act_instr.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl(self._config.update_instruction_url))
        )
        self._act_instr.setVisible(bool(self._config.update_instruction_url))
        self._menu_help.addAction(self._act_instr)
        self._menu_help.addSeparator()

        self._act_about = QAction(_("&About..."), self)
        self._act_about.triggered.connect(self._show_about)
        self._menu_help.addAction(self._act_about)

        self._act_version = QAction(_("Version info"), self)
        self._act_version.triggered.connect(
            lambda: QMessageBox.information(
                self, __app_name__, _("Version {version}", version=__version__)
            )
        )
        self._menu_help.addAction(self._act_version)

        self._menu_lang = self.menuBar().addMenu(_("Language"))
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        for code, label in _LANGUAGES:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(code == get_language())
            act.triggered.connect(lambda checked, c=code: self._on_language_changed(c))
            lang_group.addAction(act)
            self._menu_lang.addAction(act)
            self._lang_actions[code] = act

        self._menu_cred = self.menuBar().addMenu(_("Credentials"))
        self._act_login = QAction(_("Set login and password"), self)
        self._act_login.triggered.connect(self._open_login_dialog)
        self._menu_cred.addAction(self._act_login)

    def _show_about(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(_("About {name}", name=__app_name__))
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dlg.setMinimumWidth(620)

        root = QVBoxLayout(dlg)
        root.setSpacing(14)
        root.setContentsMargins(24, 20, 24, 16)

        # --- top row: icon left | text right
        top = QHBoxLayout()
        top.setSpacing(24)
        top.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_path = Path(__file__).resolve().parent / "resources" / "icons" / "SecureLoader.png"
        if icon_path.exists():
            pix = QPixmap(str(icon_path)).scaledToHeight(
                190, Qt.TransformationMode.SmoothTransformation
            )
            icon_lbl = QLabel(alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            icon_lbl.setPixmap(pix)
            icon_lbl.setFixedWidth(pix.width())
            top.addWidget(icon_lbl)

        right = QVBoxLayout()
        right.setSpacing(10)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        repo_url = "https://github.com/niwciu/SecureLoader"
        name_lbl = QLabel(
            f'<h2 style="margin:0;">'
            f'<a href="{repo_url}" style="text-decoration:none;">{__app_name__}</a>'
            f"</h2>"
        )
        name_lbl.setOpenExternalLinks(True)
        right.addWidget(name_lbl)

        creator_url = "https://github.com/niwciu/EncryptBIN"
        desc_lbl = QLabel(
            f"Flashes encrypted <code>.bin</code> firmware to embedded devices "
            f"over a serial connection.<br><br>"
            f"Firmware files are created with "
            f'<a href="{creator_url}"><b>EncryptBIN</b></a> — '
            f"a companion tool that produces AES&#8209;128&nbsp;CBC encrypted binaries "
            f"compatible with Tiny&#8209;AES&#8209;C bootloaders."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setOpenExternalLinks(True)
        right.addWidget(desc_lbl)

        sep_inner = QFrame()
        sep_inner.setFrameShape(QFrame.Shape.HLine)
        sep_inner.setFrameShadow(QFrame.Shadow.Sunken)
        right.addWidget(sep_inner)

        meta_grid = QGridLayout()
        meta_grid.setHorizontalSpacing(12)
        meta_grid.setVerticalSpacing(5)

        def _row(label: str, value: str, row: int, link: str | None = None) -> None:
            lbl = QLabel(f"<b>{label}</b>")
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if link:
                val = QLabel(f'<a href="{link}">{value}</a>')
                val.setOpenExternalLinks(True)
            else:
                val = QLabel(value)
            meta_grid.addWidget(lbl, row, 0)
            meta_grid.addWidget(val, row, 1)

        _row("Version", __version__, 0)
        _row("Author", "niwciu", 1)
        _row("GitHub", "github.com/niwciu", 2, "https://github.com/niwciu")
        _row("Email", "niwciu@gmail.com", 3, "mailto:niwciu@gmail.com")

        right.addLayout(meta_grid)
        right.addStretch()
        top.addLayout(right, stretch=1)
        root.addLayout(top)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.accept)
        root.addWidget(buttons)

        dlg.adjustSize()
        dlg.exec()

    def _open_login_dialog(self) -> None:
        dialog = LoginDialog(self._config, parent=self)
        dialog.exec()

    # ------------------------------------------------------ language switching

    def _on_language_changed(self, code: str) -> None:
        set_language(code)
        self._config.language = code
        save_config(self._config)
        for c, act in self._lang_actions.items():
            act.setChecked(c == code)
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        # Labels
        self._lbl_port.setText(_("Port"))
        self._lbl_baud.setText(_("Baud"))
        self._lbl_status.setText(_("Status"))
        self._lbl_parity.setText(_("Parity"))
        self._lbl_dev_product_id.setText(_("Product ID"))
        self._lbl_stopbits.setText(_("Stop bits"))
        self._lbl_bootloader.setText(_("Bootloader Version"))
        self._lbl_firmware_file.setText(_("Firmware file"))
        self._lbl_firmware_dl.setText(_("Firmware download"))
        self._lbl_product_id.setText(_("Product ID"))
        self._lbl_app_version.setText(_("App Version"))
        self._lbl_prev_app_version.setText(_("Previous App Ver."))
        self._lbl_protocol.setText(_("Protocol"))
        self._lbl_file_size.setText(_("File Size"))
        self._lbl_update_progress.setText(_("Update progress"))
        # Buttons
        self.connect_button.setText(_("Disconnect") if self._is_connected else _("Connect"))
        self.refresh_button.setText(_("Refresh ports"))
        self.input_file_button.setText(_("Select file..."))
        self.get_firmware_button.setText(_("Fetch from server"))
        self.get_prev_firmware_button.setText(_("Get Previous Firmware"))
        self.download_button.setText(_("Update"))
        # Menus
        self._menu_help.setTitle(_("&Help"))
        self._menu_lang.setTitle(_("Language"))
        self._menu_cred.setTitle(_("Credentials"))
        # Menu actions
        self._act_instr.setText(_("Update instruction..."))
        self._act_about.setText(_("&About..."))
        self._act_version.setText(_("Version info"))
        self._act_login.setText(_("Set login and password"))
        # Re-apply current status text
        self._update_status_text(self._current_state)

    # -------------------------------------------------------- port management

    def _populate_ports(self) -> None:
        previous = self.port_box.currentData()
        self.port_box.blockSignals(True)
        self.port_box.clear()
        for info in sorted(list_ports.comports(), key=lambda p: p.device):
            title = f"{info.device}: ({info.description or ''}) {info.manufacturer or ''}"
            self.port_box.addItem(title, userData=info.device)
            if info.device == previous:
                self.port_box.setCurrentIndex(self.port_box.count() - 1)
        self.port_box.blockSignals(False)

    def _current_port(self) -> str | None:
        data = self.port_box.currentData()
        return str(data) if data is not None else None

    def _current_baudrate(self) -> int:
        return int(self.baud_box.currentText())

    def _current_parity(self) -> Parity:
        return Parity.from_label(self.parity_box.currentText())

    def _current_stopbits(self) -> float:
        return float(self.stopbits_box.currentText())

    # ------------------------------------------------------ connect / disconnect

    def _on_connect_clicked(self) -> None:
        if self._is_connected:
            self._disconnect_serial()
        else:
            self._connect_serial()

    def _on_port_changed(self, _index: int) -> None:
        if self._is_connected:
            self._disconnect_serial()

    def _connect_serial(self) -> None:
        port = self._current_port()
        if not port:
            QMessageBox.warning(self, __app_name__, _("No serial ports found."))
            return
        self._protocol_worker = ProtocolWorker(
            port=port,
            parity=self._current_parity(),
            baudrate=self._current_baudrate(),
            stopbits=self._current_stopbits(),
        )
        self._protocol_worker.state_changed.connect(self._on_state_changed)
        self._protocol_worker.device_info.connect(self._on_device_info)
        self._protocol_worker.error_occurred.connect(self._on_protocol_error)
        self._protocol_worker.page_sent.connect(self._on_page_sent)
        self._protocol_worker.download_done.connect(self._on_download_done)
        self._protocol_worker.finished.connect(self._on_protocol_finished)
        self._protocol_thread = start_in_thread(self._protocol_worker, parent=self)
        self._is_connected = True
        self.connect_button.setText(_("Disconnect"))

    def _disconnect_serial(self) -> None:
        if self._protocol_worker is not None:
            self._protocol_worker.stop()
        self._is_connected = False
        self.connect_button.setText(_("Connect"))
        self._clear_device_info()

    # -------------------------------------------------------- protocol signals

    def _update_status_text(self, state: State) -> None:
        mapping = {
            State.IDLE: _("Idle"),
            State.CONNECTING: _("Connecting"),
            State.CONNECTED: _("Connected"),
            State.STARTING: _("Download"),
            State.SENDING: _("Download"),
        }
        self.status_edit.setText(mapping.get(state, state.name))

    def _on_state_changed(self, state: State) -> None:
        self._current_state = state
        self._update_status_text(state)
        if state in (State.IDLE, State.CONNECTING):
            self._clear_device_info()

    def _on_device_info(self, info: DeviceInfo) -> None:
        self._device_info = info
        self.dev_product_id_edit.setText(info.format_product_id())
        self.bootloader_edit.setText(info.format_bootloader_version())
        self._refresh_compatibility_indicator()
        self._update_download_button()

    def _on_protocol_error(self, msg: str) -> None:
        QMessageBox.critical(self, __app_name__, msg)
        self._disconnect_serial()

    def _on_protocol_finished(self) -> None:
        self._protocol_worker = None
        self._protocol_thread = None

    def _on_page_sent(self, sent: int, total: int) -> None:
        self.download_progress.setMaximum(max(total, 1))
        self.download_progress.setValue(sent)

    def _on_download_done(self) -> None:
        QMessageBox.information(self, __app_name__, _("Update completed successfully"))

    # ---------------------------------------------------------- firmware file

    def _add_file_combo_item(self, full_path: str, position: int | None = None) -> None:
        """Insert a combobox entry showing only the filename; full path stored as item data."""
        display = Path(full_path).name
        if position is None:
            self.input_file_box.addItem(display, full_path)
            item_idx = self.input_file_box.count() - 1
        else:
            self.input_file_box.insertItem(position, display, full_path)
            item_idx = position
        self.input_file_box.setItemData(item_idx, full_path, Qt.ItemDataRole.ToolTipRole)

    def _on_file_combo_activated(self, idx: int) -> None:
        """Handle dropdown selection — retrieve full path from item data."""
        full_path: str = self.input_file_box.itemData(idx) or ""
        if full_path:
            self._on_input_file_changed(full_path)

    def _on_select_file_clicked(self) -> None:
        start_dir = ""
        if self._config.last_firmware_paths:
            start_dir = str(Path(self._config.last_firmware_paths[0]).parent)
        name, _filter = QFileDialog.getOpenFileName(
            self,
            _("Select file..."),
            start_dir,
            "Binary Files (*.bin);;All Files (*)",
        )
        if not name:
            return
        self._remember_recent(name)
        self.input_file_box.blockSignals(True)
        idx = self.input_file_box.findData(name)
        if idx >= 0:
            self.input_file_box.removeItem(idx)
        self._add_file_combo_item(name, position=0)
        self.input_file_box.setCurrentIndex(0)
        self.input_file_box.blockSignals(False)
        self._on_input_file_changed(name)

    def _on_input_file_changed(self, path: str) -> None:
        if not path:
            self._clear_firmware_info()
            return
        # currentTextChanged fires with the item's display text (filename only)
        # when the user picks from the dropdown.  Those strings are not loadable
        # paths — the full path comes via _on_file_combo_activated / itemData.
        if not Path(path).is_absolute():
            return
        self.input_file_box.setToolTip(path)
        try:
            header, data = read_firmware_file(path)
        except OSError as e:
            QMessageBox.warning(
                self,
                __app_name__,
                _("Cannot read file {path}: {err}", path=path, err=e.strerror or str(e)),
            )
            self._clear_firmware_info()
            return
        except Exception as e:
            QMessageBox.critical(self, __app_name__, str(e))
            self._clear_firmware_info()
            return
        self._load_firmware_into_ui(header, data)
        self._remember_recent(path)

    def _load_firmware_into_ui(self, header: FirmwareHeader, data: bytes) -> None:
        self._firmware_header = header
        self._firmware_bytes = data
        self.protocol_edit.setText(header.format_protocol_version())
        self.product_id_edit.setText(header.format_product_id())
        self.app_version_edit.setText(header.format_app_version())
        self.prev_app_version_edit.setText(header.format_prev_app_version())
        self.size_edit.setText(str(header.payload_size))
        self._refresh_compatibility_indicator()
        self._update_download_button()

    def _clear_firmware_info(self) -> None:
        self._firmware_header = None
        self._firmware_bytes = b""
        for edit in (
            self.protocol_edit,
            self.product_id_edit,
            self.app_version_edit,
            self.prev_app_version_edit,
            self.size_edit,
        ):
            edit.setText("")
        self._refresh_compatibility_indicator()
        self._update_download_button()

    def _clear_device_info(self) -> None:
        self._device_info = None
        self.dev_product_id_edit.setText("")
        self.bootloader_edit.setText("")
        self._refresh_compatibility_indicator()
        self._update_download_button()

    def _remember_recent(self, path: str) -> None:
        recent = [path] + [p for p in self._config.last_firmware_paths if p != path]
        self._config.last_firmware_paths = recent[:10]
        save_config(self._config)

    # ---------------------------------------------------------- HTTP download

    def _start_fetch(self, *, previous: bool) -> None:
        if self._device_info is None:
            QMessageBox.warning(
                self, __app_name__, _("Device must be connected before downloading.")
            )
            return
        license_id = self._device_info.format_product_id()[6:8]
        unique_id = self._device_info.format_product_id()[14:18]
        prev_version: str | None = None
        if previous:
            if self._firmware_header is None:
                QMessageBox.warning(
                    self, __app_name__, _("Previous version requires a firmware file loaded.")
                )
                return
            prev_version = self._firmware_header.format_prev_app_version()

        source = HttpFirmwareSource(
            base_url=self._config.http_base_url,
            credentials=self._config.credentials(),
        )
        identifier = FirmwareIdentifier(
            license_id=license_id, unique_id=unique_id, app_version=prev_version
        )
        worker = DownloadWorker(source, identifier, previous=previous)
        worker.progress.connect(self._on_http_progress)
        worker.finished.connect(self._on_fetch_finished)
        worker.error_occurred.connect(self._on_fetch_error)
        self._download_thread = start_in_thread(worker, parent=self)

    def _on_http_progress(self, received: int, total: int) -> None:
        self.http_progress.setMaximum(max(total, 1))
        self.http_progress.setValue(received)

    def _on_fetch_finished(self, data: bytes, header: object) -> None:
        if header is None:
            QMessageBox.warning(
                self,
                __app_name__,
                _("Downloaded file is not a valid firmware image."),
            )
            return
        if not isinstance(header, FirmwareHeader):
            return
        self._load_firmware_into_ui(header, data)
        QMessageBox.information(
            self,
            __app_name__,
            _("Firmware download from server completed"),
        )

    def _on_fetch_error(self, msg: str) -> None:
        self.http_progress.setValue(0)
        self._clear_firmware_info()
        QMessageBox.critical(self, _("Server connection problem"), msg)

    # -------------------------------------------------------------- update

    def _on_update_clicked(self) -> None:
        if self._protocol_worker is None or not self._firmware_bytes:
            return
        self.download_progress.setValue(1)
        self._protocol_worker.start_download(self._firmware_bytes)

    # --------------------------------------------------------- UI state logic

    def _refresh_compatibility_indicator(self) -> None:
        has_both = self._device_info is not None and self._firmware_header is not None
        ok = True
        if has_both:
            reason = check_device_matches_firmware(
                self._device_info, self._firmware_header  # type: ignore[arg-type]
            )
            ok = not bool(reason)
            self.protocol_edit.setStyleSheet(ERROR_STYLE if reason.bootloader_mismatch else "")
            self.bootloader_edit.setStyleSheet(ERROR_STYLE if reason.bootloader_mismatch else "")
            self.product_id_edit.setStyleSheet(ERROR_STYLE if reason.product_mismatch else "")
            self.dev_product_id_edit.setStyleSheet(ERROR_STYLE if reason.product_mismatch else "")
        else:
            for e in (
                self.protocol_edit,
                self.bootloader_edit,
                self.product_id_edit,
                self.dev_product_id_edit,
            ):
                e.setStyleSheet("")
        self._compat_ok = ok and has_both

    def _update_download_button(self) -> None:
        compat_ok = self._compat_ok
        self.download_button.setEnabled(compat_ok and bool(self._firmware_bytes))
        self.get_firmware_button.setEnabled(self._device_info is not None)
        self.get_prev_firmware_button.setEnabled(
            self._firmware_header is not None and self._device_info is not None
        )

    # --------------------------------------------------------------- teardown

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._protocol_worker is not None:
            self._protocol_worker.stop()
        if self._protocol_thread is not None:
            self._protocol_thread.quit()
            self._protocol_thread.wait(2000)
        if self._download_thread is not None:
            self._download_thread.quit()
            self._download_thread.wait(2000)
        super().closeEvent(event)

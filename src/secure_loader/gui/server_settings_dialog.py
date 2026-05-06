"""Dialog for configuring server URL, credentials, and URL path structure."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, save_config
from ..i18n import _

_SEGMENT_DEFS: list[tuple[str, str]] = [
    ("Custom (bytes 0-3)", "custom_id"),
    ("HW ID (byte 4)", "hw_id"),
    ("License ID (byte 5)", "license_id"),
    ("Unique ID (bytes 6-7)", "unique_id"),
]
"""(display label, FirmwareIdentifier field name) for each product-ID slice."""

# Fixed order matches the 64-bit productId hex layout: chars [0:8][8:10][10:12][12:16]
_PID_VIZ: list[tuple[str, str, str, str]] = [
    ("AABBCCDD", "custom_id", "custom", "B 0-3"),
    ("11", "hw_id", "hw_id", "B 4"),
    ("22", "license_id", "license", "B 5"),
    ("3344", "unique_id", "unique", "B 6-7"),
]
"""(hex placeholder, field_name, short label, byte description) for the PID strip."""


class ServerSettingsDialog(QDialog):
    """Settings dialog for server URL, HTTP credentials, and URL path structure."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(_("Server settings"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setMinimumWidth(520)
        self._build_ui()
        self._populate()
        root_layout = self.layout()
        assert root_layout is not None
        root_layout.activate()
        sh = root_layout.sizeHint()
        self.resize(max(self.minimumWidth(), sh.width()), sh.height())

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 14, 16, 12)

        # ---- Server URL
        url_box = QGroupBox(_("Server"))
        url_form = QHBoxLayout(url_box)
        url_form.addWidget(QLabel(_("Base URL")))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/firmware")
        self._url_edit.textChanged.connect(self._update_preview)
        url_form.addWidget(self._url_edit, stretch=1)
        root.addWidget(url_box)

        # ---- Credentials
        cred_box = QGroupBox(_("Credentials"))
        cred_box.setCheckable(True)
        cred_box.setChecked(False)
        self._cred_box = cred_box
        cred_layout = QVBoxLayout(cred_box)
        login_row = QHBoxLayout()
        login_row.addWidget(QLabel(_("Login")))
        self._login_edit = QLineEdit()
        login_row.addWidget(self._login_edit, stretch=1)
        cred_layout.addLayout(login_row)

        pwd_row = QHBoxLayout()
        pwd_row.addWidget(QLabel(_("Password")))
        self._pwd_edit = QLineEdit()
        self._pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_row.addWidget(self._pwd_edit, stretch=1)
        self._show_btn = QPushButton(_("Show"))
        self._show_btn.setCheckable(True)
        self._show_btn.toggled.connect(self._toggle_password)
        pwd_row.addWidget(self._show_btn)
        cred_layout.addLayout(pwd_row)
        root.addWidget(cred_box)

        # ---- URL path structure
        path_box = QGroupBox(_("URL path structure"))
        path_layout = QVBoxLayout(path_box)

        hint = QLabel(_("Select and order the product-ID fields used in the download URL path."))
        hint.setWordWrap(True)
        path_layout.addWidget(hint)

        # Product ID hex strip visualisation
        self._pid_viz_lbl = QLabel()
        self._pid_viz_lbl.setTextFormat(Qt.TextFormat.RichText)
        path_layout.addWidget(self._pid_viz_lbl)

        list_row = QHBoxLayout()
        self._seg_list = QListWidget()
        self._seg_list.currentRowChanged.connect(self._update_move_buttons)
        self._seg_list.itemChanged.connect(self._refresh_display)
        list_row.addWidget(self._seg_list, stretch=1)

        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._up_btn = QPushButton(_("↑  Up"))
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn = QPushButton(_("↓  Down"))
        self._down_btn.clicked.connect(self._move_down)
        btn_col.addWidget(self._up_btn)
        btn_col.addWidget(self._down_btn)
        list_row.addLayout(btn_col)
        path_layout.addLayout(list_row)

        self._preview_lbl = QLabel()
        self._preview_lbl.setWordWrap(True)
        path_layout.addWidget(self._preview_lbl)
        root.addWidget(path_box)

        # ---- OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ---------------------------------------------------------------- populate

    def _populate(self) -> None:
        self._url_edit.setText(self._config.http_base_url)
        self._cred_box.setChecked(self._config.http_use_credentials)
        self._login_edit.setText(self._config.http_login)
        self._pwd_edit.setText(self._config.http_password)
        self._populate_segments(self._config.http_path_segments)
        self._refresh_display()
        self._update_move_buttons()

    def _populate_segments(self, active: list[str]) -> None:
        """Fill the list widget: active segments first (in config order), rest at end."""
        self._seg_list.blockSignals(True)
        self._seg_list.clear()
        shown: set[str] = set()
        for field_name in active:
            label = next((lbl for lbl, fn in _SEGMENT_DEFS if fn == field_name), field_name)
            self._add_segment_item(label, field_name, checked=True)
            shown.add(field_name)
        for label, field_name in _SEGMENT_DEFS:
            if field_name not in shown:
                self._add_segment_item(label, field_name, checked=False)
        self._seg_list.blockSignals(False)

    def _add_segment_item(self, label: str, field_name: str, *, checked: bool) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, field_name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._seg_list.addItem(item)

    # --------------------------------------------------------- segment controls

    def _move_up(self) -> None:
        row = self._seg_list.currentRow()
        if row <= 0:
            return
        item = self._seg_list.takeItem(row)
        self._seg_list.insertItem(row - 1, item)
        self._seg_list.setCurrentRow(row - 1)
        self._refresh_display()

    def _move_down(self) -> None:
        row = self._seg_list.currentRow()
        if row < 0 or row >= self._seg_list.count() - 1:
            return
        item = self._seg_list.takeItem(row)
        self._seg_list.insertItem(row + 1, item)
        self._seg_list.setCurrentRow(row + 1)
        self._refresh_display()

    def _update_move_buttons(self) -> None:
        row = self._seg_list.currentRow()
        count = self._seg_list.count()
        self._up_btn.setEnabled(row > 0)
        self._down_btn.setEnabled(0 <= row < count - 1)

    def _active_segments(self) -> list[str]:
        result = []
        for i in range(self._seg_list.count()):
            item = self._seg_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    # --------------------------------------------------------- display refresh

    def _refresh_display(self) -> None:
        """Refresh both the PID visualisation and the URL preview."""
        self._update_pid_viz()
        self._update_preview()

    def _update_pid_viz(self) -> None:
        """Render the 64-bit Product ID strip with active fields highlighted in blue."""
        active = set(self._active_segments())

        hex_cells = (
            '<td style="font-family:monospace; font-size:12px; '
            'padding-right:4px; vertical-align:middle; white-space:nowrap">0x&nbsp;</td>'
        )
        lbl_cells = "<td></td>"

        for hex_val, field, short, byte_desc in _PID_VIZ:
            if field in active:
                bg, fg, border = "#dbeafe", "#1d4ed8", "#93c5fd"
            else:
                bg, fg, border = "#f3f4f6", "#9ca3af", "#d1d5db"

            hex_cells += (
                f'<td style="background:{bg}; border:1px solid {border}; border-radius:3px; '
                f"padding:2px 5px; font-family:monospace; font-size:12px; color:{fg}; "
                f'text-align:center; white-space:nowrap">{hex_val}</td>'
                f'<td style="width:3px"></td>'
            )
            lbl_cells += (
                f'<td style="text-align:center; font-size:10px; color:{fg}; '
                f'white-space:nowrap">{short}'
                f'<br><span style="color:#6b7280; font-size:9px">{byte_desc}</span></td>'
                f"<td></td>"
            )

        html = (
            f'<table cellspacing="0" cellpadding="0">'
            f"<tr>{hex_cells}</tr>"
            f'<tr style="padding-top:2px">{lbl_cells}</tr>'
            f"</table>"
        )
        self._pid_viz_lbl.setText(html)

    def _update_preview(self) -> None:
        base = self._url_edit.text().rstrip("/") or "{base_url}"
        segs = self._active_segments()
        if segs:
            path = "/".join(f"{{{s}}}" for s in segs)
            preview = f"{base}/{path}/{{version}}.bin"
        else:
            preview = f"{base}/{{version}}.bin"
        self._preview_lbl.setText(_("Preview: ") + preview)

    # ---------------------------------------------------------------- password

    def _toggle_password(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self._pwd_edit.setEchoMode(mode)
        self._show_btn.setText(_("Hide") if show else _("Show"))

    # ------------------------------------------------------------------- save

    def _save_and_accept(self) -> None:
        self._config.http_base_url = self._url_edit.text().strip()
        self._config.http_use_credentials = self._cred_box.isChecked()
        self._config.http_login = self._login_edit.text().strip()
        self._config.http_password = self._pwd_edit.text()
        self._config.http_path_segments = self._active_segments()
        save_config(self._config)
        self.accept()

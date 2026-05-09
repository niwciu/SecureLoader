"""Credentials dialog — equivalent of the original ``login`` Qt dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, save_config
from ..i18n import _


class LoginDialog(QDialog):
    """Reads/writes HTTP credentials in :class:`AppConfig`."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle(_("Set login and password"))
        self.setMinimumSize(400, 200)
        self._build_ui()

    def _build_ui(self) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setVerticalSpacing(10)

        grid.addWidget(QLabel(_("Login:"), alignment=Qt.AlignmentFlag.AlignRight), 0, 0)
        self._login = QLineEdit(self._config.http_login)
        grid.addWidget(self._login, 0, 1)

        grid.addWidget(QLabel(_("Password:"), alignment=Qt.AlignmentFlag.AlignRight), 1, 0)
        self._password = QLineEdit(self._config.http_password)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        grid.addWidget(self._password, 1, 1)

        self._show_button = QPushButton(_("Show password"))
        self._show_button.pressed.connect(self._on_show_pressed)
        self._show_button.released.connect(self._on_show_released)
        grid.addWidget(self._show_button, 2, 1)

        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addLayout(grid)
        layout.addStretch()
        layout.addWidget(self._button_box)

    def _on_show_pressed(self) -> None:
        self._password.setEchoMode(QLineEdit.EchoMode.Normal)

    def _on_show_released(self) -> None:
        self._password.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_accept(self) -> None:
        self._config.http_login = self._login.text()
        self._config.http_password = self._password.text()
        save_config(self._config)
        self.accept()

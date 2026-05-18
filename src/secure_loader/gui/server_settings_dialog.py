"""Dialog for configuring server URL, credentials, product-ID sections, and URL path."""

from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, save_config
from ..core.id_sections import IdSectionDef
from ..i18n import _

# Up to 8 distinct section colours (background, foreground, border).
_SECTION_COLORS: list[tuple[str, str, str]] = [
    ("#dbeafe", "#1d4ed8", "#93c5fd"),  # blue
    ("#dcfce7", "#15803d", "#86efac"),  # green
    ("#fef9c3", "#854d0e", "#fde047"),  # yellow
    ("#fce7f3", "#9d174d", "#f9a8d4"),  # pink
    ("#ede9fe", "#5b21b6", "#c4b5fd"),  # violet
    ("#ffedd5", "#9a3412", "#fdba74"),  # orange
    ("#cffafe", "#0e7490", "#67e8f9"),  # cyan
    ("#f0fdf4", "#166534", "#4ade80"),  # light green
]
_INACTIVE_COLORS = ("#f3f4f6", "#9ca3af", "#d1d5db")


class _PidVizWidget(QWidget):
    """Paints the 16-nibble Product ID section map, expanding to fill container width."""

    _HEIGHT = 92
    _HEX_H = 52
    _GAP = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._defs: list[IdSectionDef] = []
        self.setFixedHeight(self._HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_defs(self, defs: list[IdSectionDef]) -> None:
        self._defs = list(defs)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        total_w = self.width()
        hex_h = self._HEX_H
        gap = self._GAP
        lbl_top = hex_h + 4
        lbl_name_h = 17
        lbl_range_h = 15

        n = 16
        cell_w = (total_w - gap * (n - 1)) / n

        nibble_section: dict[int, tuple[int, str]] = {}
        for color_idx, sec in enumerate(self._defs):
            ci = color_idx % len(_SECTION_COLORS)
            for nib in range(sec.start, sec.end):
                nibble_section[nib] = (ci, sec.name)

        i = 0
        while i < n:
            if i in nibble_section:
                ci, sec_name = nibble_section[i]
                j = i + 1
                while j < n and nibble_section.get(j) == (ci, sec_name):
                    j += 1
                bg_str, fg_str, border_str = _SECTION_COLORS[ci]
            else:
                j = i + 1
                sec_name = ""
                bg_str, fg_str, border_str = _INACTIVE_COLORS

            x = int(round(i * (cell_w + gap)))
            span_w = int(round(j * (cell_w + gap) - gap)) - x
            fg = QColor(fg_str)

            hex_rect = QRect(x, 0, span_w, hex_h)
            painter.setBrush(QBrush(QColor(bg_str)))
            painter.setPen(QPen(QColor(border_str), 1))
            painter.drawRoundedRect(hex_rect, 5, 5)

            hex_font = QFont("Monospace")
            hex_font.setPixelSize(18)
            painter.setFont(hex_font)
            painter.setPen(QPen(fg))
            painter.drawText(hex_rect, Qt.AlignmentFlag.AlignCenter, "X" * (j - i))

            if sec_name:
                short_name = sec_name if len(sec_name) <= 10 else sec_name[:9] + "…"
                name_font = QFont()
                name_font.setPixelSize(13)
                painter.setFont(name_font)
                painter.setPen(QPen(fg))
                painter.drawText(
                    QRect(x, lbl_top, span_w, lbl_name_h),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    short_name,
                )
                range_font = QFont("Monospace")
                range_font.setPixelSize(11)
                painter.setFont(range_font)
                painter.setPen(QPen(QColor("#6b7280")))
                painter.drawText(
                    QRect(x, lbl_top + lbl_name_h, span_w, lbl_range_h),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                    f"[{i}-{j - 1}]",
                )
            else:
                pos_font = QFont("Monospace")
                pos_font.setPixelSize(11)
                painter.setFont(pos_font)
                painter.setPen(QPen(QColor("#6b7280")))
                painter.drawText(
                    QRect(x, lbl_top, span_w, lbl_name_h + lbl_range_h),
                    Qt.AlignmentFlag.AlignCenter,
                    str(i),
                )

            i = j

        painter.end()


class ServerSettingsDialog(QDialog):
    """Settings dialog for server URL, credentials, product-ID sections, and URL path."""

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        # Mutable working copies — committed on OK
        self._section_rows: list[tuple[QLineEdit, QSpinBox, QSpinBox]] = []
        self._section_rows_layout: QVBoxLayout | None = None

        self.setWindowTitle(_("Server settings"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setMinimumWidth(580)
        self._build_ui()
        self._populate()
        root_layout = self.layout()
        assert root_layout is not None
        root_layout.activate()
        sh = root_layout.sizeHint()
        self.resize(max(self.minimumWidth(), sh.width()), sh.height())

    # ------------------------------------------------------------------ UI build

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 14, 16, 12)

        root.addWidget(self._build_server_group())
        root.addWidget(self._build_credentials_group())
        root.addWidget(self._build_id_sections_group())
        root.addWidget(self._build_url_path_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_server_group(self) -> QGroupBox:
        box = QGroupBox(_("Server"))
        layout = QVBoxLayout(box)
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel(_("Base URL")))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/firmware")
        self._url_edit.textChanged.connect(self._update_url_preview)
        url_row.addWidget(self._url_edit, stretch=1)
        layout.addLayout(url_row)
        self._allow_insecure_chk = QCheckBox(
            _("Allow plain HTTP (insecure — use only on trusted local networks)")
        )
        layout.addWidget(self._allow_insecure_chk)
        return box

    def _build_credentials_group(self) -> QGroupBox:
        box = QGroupBox(_("Credentials"))
        box.setCheckable(True)
        box.setChecked(False)
        self._cred_box = box
        layout = QVBoxLayout(box)

        login_row = QHBoxLayout()
        login_row.addWidget(QLabel(_("Login")))
        self._login_edit = QLineEdit()
        login_row.addWidget(self._login_edit, stretch=1)
        layout.addLayout(login_row)

        pwd_row = QHBoxLayout()
        pwd_row.addWidget(QLabel(_("Password")))
        self._pwd_edit = QLineEdit()
        self._pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        pwd_row.addWidget(self._pwd_edit, stretch=1)
        self._show_btn = QPushButton(_("Show"))
        self._show_btn.setCheckable(True)
        self._show_btn.toggled.connect(self._toggle_password)
        pwd_row.addWidget(self._show_btn)
        layout.addLayout(pwd_row)
        return box

    def _build_id_sections_group(self) -> QGroupBox:
        box = QGroupBox(_("Product ID sections"))
        layout = QVBoxLayout(box)

        hint = QLabel(
            _(
                "Define how the 64-bit Product ID is split into named sections. "
                "Start and End are nibble positions (0-15) within the 16-character hex ID."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Column headers
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(_("Section name")), stretch=3)
        hdr.addWidget(QLabel(_("Start")), stretch=1)
        hdr.addWidget(QLabel(_("End")), stretch=1)
        hdr.addWidget(QLabel(""), stretch=0)  # delete-button column
        layout.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Scrollable rows area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMaximumHeight(180)
        rows_widget = QWidget()
        self._section_rows_layout = QVBoxLayout(rows_widget)
        self._section_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._section_rows_layout.setSpacing(4)
        self._section_rows_layout.addStretch()
        scroll.setWidget(rows_widget)
        layout.addWidget(scroll)

        add_btn = QPushButton(_("+ Add section"))
        add_btn.clicked.connect(lambda: self._add_section_row())
        layout.addWidget(add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # PID visualization
        self._pid_viz = _PidVizWidget()
        layout.addWidget(self._pid_viz)
        return box

    def _build_url_path_group(self) -> QGroupBox:
        box = QGroupBox(_("URL path structure"))
        layout = QVBoxLayout(box)

        hint = QLabel(
            _(
                "Select which sections appear in the download URL path and set their order. "
                "Unchecked sections are available on the device but not used in the URL."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        list_row = QHBoxLayout()
        self._seg_list = QListWidget()
        self._seg_list.currentRowChanged.connect(self._update_move_buttons)
        self._seg_list.itemChanged.connect(self._update_url_preview)
        list_row.addWidget(self._seg_list, stretch=1)

        btn_col = QVBoxLayout()
        btn_col.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._up_btn = QPushButton(_("↑  Up"))
        self._up_btn.clicked.connect(self._move_seg_up)
        self._down_btn = QPushButton(_("↓  Down"))
        self._down_btn.clicked.connect(self._move_seg_down)
        btn_col.addWidget(self._up_btn)
        btn_col.addWidget(self._down_btn)
        list_row.addLayout(btn_col)
        layout.addLayout(list_row)

        self._preview_lbl = QLabel()
        self._preview_lbl.setWordWrap(True)
        layout.addWidget(self._preview_lbl)
        return box

    # ---------------------------------------------------------------- populate

    def _populate(self) -> None:
        self._url_edit.setText(self._config.http_base_url)
        self._allow_insecure_chk.setChecked(self._config.http_allow_insecure)
        self._cred_box.setChecked(self._config.http_use_credentials)
        self._login_edit.setText(self._config.http_login)
        self._pwd_edit.setText(self._config.http_password)

        for sec_def in self._config.id_section_defs:
            self._add_section_row(sec_def)

        self._refresh_seg_list(self._config.http_path_segments)
        self._update_pid_viz()
        self._update_url_preview()
        self._update_move_buttons()

    # ---------------------------------------------------------- section rows

    def _add_section_row(self, sec_def: IdSectionDef | None = None) -> None:
        assert self._section_rows_layout is not None

        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText(_("section_name"))
        start_spin = QSpinBox()
        start_spin.setRange(0, 15)
        end_spin = QSpinBox()
        end_spin.setRange(0, 15)

        if sec_def is not None:
            name_edit.setText(sec_def.name)
            start_spin.setValue(sec_def.start)
            end_spin.setValue(sec_def.end - 1)
        else:
            # Place the new section at the first nibble not covered by any existing valid row.
            covered: set[int] = set()
            for (_ne, other_s, other_e) in self._section_rows:
                if other_s.value() <= other_e.value():
                    covered.update(range(other_s.value(), other_e.value() + 1))
            new_start = next((i for i in range(16) if i not in covered), 15)
            start_spin.setValue(new_start)
            end_spin.setValue(new_start)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setToolTip(_("Delete this section"))

        row_layout.addWidget(name_edit, stretch=3)
        row_layout.addWidget(start_spin, stretch=1)
        row_layout.addWidget(end_spin, stretch=1)
        row_layout.addWidget(del_btn, stretch=0)

        # Insert before the trailing stretch (last item)
        insert_at = self._section_rows_layout.count() - 1
        self._section_rows_layout.insertWidget(insert_at, row_widget)

        self._section_rows.append((name_edit, start_spin, end_spin))

        # Wire signals
        name_edit.textChanged.connect(self._on_section_changed)
        start_spin.valueChanged.connect(self._on_section_changed)
        end_spin.valueChanged.connect(self._on_section_changed)
        del_btn.clicked.connect(lambda: self._delete_section_row(row_widget, name_edit, start_spin, end_spin))
        self._update_spinbox_constraints()

    def _delete_section_row(
        self,
        row_widget: QWidget,
        name_edit: QLineEdit,
        start_spin: QSpinBox,
        end_spin: QSpinBox,
    ) -> None:
        assert self._section_rows_layout is not None
        self._section_rows_layout.removeWidget(row_widget)
        row_widget.setParent(None)  # type: ignore[call-overload]
        self._section_rows = [
            r for r in self._section_rows if r[0] is not name_edit
        ]
        self._on_section_changed()

    def _on_section_changed(self) -> None:
        """Called whenever any section definition widget changes."""
        self._update_spinbox_constraints()
        self._update_pid_viz()
        self._sync_seg_list_to_sections()
        self._update_url_preview()

    def _update_spinbox_constraints(self) -> None:
        """Constrain spinboxes by nibble position, not by row order.

        Only currently-valid rows (start <= end) act as constraints for their
        neighbours.  This allows a section to freely move through another
        section's range during a multi-step repositioning without clamping
        unrelated rows.
        """
        rows = self._section_rows
        if not rows:
            return

        for _, s, e in rows:
            s.blockSignals(True)
            e.blockSignals(True)

        for _, start_spin, end_spin in rows:
            s_val = start_spin.value()
            # Consider only other rows that are currently in a valid state.
            others = [
                (other_s.value(), other_e.value())
                for (_, other_s, other_e) in rows
                if other_s is not start_spin and other_s.value() <= other_e.value()
            ]
            # start_min: right after the nearest valid section that ends before us.
            # If we're already inside another section (overlap), release the floor to 0
            # so the user can freely escape to a free nibble.
            inside_other = any(s <= s_val <= e for (s, e) in others)
            if inside_other:
                start_min = 0
            else:
                left_ends = [e for (_, e) in others if e < s_val]
                start_min = (max(left_ends) + 1) if left_ends else 0
            # end_max: just before the nearest valid section that starts after us.
            next_starts = [s for (s, _) in others if s > s_val]
            end_max = (min(next_starts) - 1) if next_starts else 15

            start_spin.setMinimum(start_min)
            end_spin.setMaximum(max(0, end_max))

        for _, s, e in rows:
            s.blockSignals(False)
            e.blockSignals(False)

    def _current_section_defs(self) -> list[IdSectionDef]:
        """Parse the current widget state into IdSectionDef objects (skipping invalid rows)."""
        result = []
        for name_edit, start_spin, end_spin in self._section_rows:
            name = name_edit.text().strip()
            start = start_spin.value()
            end = end_spin.value() + 1
            if name and 0 <= start < end <= 16:
                with contextlib.suppress(ValueError):
                    result.append(IdSectionDef(name=name, start=start, end=end))
        return result

    # -------------------------------------------------------- seg list (URL path)

    def _refresh_seg_list(self, active_segments: list[str]) -> None:
        """Populate path-segment list from config, adding any missing section names."""
        self._seg_list.blockSignals(True)
        self._seg_list.clear()
        current_names = {d.name for d in self._current_section_defs()}
        shown: set[str] = set()
        for seg_name in active_segments:
            self._add_seg_item(seg_name, checked=True)
            shown.add(seg_name)
        for name in current_names:
            if name not in shown:
                self._add_seg_item(name, checked=False)
        self._seg_list.blockSignals(False)

    def _add_seg_item(self, name: str, *, checked: bool) -> None:
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._seg_list.addItem(item)

    def _sync_seg_list_to_sections(self) -> None:
        """Add/remove items in the path-segment list to match current section definitions."""
        current_names = {d.name for d in self._current_section_defs()}
        existing_names: dict[str, Qt.CheckState] = {}
        for i in range(self._seg_list.count()):
            item = self._seg_list.item(i)
            if item:
                existing_names[item.data(Qt.ItemDataRole.UserRole)] = item.checkState()

        self._seg_list.blockSignals(True)
        # Remove items whose section was deleted
        for i in range(self._seg_list.count() - 1, -1, -1):
            item = self._seg_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) not in current_names:
                self._seg_list.takeItem(i)
        # Add items for new sections
        for name in current_names:
            if name not in existing_names:
                self._add_seg_item(name, checked=False)
        # Update display labels (in case name was edited in-place)
        for i in range(self._seg_list.count()):
            item = self._seg_list.item(i)
            if item:
                seg_name = item.data(Qt.ItemDataRole.UserRole)
                item.setText(seg_name)
        self._seg_list.blockSignals(False)

    def _move_seg_up(self) -> None:
        row = self._seg_list.currentRow()
        if row <= 0:
            return
        item = self._seg_list.takeItem(row)
        self._seg_list.insertItem(row - 1, item)
        self._seg_list.setCurrentRow(row - 1)
        self._update_url_preview()

    def _move_seg_down(self) -> None:
        row = self._seg_list.currentRow()
        if row < 0 or row >= self._seg_list.count() - 1:
            return
        item = self._seg_list.takeItem(row)
        self._seg_list.insertItem(row + 1, item)
        self._seg_list.setCurrentRow(row + 1)
        self._update_url_preview()

    def _update_move_buttons(self) -> None:
        row = self._seg_list.currentRow()
        count = self._seg_list.count()
        self._up_btn.setEnabled(row > 0)
        self._down_btn.setEnabled(0 <= row < count - 1)

    def _active_path_segments(self) -> list[str]:
        result = []
        for i in range(self._seg_list.count()):
            item = self._seg_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    # ------------------------------------------------------- PID visualization

    def _update_pid_viz(self) -> None:
        self._pid_viz.set_defs(self._current_section_defs())

    # ---------------------------------------------------------- URL preview

    def _update_url_preview(self) -> None:
        base = self._url_edit.text().rstrip("/") or "{base_url}"
        segs = self._active_path_segments()
        if segs:
            path = "/".join(f"{{{s}}}" for s in segs)
            preview = f"{base}/{path}/{{version}}.bin"
        else:
            preview = f"{base}/{{version}}.bin"
        self._preview_lbl.setText(_("Preview: ") + preview)

    # ------------------------------------------------------------ password

    def _toggle_password(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self._pwd_edit.setEchoMode(mode)
        self._show_btn.setText(_("Hide") if show else _("Show"))

    # -------------------------------------------------------------- save

    def _save_and_accept(self) -> None:
        defs = self._current_section_defs()
        if not defs:
            QMessageBox.warning(
                self,
                _("Invalid configuration"),
                _("At least one valid Product ID section must be defined."),
            )
            return

        # Check for duplicate names
        names = [d.name for d in defs]
        if len(names) != len(set(names)):
            QMessageBox.warning(
                self,
                _("Invalid configuration"),
                _("Section names must be unique."),
            )
            return

        self._config.http_base_url = self._url_edit.text().strip()
        self._config.http_allow_insecure = self._allow_insecure_chk.isChecked()
        self._config.http_use_credentials = self._cred_box.isChecked()
        self._config.http_login = self._login_edit.text().strip()
        self._config.http_password = self._pwd_edit.text()
        self._config.id_section_defs = defs
        self._config.http_path_segments = self._active_path_segments()
        save_config(self._config)
        self.accept()

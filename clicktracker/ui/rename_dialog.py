"""'Rename Sessions' window, opened from the Recorder tab."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QVBoxLayout,
)

from ..config import SESSION_NAME_MAX
from .widgets import session_label


class RenameSessionDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.changed = False
        self._names: dict[int, str] = {}

        self.setWindowTitle("Rename Sessions")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.session_combo = QComboBox()
        self.session_combo.currentIndexChanged.connect(self._load_name)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(SESSION_NAME_MAX)
        self.name_edit.setClearButtonEnabled(True)
        self.name_edit.setPlaceholderText("Leave empty to remove the name")
        form.addRow("Session", self.session_combo)
        form.addRow("New name", self.name_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        self.rename_btn = buttons.addButton("Rename", QDialogButtonBox.ButtonRole.ApplyRole)
        self.rename_btn.setDefault(True)  # Enter renames
        self.rename_btn.clicked.connect(self._rename)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self, select_id: int | None = None) -> None:
        sessions = self.store.list_sessions()
        self._names = {s["id"]: s.get("name") or "" for s in sessions}
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        for s in sessions:
            self.session_combo.addItem(session_label(s, show_clicks=False), s["id"])
        idx = self.session_combo.findData(select_id) if select_id is not None else 0
        self.session_combo.setCurrentIndex(max(idx, 0))
        self.session_combo.blockSignals(False)

        has_sessions = bool(sessions)
        self.rename_btn.setEnabled(has_sessions)
        self.name_edit.setEnabled(has_sessions)
        if not has_sessions:
            self.name_edit.setPlaceholderText("No sessions recorded yet")
        self._load_name()

    def _load_name(self, *_) -> None:
        self.name_edit.setText(self._names.get(self.session_combo.currentData(), ""))
        self.name_edit.selectAll()
        self.name_edit.setFocus()

    def _rename(self) -> None:
        session_id = self.session_combo.currentData()
        if session_id is None:
            return
        self.store.rename_session(session_id, self.name_edit.text())
        self.changed = True
        self._populate(select_id=session_id)
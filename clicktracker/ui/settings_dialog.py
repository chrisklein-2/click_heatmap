"""File ▸ Settings… dialog for app-wide preferences."""
from __future__ import annotations

from dataclasses import replace

from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QKeySequenceEdit, QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from ..capture.hotkey import qt_to_pynput
from ..preferences import Preferences

PORTABLE = QKeySequence.SequenceFormat.PortableText
NATIVE = QKeySequence.SequenceFormat.NativeText
HOTKEY_PRESETS = ("Shift+F12", "Ctrl+Alt+R", "Ctrl+Shift+F12", "Pause")


class SettingsDialog(QDialog):
    def __init__(self, prefs: Preferences, idle_method: str, tray_available: bool, parent=None):
        super().__init__(parent)
        self._prefs = prefs
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.addWidget(self._hotkey_group(prefs))
        layout.addWidget(self._idle_group(prefs, idle_method))
        layout.addWidget(self._recording_group(prefs))
        layout.addWidget(self._tray_group(prefs, tray_available))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._validate_hotkey()

    # ------------------------------------------------------------ groups
    def _hotkey_group(self, prefs: Preferences) -> QGroupBox:
        box = QGroupBox("Global hotkey")
        form = QFormLayout(box)
        self.hotkey_cb = QCheckBox("Start/stop recording from any app with a keyboard shortcut")
        self.hotkey_cb.setChecked(prefs.hotkey_enabled)
        self.hotkey_cb.toggled.connect(self._validate_hotkey)

        self.hotkey_edit = QKeySequenceEdit(QKeySequence(prefs.hotkey, PORTABLE))
        self.hotkey_edit.setMaximumSequenceLength(1)
        self.hotkey_edit.keySequenceChanged.connect(self._validate_hotkey)

        presets = QHBoxLayout()
        for text in HOTKEY_PRESETS:
            btn = QPushButton(QKeySequence(text, PORTABLE).toString(NATIVE))
            btn.setObjectName("smallButton")
            btn.clicked.connect(
                lambda _=False, t=text: self.hotkey_edit.setKeySequence(QKeySequence(t, PORTABLE)))
            presets.addWidget(btn)

        self.hotkey_status = QLabel()
        self.hotkey_status.setWordWrap(True)

        form.addRow(self.hotkey_cb)
        form.addRow("Shortcut", self.hotkey_edit)
        form.addRow("Presets", presets)
        form.addRow(self.hotkey_status)
        return box

    def _idle_group(self, prefs: Preferences, idle_method: str) -> QGroupBox:
        box = QGroupBox("Idle auto-stop")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.idle_cb = QCheckBox("Stop recording after no keyboard or mouse input for")
        self.idle_cb.setChecked(prefs.idle_stop_enabled)
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 24 * 60)
        self.idle_spin.setSuffix(" min")
        self.idle_spin.setValue(prefs.idle_minutes)
        self.idle_spin.setEnabled(prefs.idle_stop_enabled)
        self.idle_cb.toggled.connect(self.idle_spin.setEnabled)
        row.addWidget(self.idle_cb)
        row.addWidget(self.idle_spin)
        row.addStretch()
        layout.addLayout(row)
        note = QLabel(f"Idle detection: {idle_method}")
        note.setObjectName("dimLabel")
        note.setWordWrap(True)
        layout.addWidget(note)
        return box

    def _recording_group(self, prefs: Preferences) -> QGroupBox:
        box = QGroupBox("Recording")
        form = QFormLayout(box)
        self.ignore_cb = QCheckBox("Ignore clicks on this app's own window")
        self.ignore_cb.setChecked(prefs.ignore_own_window)
        self.flush_spin = QSpinBox()
        self.flush_spin.setRange(1, 300)
        self.flush_spin.setSuffix(" s")
        self.flush_spin.setValue(prefs.flush_seconds)
        form.addRow(self.ignore_cb)
        form.addRow("Write JSON buffer to database every", self.flush_spin)
        self.keys_cb = QCheckBox("Count key presses while recording (how often only, never the order)")
        self.keys_cb.setChecked(prefs.count_keys)
        form.addRow(self.keys_cb)
        return box

    def _tray_group(self, prefs: Preferences, tray_available: bool) -> QGroupBox:
        box = QGroupBox("System tray")
        layout = QVBoxLayout(box)
        self.tray_cb = QCheckBox("Show tray icon (red dot while recording)")
        self.tray_click_cb = QCheckBox("Left-clicking the tray icon starts/stops recording "
                                       "(otherwise it opens the window)")
        self.notify_cb = QCheckBox("Notify when recording starts or stops in the background")
        self.close_tray_cb = QCheckBox("Closing the window keeps the app running in the tray")
        self.start_tray_cb = QCheckBox("Start hidden in the tray")
        for cb, value in ((self.tray_cb, prefs.tray_icon),
                          (self.tray_click_cb, prefs.tray_click_toggles),
                          (self.notify_cb, prefs.notifications),
                          (self.close_tray_cb, prefs.close_to_tray),
                          (self.start_tray_cb, prefs.start_in_tray)):
            cb.setChecked(value)
            layout.addWidget(cb)

        def sync(on: bool) -> None:
            for cb in (self.tray_click_cb, self.notify_cb, self.close_tray_cb, self.start_tray_cb):
                cb.setEnabled(on)
        self.tray_cb.toggled.connect(sync)
        sync(prefs.tray_icon)

        if not tray_available:
            box.setEnabled(False)
            box.setTitle("System tray (not available on this system)")
        return box

    # -------------------------------------------------------- validation
    def _hotkey_text(self) -> str:
        return self.hotkey_edit.keySequence().toString(PORTABLE)

    def _validate_hotkey(self, *_) -> bool:
        enabled = self.hotkey_cb.isChecked()
        self.hotkey_edit.setEnabled(enabled)
        if not enabled:
            self._set_status("The global hotkey is turned off.", ok=True)
            return True
        try:
            combo = qt_to_pynput(self._hotkey_text())
        except ValueError as exc:
            self._set_status(str(exc), ok=False)
            return False
        self._set_status(f"Works in every app while the tracker is running (listening for {combo}).",
                         ok=True)
        return True

    def _set_status(self, text: str, ok: bool) -> None:
        self.hotkey_status.setText(text)
        self.hotkey_status.setStyleSheet(f"color: {'#8b919a' if ok else '#ff6b6b'};")

    def _on_accept(self) -> None:
        if not self._validate_hotkey():
            QMessageBox.warning(self, "Invalid hotkey", self.hotkey_status.text())
            return
        self.accept()

    def preferences(self) -> Preferences:
        return replace(
            self._prefs,
            hotkey_enabled=self.hotkey_cb.isChecked(),
            hotkey=self._hotkey_text() or self._prefs.hotkey,
            idle_stop_enabled=self.idle_cb.isChecked(),
            idle_minutes=self.idle_spin.value(),
            ignore_own_window=self.ignore_cb.isChecked(),
            flush_seconds=self.flush_spin.value(),
            tray_icon=self.tray_cb.isChecked(),
            notifications=self.notify_cb.isChecked(),
            close_to_tray=self.close_tray_cb.isChecked(),
            start_in_tray=self.start_tray_cb.isChecked(),
            count_keys=self.keys_cb.isChecked(),
            tray_click_toggles=self.tray_click_cb.isChecked(),
        )
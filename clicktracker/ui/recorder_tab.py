"""Recorder tab: session name, start/stop button, live statistics and recent clicks."""
from __future__ import annotations

import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget,
)

from ..config import BUFFER_PATH, SESSION_NAME_MAX
from ..capture.screens import get_monitors
from .rename_dialog import RenameSessionDialog
from .widgets import repolish, stat_box

MAX_RECENT = 200


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02}:{s % 3600 // 60:02}:{s % 60:02}"


class RecorderTab(QWidget):
    status_message = pyqtSignal(str, int)
    toggle_requested = pyqtSignal()
    sessions_changed = pyqtSignal()
    console_requested = pyqtSignal()

    def __init__(self, controller, store, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.store = store
        self._total_clicks = 0
        self._count_keys = True

        self._build_ui()

        controller.recording_changed.connect(self._on_recording_changed)
        controller.click_recorded.connect(self._on_click)
        controller.key_recorded.connect(self._on_key)
        controller.flushed.connect(self._on_flushed)

        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_duration)

        self._set_recording_ui(False)
        self.update_totals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status_label)

        name_row = QHBoxLayout()
        name_label = QLabel("Session name")
        name_label.setObjectName("dimLabel")
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(SESSION_NAME_MAX)
        self.name_edit.setClearButtonEnabled(True)
        self.name_edit.setPlaceholderText("Optional, e.g. Work or Gaming")
        self.name_edit.setToolTip("Used for the next session you start. While recording, "
                                  "editing it renames the current session.")
        self.name_edit.textChanged.connect(self._on_name_typed)
        self.name_edit.editingFinished.connect(self._on_name_committed)
        rename_btn = QPushButton("Rename Sessions…")
        rename_btn.clicked.connect(self._open_rename_dialog)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit, 1)
        name_row.addWidget(rename_btn)
        root.addLayout(name_row)

        self.record_btn = QPushButton()
        self.record_btn.setObjectName("recordButton")
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(lambda: self.toggle_requested.emit())
        root.addWidget(self.record_btn)

        self.hint_label = QLabel()
        self.hint_label.setObjectName("hintLabel")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint_label)

        self.lbl_session = QLabel("—")
        self.lbl_duration = QLabel("00:00:00")
        self.lbl_count = QLabel("0")
        self.lbl_keys = QLabel("0")
        self.lbl_last = QLabel("—")
        self.lbl_autostop = QLabel("Off")
        self.lbl_displays = QLabel(" + ".join(f"{m.width}×{m.height}" for m in get_monitors()))
        self.lbl_total = QLabel("0")
        self.lbl_sessions = QLabel("0")
        self.lbl_buffered = QLabel("0")
        self.lbl_last_write = QLabel("—")

        stats = QHBoxLayout()
        stats.addWidget(stat_box("Current session", [
            ("Session", self.lbl_session), ("Duration", self.lbl_duration),
            ("Clicks", self.lbl_count), ("Key presses", self.lbl_keys),
            ("Last click", self.lbl_last), ("Auto-stop", self.lbl_autostop),
            ("Displays", self.lbl_displays)]), 1)
        stats.addWidget(stat_box("Storage", [
            ("Total clicks", self.lbl_total), ("Sessions", self.lbl_sessions),
            ("Waiting for database", self.lbl_buffered),
            ("Last database write", self.lbl_last_write)]), 1)
        root.addLayout(stats)

        recent = QGroupBox("Recent clicks")
        rl = QVBoxLayout(recent)
        self.recent_list = QListWidget()
        rl.addWidget(self.recent_list)
        root.addWidget(recent, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        console_btn = QPushButton("Switch to Console Mode")
        console_btn.setToolTip("Close the window and keep running in a terminal, "
                               "controlled by the hotkey.")
        console_btn.clicked.connect(lambda: self.console_requested.emit())
        bottom.addWidget(console_btn)
        root.addLayout(bottom)

    def set_info(self, hotkey: str | None, autostop: str, flush_seconds: int,
                 hotkey_error: str | None = None, count_keys: bool = True) -> None:
        """Called by the main window whenever preferences change."""
        if hotkey:
            self.hint_label.setText(f"Press {hotkey} in any app to start or stop recording.")
        elif hotkey_error:
            self.hint_label.setText(f"Global hotkey unavailable: {hotkey_error}")
        else:
            self.hint_label.setText("Global hotkey is off (Recording ▸ Global Hotkey).")
        self.lbl_autostop.setText(autostop)
        self._count_keys = count_keys
        self.lbl_keys.setText(f"{self.controller.session_keys:,}" if count_keys else "Off")
        self.lbl_buffered.setToolTip(
            f"Clicks wait in memory and {BUFFER_PATH.name}; key counts wait in memory. Both are "
            f"written to the database every {flush_seconds} s and when recording stops.")

    def _set_recording_ui(self, recording: bool) -> None:
        self.record_btn.setText("■  Stop Recording" if recording else "●  Start Recording")
        self.record_btn.setProperty("recording", recording)
        self.status_label.setText("● RECORDING" if recording else "○ Idle")
        self.status_label.setProperty("recording", recording)
        repolish(self.record_btn)
        repolish(self.status_label)

    def _session_text(self) -> str:
        name = self.store.session_name
        return f"{name}  (#{self.store.session_id})" if name else f"#{self.store.session_id}"

    def _update_waiting(self) -> None:
        self.lbl_buffered.setText(
            f"{self.store.pending_count:,} clicks · {self.store.pending_key_presses:,} keys")

    def update_totals(self) -> None:
        self._total_clicks = self.store.total_clicks()
        self.lbl_total.setText(f"{self._total_clicks:,}")
        self.lbl_sessions.setText(f"{self.store.session_count():,}")
        self._update_waiting()

    def _update_duration(self) -> None:
        if self.controller.session_started is not None:
            self.lbl_duration.setText(fmt_duration(time.time() - self.controller.session_started))

    # ------------------------------------------------------- session names
    def _on_name_typed(self, text: str) -> None:
        # The field always holds the name for the next session.
        self.controller.next_session_name = text

    def _on_name_committed(self) -> None:
        # While recording, finishing an edit (Enter / leaving the field) renames the live session.
        if not self.controller.is_recording:
            return
        text = " ".join(self.name_edit.text().split())
        if text == (self.store.session_name or ""):
            return
        if self.controller.rename_current(text):
            self.lbl_session.setText(self._session_text())
            self.status_message.emit(f"Session renamed to '{self.controller.session_title}'.", 4000)
            self.sessions_changed.emit()

    def _open_rename_dialog(self, *_) -> None:
        dialog = RenameSessionDialog(self.store, self)
        dialog.exec()
        if not dialog.changed:
            return
        if self.controller.is_recording:  # the live session may have been renamed
            self.name_edit.setText(self.store.session_name or "")
            self.lbl_session.setText(self._session_text())
        self.sessions_changed.emit()

    # ------------------------------------------------------------ events
    def _on_recording_changed(self, recording: bool) -> None:
        self._set_recording_ui(recording)
        if recording:
            self.lbl_session.setText(self._session_text())
            self.lbl_count.setText("0")
            self.lbl_keys.setText("0" if self._count_keys else "Off")
            self.lbl_last.setText("—")
            self.recent_list.clear()
            self._update_duration()
            self._clock.start()
        else:
            self._clock.stop()
            msg = (f"'{self.controller.session_title}' saved ({self.controller.session_clicks:,} "
                   f"clicks, {self.controller.session_keys:,} key presses).")
            reason = self.controller.last_stop_reason
            self.status_message.emit(f"{reason} {msg}" if reason else msg, 0 if reason else 6000)
            self.name_edit.clear()  # each session gets its own name
        self.update_totals()

    def _on_click(self, x: int, y: int, button: str, ts: float) -> None:
        self._total_clicks += 1
        self.lbl_count.setText(f"{self.controller.session_clicks:,}")
        self.lbl_last.setText(f"{button} @ ({x}, {y})")
        self.lbl_total.setText(f"{self._total_clicks:,}")
        self._update_waiting()

        stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        self.recent_list.insertItem(0, f"{stamp}  {button:<7} ({x:>5}, {y:>5})")
        while self.recent_list.count() > MAX_RECENT:
            self.recent_list.takeItem(self.recent_list.count() - 1)

    def _on_key(self, _key: str) -> None:
        self.lbl_keys.setText(f"{self.controller.session_keys:,}")
        self._update_waiting()

    def _on_flushed(self, clicks: int, keys: int) -> None:
        self._update_waiting()
        self.lbl_last_write.setText(f"{datetime.now():%H:%M:%S}  (+{clicks:,} clicks, +{keys:,} keys)")
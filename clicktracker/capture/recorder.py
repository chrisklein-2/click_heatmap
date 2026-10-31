"""Connects the mouse/keyboard listeners to the store; handles flushing, naming and idle auto-stop."""
from __future__ import annotations

import sqlite3
import time
import math
from typing import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..config import FLUSH_INTERVAL_MS
from .idle import IdleDetector
from .keycounter import KeyCounter
from ..preferences import Preferences
from .screens import get_monitors
from ..storage.store import ClickStore
from .tracker import ClickTracker

IDLE_CHECK_MS = 15_000
TOGGLE_DEBOUNCE_S = 0.5


class RecordingController(QObject):
    recording_changed = pyqtSignal(bool)
    click_recorded = pyqtSignal(int, int, str, float)
    key_recorded = pyqtSignal(str)
    flushed = pyqtSignal(int, int)      # clicks, key presses written to SQLite
    storage_error = pyqtSignal(str)
    warning = pyqtSignal(str)

    def __init__(self, store: ClickStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.ignore_click: Callable[[], bool] | None = None  # set by the window (not used in console)
        self.next_session_name = ""     # name given to the next session that starts
        self.session_started: float | None = None
        self.session_clicks = 0
        self.session_keys = 0
        self.last_stop_reason: str | None = None
        self.idle = IdleDetector()

        self._finished_title = ""
        self._idle_limit_s: float | None = None
        self._last_activity = 0.0
        self._last_toggle = 0.0
        self._count_keys = False

        self.tracker = ClickTracker(self)
        self.tracker.clicked.connect(self._on_click)
        self.key_counter = KeyCounter(self)
        self.key_counter.key_pressed.connect(self._on_key)

        # Runs all the time so a failed write is retried even after Stop.
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self.flush)
        self._flush_timer.start()

        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(IDLE_CHECK_MS)
        self._idle_timer.timeout.connect(self._check_idle)

    @property
    def is_recording(self) -> bool:
        return self.store.is_recording

    @property
    def session_title(self) -> str:
        """Name of the current session, or of the last one after recording stopped."""
        return self.store.current_title if self.is_recording else self._finished_title

    # ---------------------------------------------------------- settings
    def apply_preferences(self, prefs: Preferences) -> None:
        """Apply the recording-related settings (shared by window and console mode)."""
        self.set_idle_limit(prefs.idle_minutes if prefs.idle_stop_enabled else None)
        self.set_flush_interval(prefs.flush_seconds)
        self.set_key_counting(prefs.count_keys)

    def set_flush_interval(self, seconds: int) -> None:
        self._flush_timer.setInterval(max(1, int(seconds)) * 1000)

    def seconds_until_flush(self) -> int:
        """Whole seconds until waiting clicks/keys are next written to the database."""
        remaining = self._flush_timer.remainingTime()
        return max(0, math.ceil(remaining / 1000)) if remaining >= 0 else 0

    def set_idle_limit(self, minutes: int | None) -> None:
        """None disables idle auto-stop."""
        self._idle_limit_s = minutes * 60 if minutes else None
        self._update_idle_timer()

    def set_key_counting(self, enabled: bool) -> None:
        self._count_keys = enabled
        if self.is_recording:
            if enabled:
                self._start_key_counter()
            else:
                self.key_counter.stop()

    # --------------------------------------------------------- recording
    def toggle(self) -> None:
        now = time.monotonic()
        if now - self._last_toggle < TOGGLE_DEBOUNCE_S:  # ignore double triggers
            return
        self._last_toggle = now
        if self.is_recording:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.is_recording:
            return
        self.tracker.start()  # may raise (permissions etc.)
        try:
            self.store.start_session([m.to_dict() for m in get_monitors()], self.next_session_name)
        except Exception:
            self.tracker.stop()
            raise
        self.session_started = time.time()
        self.session_clicks = 0
        self.session_keys = 0
        self.last_stop_reason = None
        self._last_activity = 0.0
        if self._count_keys:
            self._start_key_counter()
        self._update_idle_timer()
        self.recording_changed.emit(True)

    def stop(self, reason: str | None = None) -> None:
        if not self.is_recording:
            return
        self._finished_title = self.store.current_title
        self.tracker.stop()
        self.key_counter.stop()
        self._idle_timer.stop()
        self.last_stop_reason = reason
        try:
            result = self.store.end_session()
            if result:
                self.flushed.emit(result.clicks, result.keys)
        except sqlite3.Error as exc:
            self._report(exc)
        self.session_started = None
        self.recording_changed.emit(False)

    def rename_current(self, name: str) -> bool:
        """Rename the session being recorded. Returns False if not recording."""
        if not self.is_recording:
            return False
        try:
            self.store.rename_session(self.store.session_id, name)
        except sqlite3.Error as exc:
            self._report(exc)
            return False
        return True

    def flush(self) -> None:
        try:
            result = self.store.flush()
        except sqlite3.Error as exc:
            self._report(exc)
            return
        if result:
            self.flushed.emit(result.clicks, result.keys)

    def shutdown(self) -> None:
        self.stop()
        self._flush_timer.stop()
        self._idle_timer.stop()

    def _start_key_counter(self) -> None:
        try:
            self.key_counter.start()
        except Exception as exc:
            self.warning.emit(f"Key counting unavailable: {exc}")

    # -------------------------------------------------------------- idle
    def _update_idle_timer(self) -> None:
        if self.is_recording and self._idle_limit_s:
            if not self._idle_timer.isActive():
                self._idle_timer.start()
        else:
            self._idle_timer.stop()

    def _check_idle(self) -> None:
        if not self.is_recording or not self._idle_limit_s:
            return
        idle = self.idle.idle_seconds()
        if idle is None:  # no OS support: fall back to time since our own last event
            idle = time.time() - max(self._last_activity, self.session_started or time.time())
        if idle >= self._idle_limit_s:
            minutes = round(self._idle_limit_s / 60)
            self.stop(reason=f"Stopped automatically after {minutes} min with no input.")

    # ------------------------------------------------------------ events
    def _report(self, exc: Exception) -> None:
        self.storage_error.emit(
            f"Database write failed ({exc}). Clicks are safe in "
            f"{self.store.buffer.path.name} and will be retried.")

    def _on_click(self, x: int, y: int, button: str, ts: float) -> None:
        if not self.is_recording:
            return
        self._last_activity = ts
        if self.ignore_click is not None and self.ignore_click():
            return
        self.store.add_click(x, y, button, ts)
        if self.store.buffer.last_error:
            self.storage_error.emit(self.store.buffer.last_error)
        self.session_clicks += 1
        self.click_recorded.emit(x, y, button, ts)

    def _on_key(self, key: str) -> None:
        if not self.is_recording:
            return
        now = time.time()
        self._last_activity = now
        self.store.add_key(key, now)
        self.session_keys += 1
        self.key_recorded.emit(key)
"""Global key listener that reports each physical key press once (no auto-repeat)."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

from .keynames import key_id


class KeyCounter(QObject):
    key_pressed = pyqtSignal(str)  # key name only; nothing about order is kept

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener: keyboard.Listener | None = None
        self._down: set[str] = set()  # keys currently held (used to ignore auto-repeat)

    @property
    def is_running(self) -> bool:
        return self._listener is not None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._down.clear()
        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        self._listener.wait()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._down.clear()

    # Both callbacks run on pynput's thread. An exception would stop the
    # listener, so they are wrapped defensively.
    def _on_press(self, key) -> None:
        try:
            kid = key_id(key)
            if kid is None or kid in self._down:
                return
            self._down.add(kid)
            self.key_pressed.emit(kid)
        except Exception:
            pass

    def _on_release(self, key) -> None:
        try:
            kid = key_id(key)
            if kid is not None:
                self._down.discard(kid)
        except Exception:
            pass
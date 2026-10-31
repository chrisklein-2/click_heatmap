"""Global mouse click listener that forwards clicks to the Qt main thread."""
import time

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import mouse


class ClickTracker(QObject):
    clicked = pyqtSignal(int, int, str, float)  # x, y, button, unix timestamp

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = mouse.Listener(on_click=self._on_click)
        self._listener.start()
        self._listener.wait()  # block until the OS hook is ready

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        # Runs on pynput's thread; Qt queues the signal to the GUI thread.
        if pressed:
            self.clicked.emit(int(x), int(y), getattr(button, "name", str(button)), time.time())
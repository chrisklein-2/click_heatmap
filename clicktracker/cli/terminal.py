"""Terminal helpers for console mode: key-by-key input and a status line that updates in place."""
from __future__ import annotations

import atexit
import shutil
import sys
import threading

from PyQt6.QtCore import QObject, pyqtSignal


def is_interactive() -> bool:
    """True when there is a real terminal to read keys from and draw a status line on."""
    try:
        return bool(sys.stdin and sys.stdout and sys.stdin.isatty() and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


class InputReader(QObject):
    """Reads the keyboard on a background thread.

    In a real terminal it emits one `char` at a time, so the status line and what you type
    can share a line. Otherwise (input piped from a file etc.) it emits whole `line`s."""
    char = pyqtSignal(str)
    line = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.interactive = is_interactive()
        self._restore = None

    def start(self) -> None:
        if sys.stdin is None:
            return
        if not self.interactive:
            target = self._read_lines
        elif sys.platform == "win32":
            target = self._read_keys_windows
        else:
            self._enter_cbreak()
            target = self._read_keys_posix
        threading.Thread(target=target, name="console-input", daemon=True).start()

    def restore(self) -> None:
        """Put the terminal back to normal (macOS/Linux)."""
        if self._restore is not None:
            restore, self._restore = self._restore, None
            restore()

    def _enter_cbreak(self) -> None:
        import termios
        import tty
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        tty.setcbreak(fd)  # keys arrive immediately and are not echoed
        self._restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        atexit.register(self.restore)

    def _emit(self, signal, text: str) -> bool:
        try:
            signal.emit(text)
            return True
        except RuntimeError:  # app is shutting down
            return False

    def _read_keys_windows(self) -> None:
        import msvcrt
        while True:
            try:
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):   # arrow/function key: skip its second half
                    msvcrt.getwch()
                    continue
            except Exception:
                return
            if not self._emit(self.char, ch):
                return

    def _read_keys_posix(self) -> None:
        while True:
            try:
                ch = sys.stdin.read(1)
            except Exception:
                return
            if not ch or not self._emit(self.char, ch):
                return

    def _read_lines(self) -> None:
        while True:
            try:
                text = sys.stdin.readline()
            except Exception:
                return
            if not text or not self._emit(self.line, text.strip()):
                return


class StatusLine:
    """Keeps one line, '<status> > <what you typed>', at the bottom of the output.

    Uses only carriage returns and spaces, so it works in any terminal."""
    PROMPT = " > "

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.status = ""
        self.typed = ""
        self._drawn = ""  # what is currently on screen

    def _compose(self) -> str:
        width = max(20, shutil.get_terminal_size((80, 24)).columns - 1)
        tail = self.PROMPT + self.typed
        room = max(0, width - len(tail))
        status = self.status if len(self.status) <= room else self.status[:max(0, room - 1)] + "~"
        return (status + tail)[:width]  # never wrap: a wrapped line can't be redrawn in place

    def draw(self) -> None:
        if not self.enabled:
            return
        text = self._compose()
        if text == self._drawn:
            return
        pad = max(0, len(self._drawn) - len(text))
        sys.stdout.write("\r" + text + " " * pad + "\b" * pad)
        sys.stdout.flush()
        self._drawn = text

    def clear(self) -> None:
        if self.enabled and self._drawn:
            sys.stdout.write("\r" + " " * len(self._drawn) + "\r")
            sys.stdout.flush()
        self._drawn = ""

    def print(self, message: str) -> None:
        """Print a normal line above the status line."""
        self.clear()
        print(message, flush=True)
        self.draw()
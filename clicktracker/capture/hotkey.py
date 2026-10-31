"""System-wide hotkey that works while other apps have focus (pynput)."""
from __future__ import annotations

import sys

from PyQt6.QtCore import QObject, pyqtSignal
from pynput import keyboard

_IS_MAC = sys.platform == "darwin"

# Qt's portable text calls the Command key "Ctrl" on macOS.
_MODIFIERS = {
    "ctrl": "<cmd>" if _IS_MAC else "<ctrl>",
    "meta": "<ctrl>" if _IS_MAC else "<cmd>",
    "alt": "<alt>",
    "shift": "<shift>",
}
_SPECIAL = {
    "space": "<space>", "tab": "<tab>", "backspace": "<backspace>",
    "return": "<enter>", "enter": "<enter>", "esc": "<esc>",
    "ins": "<insert>", "del": "<delete>", "home": "<home>", "end": "<end>",
    "pgup": "<page_up>", "pgdown": "<page_down>",
    "left": "<left>", "right": "<right>", "up": "<up>", "down": "<down>",
    "pause": "<pause>", "scrolllock": "<scroll_lock>", "print": "<print_screen>",
    "capslock": "<caps_lock>", "numlock": "<num_lock>", "menu": "<menu>",
}
_OK_WITHOUT_MODIFIER = {"pause", "scrolllock", "print", "ins", "menu"}


def qt_to_pynput(sequence: str) -> str:
    """Convert Qt text like 'Shift+F12' to pynput format '<shift>+<f12>'.
    Raises ValueError with a readable message if the combination isn't usable."""
    chord = sequence.split(", ")[0].strip()  # only the first chord is used
    if not chord:
        raise ValueError("Press a key combination first.")
    parts = chord[:-2].split("+") + ["+"] if chord.endswith("++") else chord.split("+")
    *mods, key = [p.strip() for p in parts]

    mod_tokens = []
    for m in mods:
        token = _MODIFIERS.get(m.lower())
        if token is None:
            raise ValueError(f"Unsupported modifier: {m}")
        mod_tokens.append(token)

    k = key.lower()
    is_fkey = len(k) > 1 and k[0] == "f" and k[1:].isdigit()
    if is_fkey:
        if not 1 <= int(k[1:]) <= 20:
            raise ValueError(f"{key} isn't supported.")
        key_token = f"<{k}>"
    elif k in _SPECIAL:
        key_token = _SPECIAL[k]
    elif len(k) == 1:
        key_token = k
    else:
        raise ValueError(f"The key '{key}' isn't supported.")

    mod_names = {m.lower() for m in mods}
    if len(k) == 1 and not (mod_names - {"shift"}):
        raise ValueError("Letters, numbers and symbols need Ctrl or Alt, "
                         "otherwise normal typing would trigger the hotkey.")
    if not mods and not (is_fkey or k in _OK_WITHOUT_MODIFIER):
        raise ValueError("Add a modifier (Ctrl, Alt or Shift) to this key.")

    combo = "+".join([*mod_tokens, key_token])
    try:
        keyboard.HotKey.parse(combo)
    except ValueError as exc:
        raise ValueError(f"That key isn't available on this system ({exc}).") from None
    return combo


class GlobalHotkey(QObject):
    triggered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener: keyboard.GlobalHotKeys | None = None
        self.combo: str | None = None

    @property
    def is_active(self) -> bool:
        return self._listener is not None

    def start(self, qt_sequence: str) -> None:
        combo = qt_to_pynput(qt_sequence)  # validate before touching the old listener
        self.stop()
        # The callback runs on pynput's thread; the signal is queued to the GUI thread.
        self._listener = keyboard.GlobalHotKeys({combo: lambda: self.triggered.emit()})
        self._listener.start()
        self.combo = combo

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            self.combo = None
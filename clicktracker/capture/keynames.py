"""Turn pynput key events into stable names for the *physical* key.

'1' and '!' are both "1", 'A' and 'a' are both "a", left/right Shift are
"shift_l"/"shift_r", numpad keys are "kp_0"... so counts line up with the drawn keyboard.
"""
from __future__ import annotations

import sys

from pynput import keyboard

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
CMD_LABEL = "Win" if IS_WINDOWS else "Cmd" if IS_MAC else "Super"
ALT_LABEL = "Option" if IS_MAC else "Alt"

# Shifted symbol -> the key it lives on (US layout).
_SHIFTED = dict(zip('~!@#$%^&*()_+{}|:"<>?', "`1234567890-=[]\\;',./"))

# pynput uses different names for the same key on different platforms.
_ALIASES = {"shift": "shift_l", "ctrl": "ctrl_l", "alt": "alt_l", "alt_gr": "alt_r", "cmd": "cmd_l"}

# Virtual-key codes identify the physical key regardless of Shift/Ctrl.
_WIN_VK = {
    **{0x41 + i: chr(0x61 + i) for i in range(26)},      # A-Z
    **{0x30 + i: str(i) for i in range(10)},             # 0-9
    **{0x60 + i: f"kp_{i}" for i in range(10)},          # numpad 0-9
    0x6A: "kp_multiply", 0x6B: "kp_add", 0x6D: "kp_subtract", 0x6E: "kp_decimal", 0x6F: "kp_divide",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'", 0xE2: "intl_backslash",
    0xA6: "browser_back", 0xA7: "browser_forward", 0xA8: "browser_refresh", 0xA9: "browser_stop",
    0xAA: "browser_search", 0xAB: "browser_favorites", 0xAC: "browser_home",
    0xB4: "launch_mail", 0xB5: "launch_media", 0xB6: "launch_app1", 0xB7: "launch_app2",
}

_MAC_VK = {
    0x00: "a", 0x01: "s", 0x02: "d", 0x03: "f", 0x04: "h", 0x05: "g", 0x06: "z", 0x07: "x",
    0x08: "c", 0x09: "v", 0x0A: "intl_backslash", 0x0B: "b", 0x0C: "q", 0x0D: "w", 0x0E: "e",
    0x0F: "r", 0x10: "y", 0x11: "t", 0x12: "1", 0x13: "2", 0x14: "3", 0x15: "4", 0x16: "6",
    0x17: "5", 0x18: "=", 0x19: "9", 0x1A: "7", 0x1B: "-", 0x1C: "8", 0x1D: "0", 0x1E: "]",
    0x1F: "o", 0x20: "u", 0x21: "[", 0x22: "i", 0x23: "p", 0x25: "l", 0x26: "j", 0x27: "'",
    0x28: "k", 0x29: ";", 0x2A: "\\", 0x2B: ",", 0x2C: "/", 0x2D: "n", 0x2E: "m", 0x2F: ".",
    0x32: "`",
    0x41: "kp_decimal", 0x43: "kp_multiply", 0x45: "kp_add", 0x47: "num_lock", 0x4B: "kp_divide",
    0x4C: "kp_enter", 0x4E: "kp_subtract", 0x51: "kp_equal",
    0x52: "kp_0", 0x53: "kp_1", 0x54: "kp_2", 0x55: "kp_3", 0x56: "kp_4",
    0x57: "kp_5", 0x58: "kp_6", 0x59: "kp_7", 0x5B: "kp_8", 0x5C: "kp_9",
}

# X11 keysyms for the numpad (with Num Lock on and off).
_X11_VK = {
    **{0xFFB0 + i: f"kp_{i}" for i in range(10)},
    0xFFAE: "kp_decimal", 0xFFAB: "kp_add", 0xFFAD: "kp_subtract", 0xFFAA: "kp_multiply",
    0xFFAF: "kp_divide", 0xFF8D: "kp_enter",
    0xFF9E: "kp_0", 0xFF9C: "kp_1", 0xFF99: "kp_2", 0xFF9B: "kp_3", 0xFF96: "kp_4",
    0xFF9D: "kp_5", 0xFF98: "kp_6", 0xFF95: "kp_7", 0xFF97: "kp_8", 0xFF9A: "kp_9",
    0xFF9F: "kp_decimal",
}

_VK_TABLE = _WIN_VK if IS_WINDOWS else _MAC_VK if IS_MAC else _X11_VK

_DISPLAY = {
    "shift_l": "Left Shift", "shift_r": "Right Shift",
    "ctrl_l": "Left Ctrl", "ctrl_r": "Right Ctrl",
    "alt_l": f"Left {ALT_LABEL}", "alt_r": f"Right {ALT_LABEL}",
    "cmd_l": f"Left {CMD_LABEL}", "cmd_r": f"Right {CMD_LABEL}",
    "esc": "Esc", "intl_backslash": "ISO \\ key",
}


def key_id(key) -> str | None:
    """Stable name for the physical key, or None if it can't be identified."""
    if key is None:
        return None
    if isinstance(key, keyboard.Key):
        return _ALIASES.get(key.name, key.name)
    vk = getattr(key, "vk", None)
    if vk is not None and vk in _VK_TABLE:
        return _VK_TABLE[vk]
    char = getattr(key, "char", None)
    if char and len(char) == 1 and char.isprintable() and not char.isspace():
        c = char.lower()
        return _SHIFTED.get(c, c)
    if vk is not None:
        return f"vk_{vk}"
    return None


def display_name(kid: str) -> str:
    """Human-friendly name, e.g. 'kp_5' -> 'Numpad 5', 'page_up' -> 'Page Up'."""
    if kid in _DISPLAY:
        return _DISPLAY[kid]
    if kid.startswith("kp_"):
        return "Numpad " + kid[3:].title()
    if kid.startswith("vk_"):
        return f"Key code {kid[3:]}"
    if len(kid) == 1:
        return kid.upper()
    return kid.replace("_", " ").title()
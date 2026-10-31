"""Position (in key-width units) of every key on the drawn keyboard (US ANSI)."""
from __future__ import annotations

from dataclasses import dataclass

from ..capture.keynames import ALT_LABEL, CMD_LABEL


@dataclass(frozen=True)
class KeyDef:
    id: str       # matches keynames.key_id()
    label: str
    x: float
    y: float
    w: float = 1.0
    h: float = 1.0


def _row(y: float, x: float, items) -> list[KeyDef]:
    """Lay keys out left to right. An item is (id, label) or (id, label, width);
    an empty id leaves a gap."""
    keys = []
    for item in items:
        kid, label, *rest = item
        w = rest[0] if rest else 1.0
        if kid:
            keys.append(KeyDef(kid, label, x, y, w))
        x += w
    return keys


_FKEYS = lambda a, b: [(f"f{i}", f"F{i}") for i in range(a, b + 1)]  # noqa: E731

MAIN = (
    _row(0, 0, [("esc", "Esc"), ("", "", 1), *_FKEYS(1, 4), ("", "", 0.5),
                *_FKEYS(5, 8), ("", "", 0.5), *_FKEYS(9, 12)])
    + _row(1.5, 0, [("`", "`"), *[(d, d) for d in "1234567890"], ("-", "-"), ("=", "="),
                    ("backspace", "Backspace", 2)])
    + _row(2.5, 0, [("tab", "Tab", 1.5), *[(c, c.upper()) for c in "qwertyuiop"],
                    ("[", "["), ("]", "]"), ("\\", "\\", 1.5)])
    + _row(3.5, 0, [("caps_lock", "Caps Lock", 1.75), *[(c, c.upper()) for c in "asdfghjkl"],
                    (";", ";"), ("'", "'"), ("enter", "Enter", 2.25)])
    + _row(4.5, 0, [("shift_l", "Shift", 2.25), *[(c, c.upper()) for c in "zxcvbnm"],
                    (",", ","), (".", "."), ("/", "/"), ("shift_r", "Shift", 2.75)])
    + _row(5.5, 0, [("ctrl_l", "Ctrl", 1.25), ("cmd_l", CMD_LABEL, 1.25), ("alt_l", ALT_LABEL, 1.25),
                    ("space", "Space", 6.25), ("alt_r", ALT_LABEL, 1.25), ("cmd_r", CMD_LABEL, 1.25),
                    ("menu", "Menu", 1.25), ("ctrl_r", "Ctrl", 1.25)])
)

NAVIGATION = (
    _row(0, 15.25, [("print_screen", "PrtSc"), ("scroll_lock", "ScrLk"), ("pause", "Pause")])
    + _row(1.5, 15.25, [("insert", "Ins"), ("home", "Home"), ("page_up", "PgUp")])
    + _row(2.5, 15.25, [("delete", "Del"), ("end", "End"), ("page_down", "PgDn")])
    + _row(4.5, 16.25, [("up", "↑")])
    + _row(5.5, 15.25, [("left", "←"), ("down", "↓"), ("right", "→")])
)

NUMPAD = (
    _row(1.5, 18.5, [("num_lock", "Num"), ("kp_divide", "/"), ("kp_multiply", "*"), ("kp_subtract", "-")])
    + _row(2.5, 18.5, [("kp_7", "7"), ("kp_8", "8"), ("kp_9", "9")])
    + [KeyDef("kp_add", "+", 21.5, 2.5, 1, 2)]
    + _row(3.5, 18.5, [("kp_4", "4"), ("kp_5", "5"), ("kp_6", "6")])
    + _row(4.5, 18.5, [("kp_1", "1"), ("kp_2", "2"), ("kp_3", "3")])
    + [KeyDef("kp_enter", "Enter", 21.5, 4.5, 1, 2)]
    + _row(5.5, 18.5, [("kp_0", "0", 2), ("kp_decimal", ".")])
)


def build_layout(numpad: bool = True) -> list[KeyDef]:
    return MAIN + NAVIGATION + (NUMPAD if numpad else [])
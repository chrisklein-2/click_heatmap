"""Persistent user settings stored in data/settings.ini."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSettings


class AppSettings:
    def __init__(self, path: Path):
        self._qs = QSettings(str(path), QSettings.Format.IniFormat)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the saved value converted to the type of `default`."""
        if default is None:
            return self._qs.value(key)
        try:
            return self._qs.value(key, default, type=type(default))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value: Any) -> None:
        self._qs.setValue(key, value)

    def sync(self) -> None:
        self._qs.sync()
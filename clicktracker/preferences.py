"""App-wide preferences (menu bar + File ▸ Settings…), stored in settings.ini."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from .config import FLUSH_INTERVAL_MS
from .settings import AppSettings


@dataclass
class Preferences:
    hotkey_enabled: bool = True
    hotkey: str = "Shift+F12"           # Qt "portable text" format
    idle_stop_enabled: bool = False     # off unless you turn it on
    idle_minutes: int = 60
    ignore_own_window: bool = True
    count_keys: bool = True
    flush_seconds: int = FLUSH_INTERVAL_MS // 1000
    tray_icon: bool = True
    notifications: bool = True
    close_to_tray: bool = False
    start_in_tray: bool = False
    tray_click_toggles: bool = True

    @classmethod
    def load(cls, settings: AppSettings) -> "Preferences":
        defaults = cls()
        return cls(**{f.name: settings.get(f"prefs/{f.name}", getattr(defaults, f.name))
                      for f in fields(cls)})

    def save(self, settings: AppSettings) -> None:
        for name, value in asdict(self).items():
            settings.set(f"prefs/{name}", value)
        settings.sync()
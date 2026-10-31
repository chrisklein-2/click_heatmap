"""Paths and constants shared across the app."""
from pathlib import Path

APP_NAME = "Click Heatmap Tracker"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DB_PATH = DATA_DIR / "clicks.db"
BUFFER_PATH = DATA_DIR / "click_buffer.json"
SETTINGS_PATH = DATA_DIR / "settings.ini"
BACKGROUND_PNG = DATA_DIR / "background.png"
BACKGROUND_META = DATA_DIR / "background.json"

FLUSH_INTERVAL_MS = 10_000  # how often buffered clicks are written to SQLite

LOCK_PATH = DATA_DIR / "app.lock"   # prevents two copies running at once
SESSION_NAME_MAX = 80
"""ClickStore: buffers clicks (JSON file) and key counts (memory) and flushes both to SQLite."""
from __future__ import annotations

import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .buffer import ClickBuffer
from ..config import SESSION_NAME_MAX
from .database import ClickDatabase
from .filters import ClickFilter
from .models import Click, session_title


def hour_start(timestamp: float) -> int:
    """Unix time of the start of the local hour containing `timestamp`."""
    return int(datetime.fromtimestamp(timestamp).replace(minute=0, second=0, microsecond=0).timestamp())


def clean_session_name(name: str | None) -> str | None:
    """Trim and collapse whitespace; empty names become None."""
    name = " ".join((name or "").split())
    return name[:SESSION_NAME_MAX] or None


@dataclass
class FlushResult:
    clicks: int = 0
    keys: int = 0

    def __bool__(self) -> bool:
        return bool(self.clicks or self.keys)


class ClickStore:
    def __init__(self, db_path: Path, buffer_path: Path):
        self.db = ClickDatabase(db_path)
        self.buffer = ClickBuffer(buffer_path)
        self.session_id: int | None = None
        self.session_name: str | None = None
        self.last_flush: float | None = None
        self._seq = 0

        # Key counts: absolute totals per (session, hour, key) for the current session.
        self._key_totals: dict[tuple[int, int, str], int] = {}
        self._dirty_keys: set[tuple[int, int, str]] = set()
        self._unflushed_key_presses = 0

        # Import clicks a previous run left in the JSON buffer.
        self.recovered = 0
        if self.buffer.load_leftovers():
            try:
                self.recovered = self.flush().clicks
            except sqlite3.Error:
                pass  # they stay in the buffer and are retried on the next flush
        self.db.close_orphaned_sessions()

    @property
    def is_recording(self) -> bool:
        return self.session_id is not None

    @property
    def current_title(self) -> str:
        return session_title(self.session_id, self.session_name) if self.is_recording else ""

    @property
    def pending_count(self) -> int:
        return len(self.buffer.pending)

    @property
    def pending_key_presses(self) -> int:
        return self._unflushed_key_presses

    # ---------------------------------------------------------- recording
    def start_session(self, monitors: list[dict], name: str | None = None) -> int:
        name = clean_session_name(name)
        self.session_id = self.db.create_session(monitors, name)
        self.session_name = name
        self._seq = 0
        self.buffer.set_active_session(self.session_id)
        return self.session_id

    def rename_session(self, session_id: int, name: str | None) -> str | None:
        name = clean_session_name(name)
        self.db.rename_session(session_id, name)
        if session_id == self.session_id:
            self.session_name = name
        return name

    def add_click(self, x: int, y: int, button: str, timestamp: float) -> Click:
        """Buffer a click (memory + JSON). Does NOT touch the database."""
        if self.session_id is None:
            raise RuntimeError("add_click() called without an active session")
        self._seq += 1
        click = Click(self.session_id, self._seq, x, y, button, timestamp)
        self.buffer.add(click)
        return click

    def add_key(self, key: str, timestamp: float) -> None:
        """Count one key press (in memory). Only per-hour totals are kept, never the order."""
        if self.session_id is None:
            return
        slot = (self.session_id, hour_start(timestamp), key)
        self._key_totals[slot] = self._key_totals.get(slot, 0) + 1
        self._dirty_keys.add(slot)
        self._unflushed_key_presses += 1

    def flush(self) -> FlushResult:
        """Write buffered clicks and changed key totals to SQLite."""
        result = FlushResult()
        batch = self.buffer.snapshot()
        if batch:
            self.db.write_clicks(batch)          # if this raises, the buffer is untouched
            self.buffer.discard(len(batch))
            result.clicks = len(batch)

        if self._dirty_keys:
            self.db.write_key_counts([(*slot, self._key_totals[slot]) for slot in self._dirty_keys])
            self._dirty_keys.clear()
            result.keys = self._unflushed_key_presses
            self._unflushed_key_presses = 0
            # Totals of finished sessions are now fully in the database.
            self._key_totals = {s: n for s, n in self._key_totals.items() if s[0] == self.session_id}

        if result:
            self.last_flush = time.time()
        return result

    def end_session(self) -> FlushResult:
        session_id, self.session_id = self.session_id, None
        self.session_name = None
        if session_id is None:
            return FlushResult()
        self.buffer.active_session = None
        result = self.flush()
        self.db.end_session(session_id)
        self.buffer.save()                       # removes the buffer file once it's empty
        return result

    # ------------------------------------------------------------ queries
    def _pending_matching(self, f: ClickFilter):
        return (c for c in self.buffer.pending if f.matches(c))

    def query_clicks(self, f: ClickFilter) -> list[tuple[int, int, str]]:
        rows = self.db.query_clicks(f)
        rows.extend((c.x, c.y, c.button) for c in self._pending_matching(f))
        return rows

    def hour_counts(self, f: ClickFilter) -> dict[int, int]:
        counts = self.db.hour_counts(f)
        for c in self._pending_matching(f):
            hour = datetime.fromtimestamp(c.timestamp).hour
            counts[hour] = counts.get(hour, 0) + 1
        return counts

    def days_with_clicks(self, f: ClickFilter) -> list[str]:
        days = self.db.days(f)
        days.update(date.fromtimestamp(c.timestamp).isoformat() for c in self._pending_matching(f))
        return sorted(days, reverse=True)

    def time_range(self, f: ClickFilter) -> tuple[float, float] | None:
        values = [v for v in self.db.time_range(f) if v is not None]
        values += [c.timestamp for c in self._pending_matching(f)]
        return (min(values), max(values)) if values else None

    def key_counts(self, session_id: int | None = None, start_ts: float | None = None) -> dict[str, int]:
        """Presses per key. Sessions with totals in memory are read from memory only,
        so nothing is counted twice."""
        start_hour = hour_start(start_ts) if start_ts is not None else None
        in_memory = {slot[0] for slot in self._key_totals}
        counts = self.db.key_counts(session_id, start_hour, exclude_sessions=in_memory)
        for (sid, hour, key), n in self._key_totals.items():
            if session_id is not None and sid != session_id:
                continue
            if start_hour is not None and hour < start_hour:
                continue
            counts[key] = counts.get(key, 0) + n
        return counts

    def list_sessions(self) -> list[dict]:
        pending = Counter(c.session_id for c in self.buffer.pending)
        sessions = self.db.list_sessions()
        for s in sessions:
            s["clicks"] += pending.get(s["id"], 0)
            s["live"] = s["id"] == self.session_id
        return sessions

    def session_monitors(self, session_id: int) -> list[dict]:
        return self.db.session_monitors(session_id)

    def session_count(self) -> int:
        return self.db.session_count()

    def total_clicks(self) -> int:
        return self.db.click_count() + self.pending_count

    # ------------------------------------------------------------ editing
    def delete_session(self, session_id: int) -> None:
        if session_id == self.session_id:
            raise ValueError("Can't delete the session that is currently recording.")
        if any(c.session_id == session_id for c in self.buffer.pending):
            self.buffer.pending = [c for c in self.buffer.pending if c.session_id != session_id]
            self.buffer.save()
        self._key_totals = {s: n for s, n in self._key_totals.items() if s[0] != session_id}
        self._dirty_keys = {s for s in self._dirty_keys if s[0] != session_id}
        self.db.delete_session(session_id)

    def close(self) -> None:
        try:
            if self.is_recording:
                self.end_session()
            else:
                self.flush()
        except sqlite3.Error:
            pass  # clicks remain in click_buffer.json and are imported next launch
        self.db.close()
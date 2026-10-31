"""SQLite access. Only ClickStore talks to this class."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .filters import DAY_SQL, HOUR_SQL, ClickFilter
from .models import Click

TABLES = """
CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    ended_at      TEXT,
    screen_layout TEXT                 -- JSON list of monitors at recording time
);

CREATE TABLE IF NOT EXISTS clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    seq        INTEGER,                -- position within the session
    x          INTEGER NOT NULL,
    y          INTEGER NOT NULL,
    button     TEXT    NOT NULL,
    timestamp  REAL    NOT NULL        -- unix epoch seconds
);

CREATE TABLE IF NOT EXISTS key_counts (
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    hour       INTEGER NOT NULL,   -- unix time of the start of the (local) hour
    key_name   TEXT    NOT NULL,   -- e.g. "a", "enter", "shift_l", "kp_5"
    presses    INTEGER NOT NULL,
    PRIMARY KEY (session_id, hour, key_name)
);
"""

INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_clicks_session_seq ON clicks(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_clicks_timestamp ON clicks(timestamp);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ClickDatabase:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(TABLES)
        self._migrate()
        self.conn.executescript(INDEXES)
        self.conn.commit()

    def _migrate(self) -> None:
        """Upgrade databases created by older versions."""
        click_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(clicks)")}
        if "seq" not in click_cols:
            self.conn.execute("ALTER TABLE clicks ADD COLUMN seq INTEGER")
        session_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(sessions)")}
        if "name" not in session_cols:
            self.conn.execute("ALTER TABLE sessions ADD COLUMN name TEXT")

    def create_session(self, monitors: list[dict], name: str | None = None) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (started_at, screen_layout, name) VALUES (?, ?, ?)",
                (now_iso(), json.dumps(monitors), name))
        return cur.lastrowid

    def rename_session(self, session_id: int, name: str | None) -> None:
        with self.conn:
            self.conn.execute("UPDATE sessions SET name = ? WHERE id = ?", (name, session_id))

    
    def end_session(self, session_id: int) -> None:
        with self.conn:
            self.conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (now_iso(), session_id))

    def close_orphaned_sessions(self) -> None:
        """Sessions left open by a crash end at the time of their last click."""
        rows = self.conn.execute("SELECT id, started_at FROM sessions WHERE ended_at IS NULL").fetchall()
        with self.conn:
            for r in rows:
                last = self.conn.execute("SELECT MAX(timestamp) FROM clicks WHERE session_id = ?",
                                         (r["id"],)).fetchone()[0]
                ended = (datetime.fromtimestamp(last).isoformat(timespec="seconds")
                         if last else r["started_at"])
                self.conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?", (ended, r["id"]))

    def delete_session(self, session_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM clicks WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM key_counts WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    def list_sessions(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT s.id, s.name, s.started_at, s.ended_at, COUNT(c.id) AS clicks
            FROM sessions s LEFT JOIN clicks c ON c.session_id = s.id
            GROUP BY s.id ORDER BY s.id DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def session_monitors(self, session_id: int) -> list[dict]:
        row = self.conn.execute("SELECT screen_layout FROM sessions WHERE id = ?",
                                (session_id,)).fetchone()
        return json.loads(row["screen_layout"]) if row and row["screen_layout"] else []

    def session_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    # -------------------------------------------------------------- clicks
    def write_clicks(self, clicks: list[Click]) -> None:
        """Insert a batch in ONE transaction. Already-stored (session, seq) pairs are
        skipped, so re-importing a buffer after a crash can't create duplicates."""
        first_seen: dict[int, float] = {}
        for c in clicks:
            first_seen[c.session_id] = min(c.timestamp, first_seen.get(c.session_id, c.timestamp))
        with self.conn:
            # Normally a no-op; recreates a session row if it is somehow missing.
            self.conn.executemany(
                "INSERT OR IGNORE INTO sessions (id, started_at) VALUES (?, ?)",
                [(sid, datetime.fromtimestamp(ts).isoformat(timespec="seconds"))
                 for sid, ts in first_seen.items()])
            self.conn.executemany(
                "INSERT OR IGNORE INTO clicks (session_id, seq, x, y, button, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(c.session_id, c.seq, c.x, c.y, c.button, c.timestamp) for c in clicks])

    def click_count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0]

    def query_clicks(self, f: ClickFilter) -> list[tuple[int, int, str]]:
        where, params = f.sql_where()
        return [tuple(r) for r in self.conn.execute(f"SELECT x, y, button FROM clicks{where}", params)]

    def hour_counts(self, f: ClickFilter) -> dict[int, int]:
        where, params = f.sql_where()
        rows = self.conn.execute(
            f"SELECT {HOUR_SQL} AS h, COUNT(*) FROM clicks{where} GROUP BY h", params)
        return {r[0]: r[1] for r in rows}

    def days(self, f: ClickFilter) -> set[str]:
        where, params = f.sql_where()
        return {r[0] for r in self.conn.execute(f"SELECT DISTINCT {DAY_SQL} FROM clicks{where}", params)}

    def time_range(self, f: ClickFilter) -> tuple[float | None, float | None]:
        where, params = f.sql_where()
        row = self.conn.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM clicks{where}", params).fetchone()
        return row[0], row[1]

    # --------------------------------------------------------- key counts
    def write_key_counts(self, rows: list[tuple[int, int, str, int]]) -> None:
        """rows = (session_id, hour, key_name, total_presses). Totals are absolute,
        so writing the same row twice can never double-count."""
        with self.conn:
            self.conn.executemany(
                "INSERT INTO key_counts (session_id, hour, key_name, presses) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id, hour, key_name) "
                "DO UPDATE SET presses = MAX(presses, excluded.presses)",
                rows)

    def key_counts(self, session_id: int | None = None, start_hour: int | None = None,
                   exclude_sessions=()) -> dict[str, int]:
        clauses, params = [], []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if start_hour is not None:
            clauses.append("hour >= ?")
            params.append(start_hour)
        if exclude_sessions:
            clauses.append(f"session_id NOT IN ({', '.join('?' * len(exclude_sessions))})")
            params.extend(exclude_sessions)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self.conn.execute(
            f"SELECT key_name, SUM(presses) FROM key_counts{where} GROUP BY key_name", params)
        return {r[0]: r[1] for r in rows}


    def close(self) -> None:
        self.conn.close()
"""Filters shared by the SQL queries and the in-memory buffer."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .models import Click

HOUR_SQL = "CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER)"
DAY_SQL = "date(timestamp, 'unixepoch', 'localtime')"


@dataclass(frozen=True)
class ClickFilter:
    session_id: int | None = None
    button: str | None = None
    start_ts: float | None = None     # inclusive
    end_ts: float | None = None       # exclusive
    hour_of_day: int | None = None    # 0-23 local time, on any day

    def sql_where(self) -> tuple[str, list]:
        clauses, params = [], []
        if self.session_id is not None:
            clauses.append("session_id = ?")
            params.append(self.session_id)
        if self.button:
            clauses.append("button = ?")
            params.append(self.button)
        if self.start_ts is not None:
            clauses.append("timestamp >= ?")
            params.append(self.start_ts)
        if self.end_ts is not None:
            clauses.append("timestamp < ?")
            params.append(self.end_ts)
        if self.hour_of_day is not None:
            clauses.append(f"{HOUR_SQL} = ?")
            params.append(self.hour_of_day)
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    def matches(self, c: Click) -> bool:
        if self.session_id is not None and c.session_id != self.session_id:
            return False
        if self.button and c.button != self.button:
            return False
        if self.start_ts is not None and c.timestamp < self.start_ts:
            return False
        if self.end_ts is not None and c.timestamp >= self.end_ts:
            return False
        if self.hour_of_day is not None and datetime.fromtimestamp(c.timestamp).hour != self.hour_of_day:
            return False
        return True

    def without_time(self) -> "ClickFilter":
        return replace(self, start_ts=None, end_ts=None, hour_of_day=None)
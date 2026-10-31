"""Clicks waiting to be written to the database: kept in memory and mirrored to JSON."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .jsonfmt import write_json_atomic
from .models import Click


class ClickBuffer:
    """The in-memory list is the working copy; the JSON file protects it against crashes.

    File layout (one click per line):
        {
          "active_session": 3,
          "clicks": [
            {"x": 1203, "y": 88, "button": "left", "timestamp": 1714570812.123, "session": 3, "seq": 1},
            ...
          ]
        }
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.pending: list[Click] = []
        self.active_session: int | None = None
        self.last_error: str | None = None

    def load_leftovers(self) -> list[Click]:
        """Load clicks a previous run didn't get into the database (crash, locked DB...)."""
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            clicks = [Click.from_json(d) for d in data.get("clicks", [])]
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            self.last_error = f"Could not read {self.path.name}: {exc}"
            try:  # keep the bad file for inspection instead of overwriting it
                os.replace(self.path, self.path.with_name(self.path.name + ".corrupt"))
            except OSError:
                pass
            return []
        self.pending.extend(clicks)
        return clicks

    def set_active_session(self, session_id: int | None) -> None:
        self.active_session = session_id
        self.save()

    def add(self, click: Click) -> None:
        self.pending.append(click)
        self.save()

    def snapshot(self) -> list[Click]:
        return list(self.pending)

    def discard(self, count: int) -> None:
        """Drop the first `count` clicks (after they were committed to the database)."""
        del self.pending[:count]
        self.save()

    def save(self) -> bool:
        try:
            if not self.pending and self.active_session is None:
                self.path.unlink(missing_ok=True)  # nothing buffered -> no file
            else:
                write_json_atomic(self.path, {
                    "active_session": self.active_session,
                    "clicks": [c.to_json() for c in self.pending],
                })
            self.last_error = None
            return True
        except OSError as exc:
            # The in-memory copy is still intact; the next save retries.
            self.last_error = f"Could not write {self.path.name}: {exc}"
            return False
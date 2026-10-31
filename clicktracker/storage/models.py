"""Plain data objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Click:
    session_id: int
    seq: int            # 1, 2, 3... within a session (used to avoid duplicates)
    x: int
    y: int
    button: str
    timestamp: float    # unix epoch seconds

    def to_json(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "button": self.button,
            "timestamp": round(self.timestamp, 3),
            "session": self.session_id,
            "seq": self.seq,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Click":
        return cls(
            session_id=int(d["session"]),
            seq=int(d["seq"]),
            x=int(d["x"]),
            y=int(d["y"]),
            button=str(d["button"]),
            timestamp=float(d["timestamp"]),
        )

def session_title(session_id: int | None, name: str | None) -> str:
    """Display name for a session: its custom name, or 'Session #id'."""
    if name:
        return name
    return f"Session #{session_id}" if session_id is not None else "Untitled session"
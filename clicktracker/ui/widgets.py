"""Small helpers shared by the tabs."""
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QLabel, QWidget

from datetime import datetime

from ..storage.models import session_title

def repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def stat_box(title: str, rows: list[tuple[str, QLabel]]) -> QGroupBox:
    box = QGroupBox(title)
    grid = QGridLayout(box)
    grid.setColumnStretch(1, 1)
    for r, (name, value) in enumerate(rows):
        key = QLabel(name)
        key.setObjectName("dimLabel")
        value.setObjectName("valueLabel")
        grid.addWidget(key, r, 0)
        grid.addWidget(value, r, 1)
    return box

def session_label(session: dict, show_clicks: bool = True) -> str:
    """Text for session lists, e.g. 'Work  ·  May 07, 14:03  (1,234)  • live'."""
    started = datetime.fromisoformat(session["started_at"]).strftime("%b %d, %H:%M")
    text = f"{session_title(session['id'], session.get('name'))}  ·  {started}"
    if show_clicks:
        text += f"  ({session['clicks']:,})"
    if session.get("live"):
        text += "  • live"
    return text
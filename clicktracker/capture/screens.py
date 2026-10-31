"""Monitor geometry (in the coordinate space pynput reports) and screenshots."""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        return asdict(self)


def _uses_physical_pixels() -> bool:
    # pynput reports physical pixels on Windows/Linux and points on macOS.
    return sys.platform != "darwin"


def get_monitors() -> list[Monitor]:
    monitors = []
    for screen in QGuiApplication.screens():
        g = screen.geometry()
        scale = screen.devicePixelRatio() if _uses_physical_pixels() else 1.0
        # Qt keeps a screen's top-left in native coordinates and only scales the size.
        monitors.append(Monitor(screen.name(), g.x(), g.y(),
                                round(g.width() * scale), round(g.height() * scale)))
    return monitors


def capture_desktop(path: Path) -> list[int]:
    """Screenshot every monitor into one image laid out like the desktop.
    Returns the bounds [x0, y0, x1, y1] the image covers."""
    screens = QGuiApplication.screens()
    monitors = get_monitors()
    x0 = min(m.x for m in monitors)
    y0 = min(m.y for m in monitors)
    x1 = max(m.x + m.width for m in monitors)
    y1 = max(m.y + m.height for m in monitors)

    canvas = QImage(x1 - x0, y1 - y0, QImage.Format.Format_RGB32)
    canvas.fill(QColor("#000000"))
    painter = QPainter(canvas)
    for screen, mon in zip(screens, monitors):
        img = screen.grabWindow(0).toImage()
        img.setDevicePixelRatio(1.0)
        if img.width() != mon.width or img.height() != mon.height:
            img = img.scaled(mon.width, mon.height, Qt.AspectRatioMode.IgnoreAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(mon.x - x0, mon.y - y0, img)
    painter.end()
    canvas.save(str(path))
    return [x0, y0, x1, y1]
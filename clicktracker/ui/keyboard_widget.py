"""Custom-painted keyboard with a press counter on every key."""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .keyboard_layout import KeyDef
from ..capture.keynames import display_name
from .theme import BG, BORDER, SURFACE, TEXT, TEXT_DIM

# Colour ramp used when "Color by frequency" is on (low -> high).
_STOPS = ((0.0, QColor("#23395d")), (0.35, QColor("#2f6fd6")),
          (0.7, QColor("#e0922f")), (1.0, QColor("#e5484d")))


def heat_color(t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    for (t0, c0), (t1, c1) in zip(_STOPS, _STOPS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return QColor(round(c0.red() + (c1.red() - c0.red()) * f),
                          round(c0.green() + (c1.green() - c0.green()) * f),
                          round(c0.blue() + (c1.blue() - c0.blue()) * f))
    return QColor(_STOPS[-1][1])


def compact(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}k"
    if n < 1_000_000:
        return f"{n // 1000}k"
    return f"{n / 1_000_000:.1f}M"


class KeyboardWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys: list[KeyDef] = []
        self._counts: dict[str, int] = {}
        self._tint = True
        self._rects: list[tuple[KeyDef, QRectF]] = []
        self.setMinimumSize(640, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, keys: list[KeyDef], counts: dict[str, int], tint: bool) -> None:
        self._keys, self._counts, self._tint = keys, counts, tint
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        self._rects = []
        if not self._keys:
            p.end()
            return

        total_w = max(k.x + k.w for k in self._keys)
        total_h = max(k.y + k.h for k in self._keys)
        margin = 10
        unit = min((self.width() - 2 * margin) / total_w, (self.height() - 2 * margin) / total_h)
        if unit <= 0:
            p.end()
            return
        ox = (self.width() - unit * total_w) / 2
        oy = (self.height() - unit * total_h) / 2
        gap = max(2.0, unit * 0.07)
        pad_x, pad_y = unit * 0.1, unit * 0.07

        label_font = QFont(self.font())
        label_font.setPixelSize(max(8, round(unit * 0.2)))
        count_font = QFont(self.font())
        count_font.setPixelSize(max(9, round(unit * 0.27)))
        count_font.setBold(True)
        label_metrics = QFontMetrics(label_font)
        peak = max((self._counts.get(k.id, 0) for k in self._keys), default=0)

        for key in self._keys:
            rect = QRectF(ox + key.x * unit + gap / 2, oy + key.y * unit + gap / 2,
                          key.w * unit - gap, key.h * unit - gap)
            self._rects.append((key, rect))
            count = self._counts.get(key.id, 0)

            if self._tint and count and peak:
                fill = heat_color(max(0.08, (count / peak) ** 0.5))
            else:
                fill = QColor(SURFACE)
            p.setPen(QPen(QColor(BORDER), 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, unit * 0.12, unit * 0.12)

            inner = rect.adjusted(pad_x, pad_y, -pad_x, -pad_y)
            p.setFont(label_font)
            p.setPen(QColor(TEXT))
            label = label_metrics.elidedText(key.label, Qt.TextElideMode.ElideRight, int(inner.width()))
            p.drawText(inner, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, label)

            p.setFont(count_font)
            p.setPen(QColor("#ffffff") if count else QColor(TEXT_DIM))
            p.drawText(inner, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, compact(count))
        p.end()

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            point = QPointF(event.pos())
            for key, rect in self._rects:
                if rect.contains(point):
                    count = self._counts.get(key.id, 0)
                    total = sum(self._counts.values())
                    share = f"  ({count / total:.1%} of all presses)" if total else ""
                    QToolTip.showText(event.globalPos(), f"{display_name(key.id)}: {count:,}{share}", self)
                    return True
            QToolTip.hideText()
            event.ignore()
            return True
        return super().event(event)
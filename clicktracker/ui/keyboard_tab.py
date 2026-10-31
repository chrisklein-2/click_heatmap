"""Keyboard tab: how often each key was pressed, drawn on a keyboard layout."""
from __future__ import annotations

import html
import time
from datetime import date, datetime, time as dtime

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .widgets import session_label

from ..config import DATA_DIR
from .keyboard_layout import build_layout
from ..capture.keynames import display_name
from .keyboard_widget import KeyboardWidget

ALL_SESSIONS = -1
PERIODS = (("All time", "all"), ("Today", "today"), ("Last 24 hours", "24h"),
           ("Last 7 days", "7d"), ("Last 30 days", "30d"))
PERIOD_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
TOP_N = 8


def select_data(combo: QComboBox, value) -> None:
    idx = combo.findData(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


class KeyboardTab(QWidget):
    status_message = pyqtSignal(str, int)

    def __init__(self, store, settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self._restoring = True
        self._preferred_session = ALL_SESSIONS

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)

        self._build_ui()
        self._restore_settings()
        self._restoring = False

    # -------------------------------------------------------- public hooks
    def on_activated(self) -> None:
        self.populate_sessions()
        self.refresh()

    def on_data_changed(self) -> None:
        self.populate_sessions()
        if self.isVisible():
            self.schedule_refresh()

    def on_key_pressed(self, *_) -> None:
        if self.isVisible():
            self.schedule_refresh(500)

    def schedule_refresh(self, delay_ms: int = 100) -> None:
        self._refresh_timer.start(delay_ms)

    def set_counting_state(self, enabled: bool) -> None:
        self.state_label.setText(
            "Key presses are counted while recording. Only how often each key is pressed is "
            "stored, never the order." if enabled else
            "Key counting is off. Turn it on under Recording ▸ Count Key Presses.")

    # ------------------------------------------------------------- layout
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        controls = QHBoxLayout()
        self.session_combo = QComboBox()
        self.session_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.session_combo.setMinimumContentsLength(16)
        self.period_combo = QComboBox()
        for label, value in PERIODS:
            self.period_combo.addItem(label, value)
        self.numpad_cb = QCheckBox("Numpad")
        self.tint_cb = QCheckBox("Color by frequency")
        for combo in (self.session_combo, self.period_combo):
            combo.currentIndexChanged.connect(self._changed)
        for cb in (self.numpad_cb, self.tint_cb):
            cb.toggled.connect(self._changed)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: self.on_activated())
        export_btn = QPushButton("Export PNG…")
        export_btn.clicked.connect(self.export_png)

        controls.addWidget(QLabel("Session"))
        controls.addWidget(self.session_combo)
        controls.addSpacing(8)
        controls.addWidget(QLabel("Period"))
        controls.addWidget(self.period_combo)
        controls.addSpacing(12)
        controls.addWidget(self.numpad_cb)
        controls.addWidget(self.tint_cb)
        controls.addStretch()
        controls.addWidget(refresh_btn)
        controls.addWidget(export_btn)
        root.addLayout(controls)

        self.state_label = QLabel()
        self.state_label.setObjectName("hintLabel")
        root.addWidget(self.state_label)

        self.keyboard = KeyboardWidget()
        root.addWidget(self.keyboard, 1)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.other_label = QLabel()
        self.other_label.setObjectName("dimLabel")
        self.other_label.setWordWrap(True)
        root.addWidget(self.summary_label)
        root.addWidget(self.other_label)

    # ----------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        s = self.settings
        self._preferred_session = s.get("keyboard/session", ALL_SESSIONS)
        select_data(self.period_combo, s.get("keyboard/period", "all"))
        self.numpad_cb.setChecked(s.get("keyboard/numpad", True))
        self.tint_cb.setChecked(s.get("keyboard/tint", True))
        self.populate_sessions()

    def _save_settings(self) -> None:
        s = self.settings
        s.set("keyboard/session", self.session_combo.currentData())
        s.set("keyboard/period", self.period_combo.currentData())
        s.set("keyboard/numpad", self.numpad_cb.isChecked())
        s.set("keyboard/tint", self.tint_cb.isChecked())

    def _changed(self, *_) -> None:
        if self._restoring:
            return
        self._save_settings()
        self.schedule_refresh()

    def populate_sessions(self) -> None:
        current = self.session_combo.currentData() if self.session_combo.count() else self._preferred_session
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItem("All sessions", ALL_SESSIONS)
        for s in self.store.list_sessions():
            self.session_combo.addItem(session_label(s, show_clicks=False), s["id"])
        idx = self.session_combo.findData(current)
        self.session_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.session_combo.blockSignals(False)

    # ------------------------------------------------------------ drawing
    def _period_start(self) -> float | None:
        mode = self.period_combo.currentData()
        if mode == "today":
            return datetime.combine(date.today(), dtime()).timestamp()
        hours = PERIOD_HOURS.get(mode)
        return time.time() - hours * 3600 if hours else None

    def refresh(self) -> None:
        sid = self.session_combo.currentData()
        session_id = None if sid in (None, ALL_SESSIONS) else sid
        counts = self.store.key_counts(session_id, self._period_start())
        keys = build_layout(self.numpad_cb.isChecked())
        self.keyboard.set_data(keys, counts, self.tint_cb.isChecked())

        total = sum(counts.values())
        if total:
            top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
            ranking = " · ".join(f"{html.escape(display_name(k))} {n:,}" for k, n in top)
            self.summary_label.setText(f"<b>{total:,}</b> key presses &nbsp;|&nbsp; Most used: {ranking}")
        else:
            self.summary_label.setText("No key presses recorded for this selection yet.")

        shown = {k.id for k in keys}
        others = sorted(((k, n) for k, n in counts.items() if k not in shown),
                        key=lambda kv: kv[1], reverse=True)
        self.other_label.setText("Keys not on the layout above: "
                                 + " · ".join(f"{display_name(k)} {n:,}" for k, n in others))
        self.other_label.setVisible(bool(others))

    def export_png(self, *_) -> None:
        default = DATA_DIR / f"keyboard_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export keyboard", str(default), "PNG image (*.png)")
        if path and self.keyboard.grab().save(path):
            self.status_message.emit(f"Saved {path}", 6000)
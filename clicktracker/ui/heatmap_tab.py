"""Heatmap tab: data filters, time selection, layer toggles and the chart."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, time as dtime, timedelta

from PyQt6.QtCore import QDate, QDateTime, QTime, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSlider,
    QVBoxLayout, QWidget,
)

import matplotlib.image as mpimg

from .widgets import session_label

from ..config import BACKGROUND_META, BACKGROUND_PNG, DATA_DIR
from ..storage.filters import ClickFilter
from .heatmap import HeatmapCanvas, RenderOptions
from ..capture.screens import get_monitors

ALL_SESSIONS = -1
BUTTONS = (("All buttons", ""), ("Left", "left"), ("Right", "right"), ("Middle", "middle"))
COLORMAPS = ("turbo", "inferno", "hot", "plasma", "jet", "viridis")
TIME_MODES = (("All time", "all"), ("Hour by hour", "hourly"), ("Custom range", "custom"))


def hour_label(hour: int, count: int = 0) -> str:
    return f"{hour:02d}:00 – {(hour + 1) % 24:02d}:00   ({count:,})"


def select_data(combo: QComboBox, value) -> None:
    idx = combo.findData(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)


class HeatmapTab(QWidget):
    status_message = pyqtSignal(str, int)
    data_changed = pyqtSignal()

    def __init__(self, store, settings, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self._restoring = True
        self._preferred_session = ALL_SESSIONS
        self._preferred_day: str | None = None
        self._bg_cache = None

        self._render_timer = QTimer(self)  # debounces redraws
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.refresh)

        self._build_ui()
        self._restore_settings()
        self._restoring = False

    # ------------------------------------------------------ public hooks
    def on_activated(self) -> None:
        self.populate_sessions()
        self._populate_days()
        self.refresh()

    def on_data_changed(self) -> None:
        self.populate_sessions()
        self._populate_days()
        if self.isVisible():
            self.schedule_render()

    def on_new_click(self, *_) -> None:
        if self.isVisible():
            self.schedule_render(750)

    def on_background_changed(self) -> None:
        self._bg_cache = None
        if self.isVisible():
            self.schedule_render()

    def schedule_render(self, delay_ms: int = 120) -> None:
        self._render_timer.start(delay_ms)

    # ----------------------------------------------------------- layout
    def _build_ui(self) -> None:
        panel = QWidget()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 8, 0)
        pl.addWidget(self._build_data_box())
        pl.addWidget(self._build_time_box())
        pl.addWidget(self._build_layers_box())
        pl.addWidget(self._build_appearance_box())
        pl.addLayout(self._build_actions())
        self.info_label = QLabel()
        self.info_label.setObjectName("dimLabel")
        self.info_label.setWordWrap(True)
        pl.addWidget(self.info_label)
        pl.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(330)

        self.canvas = HeatmapCanvas()

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.addWidget(scroll)
        root.addWidget(self.canvas, 1)

    def _build_data_box(self) -> QGroupBox:
        box = QGroupBox("Data")
        form = QFormLayout(box)
        self.session_combo = QComboBox()
        self.session_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.session_combo.setMinimumContentsLength(12)
        self.session_combo.currentIndexChanged.connect(self._on_scope_changed)
        self.button_combo = QComboBox()
        for label, value in BUTTONS:
            self.button_combo.addItem(label, value)
        self.button_combo.currentIndexChanged.connect(self._on_scope_changed)
        form.addRow("Session", self.session_combo)
        form.addRow("Button", self.button_combo)
        return box

    def _build_time_box(self) -> QGroupBox:
        box = QGroupBox("Time")
        layout = QVBoxLayout(box)
        self.time_mode_combo = QComboBox()
        for label, value in TIME_MODES:
            self.time_mode_combo.addItem(label, value)
        self.time_mode_combo.currentIndexChanged.connect(self._on_time_mode_changed)
        layout.addWidget(self.time_mode_combo)

        # --- hour by hour
        self.hourly_widget = QWidget()
        hf = QFormLayout(self.hourly_widget)
        hf.setContentsMargins(0, 4, 0, 0)
        self.day_combo = QComboBox()
        self.day_combo.currentIndexChanged.connect(self._changed)
        self.hour_combo = QComboBox()
        for h in range(24):
            self.hour_combo.addItem(hour_label(h))
        self.hour_combo.currentIndexChanged.connect(self._changed)
        hour_row = QHBoxLayout()
        for text, step in (("◀", -1), ("▶", 1)):
            btn = QPushButton(text)
            btn.setObjectName("smallButton")
            btn.setFixedWidth(34)
            btn.setToolTip("Previous hour" if step < 0 else "Next hour")
            btn.clicked.connect(lambda _=False, s=step: self._step_hour(s))
            hour_row.addWidget(btn)
            if step < 0:
                hour_row.addWidget(self.hour_combo, 1)
        hf.addRow("Day", self.day_combo)
        hf.addRow("Hour", hour_row)
        layout.addWidget(self.hourly_widget)

        # --- custom range
        self.custom_widget = QWidget()
        cf = QFormLayout(self.custom_widget)
        cf.setContentsMargins(0, 4, 0, 0)
        self.from_edit = self._make_datetime_edit()
        self.to_edit = self._make_datetime_edit()
        cf.addRow("From", self.from_edit)
        cf.addRow("To", self.to_edit)
        presets = QGridLayout()
        for i, (label, key) in enumerate((("Last hour", "hour"), ("Today", "today"),
                                          ("Last 7 days", "week"), ("Fit to data", "fit"))):
            btn = QPushButton(label)
            btn.setObjectName("smallButton")
            btn.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            presets.addWidget(btn, i // 2, i % 2)
        cf.addRow(presets)
        layout.addWidget(self.custom_widget)
        return box

    def _make_datetime_edit(self) -> QDateTimeEdit:
        edit = QDateTimeEdit()
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        edit.dateTimeChanged.connect(self._changed)
        return edit

    def _build_layers_box(self) -> QGroupBox:
        box = QGroupBox("Layers")
        layout = QVBoxLayout(box)
        self.show_heat_cb = QCheckBox("Heat map")
        self.show_points_cb = QCheckBox("Individual clicks")
        self.show_bg_cb = QCheckBox("Screenshot background")
        for cb in (self.show_heat_cb, self.show_points_cb, self.show_bg_cb):
            cb.toggled.connect(self._changed)
            layout.addWidget(cb)
        return box

    def _build_appearance_box(self) -> QGroupBox:
        box = QGroupBox("Appearance")
        form = QFormLayout(box)
        self.cmap_combo = QComboBox()
        self.cmap_combo.addItems(COLORMAPS)
        self.cmap_combo.currentIndexChanged.connect(self._changed)
        self.blur_slider, self.blur_row = self._slider(5, 200, " px")
        self.opacity_slider, self.opacity_row = self._slider(10, 100, "%")
        self.point_slider, self.point_row = self._slider(2, 40, "")
        self.boost_cb = QCheckBox("Boost low-density areas")
        self.boost_cb.toggled.connect(self._changed)
        form.addRow("Colors", self.cmap_combo)
        form.addRow("Blur", self.blur_row)
        form.addRow("Opacity", self.opacity_row)
        form.addRow("Dot size", self.point_row)
        form.addRow(self.boost_cb)
        return box

    def _slider(self, lo: int, hi: int, suffix: str):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        label = QLabel(f"{lo}{suffix}")
        label.setMinimumWidth(46)
        slider.valueChanged.connect(lambda v: label.setText(f"{v}{suffix}"))
        slider.valueChanged.connect(self._changed)
        layout.addWidget(slider, 1)
        layout.addWidget(label)
        return slider, row

    def _build_actions(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(lambda: self.on_activated())
        export_btn = QPushButton("Export PNG…")
        export_btn.clicked.connect(self.export_png)
        delete_btn = QPushButton("Delete selected session")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._delete_session)
        for b in (refresh_btn, export_btn, delete_btn):
            layout.addWidget(b)
        return layout

    # -------------------------------------------------------- settings
    def _restore_settings(self) -> None:
        s = self.settings
        self._preferred_session = s.get("heatmap/session", ALL_SESSIONS)
        select_data(self.button_combo, s.get("heatmap/button", ""))
        cmap_idx = self.cmap_combo.findText(s.get("heatmap/colormap", "turbo"))
        self.cmap_combo.setCurrentIndex(max(cmap_idx, 0))
        self.show_heat_cb.setChecked(s.get("heatmap/show_heat", True))
        self.show_points_cb.setChecked(s.get("heatmap/show_points", False))
        self.show_bg_cb.setChecked(s.get("heatmap/show_background", True))
        self.boost_cb.setChecked(s.get("heatmap/boost", False))
        self.blur_slider.setValue(s.get("heatmap/blur", 40))
        self.opacity_slider.setValue(s.get("heatmap/opacity", 70))
        self.point_slider.setValue(s.get("heatmap/point_size", 8))

        select_data(self.time_mode_combo, s.get("time/mode", "all"))
        self._preferred_day = s.get("time/day")
        self.hour_combo.setCurrentIndex(min(23, max(0, s.get("time/hour", datetime.now().hour))))
        now = QDateTime.currentDateTime()
        start = QDateTime.fromString(s.get("time/custom_start", ""), Qt.DateFormat.ISODate)
        end = QDateTime.fromString(s.get("time/custom_end", ""), Qt.DateFormat.ISODate)
        self.from_edit.setDateTime(start if start.isValid() else now.addDays(-1))
        self.to_edit.setDateTime(end if end.isValid() else now)

        self.populate_sessions()
        self._populate_days()
        self._on_time_mode_changed()
        self._update_enabled()

    def _save_settings(self) -> None:
        s = self.settings
        s.set("heatmap/session", self.session_combo.currentData())
        s.set("heatmap/button", self.button_combo.currentData())
        s.set("heatmap/colormap", self.cmap_combo.currentText())
        s.set("heatmap/show_heat", self.show_heat_cb.isChecked())
        s.set("heatmap/show_points", self.show_points_cb.isChecked())
        s.set("heatmap/show_background", self.show_bg_cb.isChecked())
        s.set("heatmap/boost", self.boost_cb.isChecked())
        s.set("heatmap/blur", self.blur_slider.value())
        s.set("heatmap/opacity", self.opacity_slider.value())
        s.set("heatmap/point_size", self.point_slider.value())
        s.set("time/mode", self.time_mode_combo.currentData())
        if self.day_combo.currentData() is not None:
            s.set("time/day", self.day_combo.currentData())
        s.set("time/hour", self.hour_combo.currentIndex())
        s.set("time/custom_start", self.from_edit.dateTime().toString(Qt.DateFormat.ISODate))
        s.set("time/custom_end", self.to_edit.dateTime().toString(Qt.DateFormat.ISODate))

    # ---------------------------------------------------------- reacting
    def _changed(self, *_) -> None:
        if self._restoring:
            return
        self._save_settings()
        self._update_enabled()
        self.schedule_render()

    def _on_scope_changed(self, *_) -> None:
        if self._restoring:
            return
        self._populate_days()  # available days depend on session/button
        self._changed()

    def _on_time_mode_changed(self, *_) -> None:
        mode = self.time_mode_combo.currentData()
        self.hourly_widget.setVisible(mode == "hourly")
        self.custom_widget.setVisible(mode == "custom")
        self._changed()

    def _update_enabled(self) -> None:
        heat = self.show_heat_cb.isChecked()
        for w in (self.cmap_combo, self.blur_row, self.opacity_row, self.boost_cb):
            w.setEnabled(heat)
        self.point_row.setEnabled(self.show_points_cb.isChecked())

    def _step_hour(self, delta: int) -> None:
        hour = self.hour_combo.currentIndex() + delta
        if self.day_combo.currentData() and not 0 <= hour <= 23:
            # Crossing midnight: jump to the next/previous day that has data (list is newest first).
            new_idx = self.day_combo.currentIndex() + (-1 if hour > 23 else 1)
            if not 1 <= new_idx < self.day_combo.count():
                return
            self.day_combo.setCurrentIndex(new_idx)
        self.hour_combo.setCurrentIndex(hour % 24)

    def _apply_preset(self, preset: str) -> None:
        now = QDateTime.currentDateTime()
        if preset == "hour":
            start, end = now.addSecs(-3600), now
        elif preset == "today":
            start = QDateTime(QDate.currentDate(), QTime(0, 0))
            end = start.addDays(1)
        elif preset == "week":
            start, end = now.addDays(-7), now
        else:  # fit to data
            rng = self.store.time_range(self._scope_filter())
            if rng is None:
                self.status_message.emit("No clicks to fit to.", 4000)
                return
            start = QDateTime.fromSecsSinceEpoch(int(rng[0]))
            end = QDateTime.fromSecsSinceEpoch(int(rng[1]) + 60)
        for edit, value in ((self.from_edit, start), (self.to_edit, end)):
            edit.blockSignals(True)
            edit.setDateTime(value)
            edit.blockSignals(False)
        self._changed()

    # ------------------------------------------------------ populating
    def populate_sessions(self) -> None:
        current = self.session_combo.currentData() if self.session_combo.count() else self._preferred_session
        self.session_combo.blockSignals(True)
        self.session_combo.clear()
        self.session_combo.addItem("All sessions", ALL_SESSIONS)
        for s in self.store.list_sessions():
            self.session_combo.addItem(session_label(s), s["id"])
        idx = self.session_combo.findData(current)
        self.session_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.session_combo.blockSignals(False)

    def _populate_days(self) -> None:
        current = self.day_combo.currentData() if self.day_combo.count() else self._preferred_day
        days = self.store.days_with_clicks(self._scope_filter())
        self.day_combo.blockSignals(True)
        self.day_combo.clear()
        self.day_combo.addItem("Every day", "")
        for d in days:
            self.day_combo.addItem(date.fromisoformat(d).strftime("%a, %b %d %Y"), d)
        idx = self.day_combo.findData(current) if current is not None else -1
        if idx < 0:
            idx = 1 if days else 0  # default to the most recent day
        self.day_combo.setCurrentIndex(idx)
        self.day_combo.blockSignals(False)

    def _update_hour_counts(self) -> None:
        f = self._scope_filter()
        day = self.day_combo.currentData()
        if day:
            start = datetime.combine(date.fromisoformat(day), dtime())
            f = replace(f, start_ts=start.timestamp(), end_ts=(start + timedelta(days=1)).timestamp())
        counts = self.store.hour_counts(f)
        for h in range(24):
            self.hour_combo.setItemText(h, hour_label(h, counts.get(h, 0)))

    # --------------------------------------------------------- filtering
    def _scope_filter(self) -> ClickFilter:
        sid = self.session_combo.currentData()
        return ClickFilter(session_id=None if sid in (None, ALL_SESSIONS) else sid,
                           button=self.button_combo.currentData() or None)

    def current_filter(self) -> ClickFilter:
        base = self._scope_filter()
        mode = self.time_mode_combo.currentData()
        if mode == "hourly":
            hour = self.hour_combo.currentIndex()
            day = self.day_combo.currentData()
            if not day:  # this hour on every day
                return replace(base, hour_of_day=hour)
            start = datetime.combine(date.fromisoformat(day), dtime(hour=hour))
            return replace(base, start_ts=start.timestamp(),
                           end_ts=(start + timedelta(hours=1)).timestamp())
        if mode == "custom":
            return replace(base,
                           start_ts=float(self.from_edit.dateTime().toSecsSinceEpoch()),
                           end_ts=float(self.to_edit.dateTime().toSecsSinceEpoch()))
        return base

    # ---------------------------------------------------------- drawing
    def _render_options(self) -> RenderOptions:
        return RenderOptions(
            show_heat=self.show_heat_cb.isChecked(),
            show_points=self.show_points_cb.isChecked(),
            sigma=self.blur_slider.value(),
            colormap=self.cmap_combo.currentText(),
            opacity=self.opacity_slider.value() / 100,
            boost=self.boost_cb.isChecked(),
            point_size=self.point_slider.value(),
        )

    def refresh(self) -> None:
        if self.time_mode_combo.currentData() == "hourly":
            self._update_hour_counts()
        f = self.current_filter()
        try:
            clicks = self.store.query_clicks(f)
            monitors = self.store.session_monitors(f.session_id) if f.session_id is not None else []
            if not monitors:
                monitors = [m.to_dict() for m in get_monitors()]
            background, bounds = (self._load_background() if self.show_bg_cb.isChecked()
                                  else (None, None))
            self.canvas.render(clicks, monitors, background, bounds, self._render_options())
        except Exception as exc:
            self.info_label.setText(f"Could not draw the heatmap:\n{exc}")
            return
        self.info_label.setText(self._describe(f, len(clicks), background is not None))

    def _describe(self, f: ClickFilter, count: int, has_background: bool) -> str:
        lines = [f"{count:,} clicks shown"]
        mode = self.time_mode_combo.currentData()
        if mode == "hourly":
            h = self.hour_combo.currentIndex()
            span = f"{h:02d}:00–{(h + 1) % 24:02d}:00"
            lines.append(f"{span} on {self.day_combo.currentText()}"
                         if self.day_combo.currentData() else f"{span}, every day")
        elif mode == "custom":
            if f.start_ts >= f.end_ts:
                lines.append("⚠ 'From' must be earlier than 'To'.")
            else:
                lines.append(f"{self.from_edit.text()}  →  {self.to_edit.text()}")
        else:
            lines.append("All time")
        if self.show_bg_cb.isChecked() and not has_background:
            lines.append("Tip: capture a screenshot background on the Recorder tab.")
        return "\n".join(lines)

    def _load_background(self):
        if not (BACKGROUND_PNG.exists() and BACKGROUND_META.exists()):
            return None, None
        mtime = BACKGROUND_PNG.stat().st_mtime
        if self._bg_cache is None or self._bg_cache[0] != mtime:
            image = mpimg.imread(str(BACKGROUND_PNG))
            bounds = json.loads(BACKGROUND_META.read_text())["bounds"]
            self._bg_cache = (mtime, image, bounds)
        return self._bg_cache[1], self._bg_cache[2]

    # ---------------------------------------------------------- actions
    def export_png(self, *_) -> None:
        default = DATA_DIR / f"heatmap_{datetime.now():%Y%m%d_%H%M%S}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export heatmap", str(default), "PNG image (*.png)")
        if path:
            self.canvas.export_png(path)
            self.status_message.emit(f"Saved {path}", 6000)

    def _delete_session(self, *_) -> None:
        sid = self.session_combo.currentData()
        if sid in (None, ALL_SESSIONS):
            QMessageBox.information(self, "Delete session", "Select a specific session first.")
            return
        if sid == self.store.session_id:
            QMessageBox.warning(self, "Delete session", "Stop recording before deleting this session.")
            return
        answer = QMessageBox.question(self, "Delete session",
                                      f"Permanently delete session #{sid} and all of its clicks?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_session(sid)
        self.populate_sessions()
        self._populate_days()
        self._save_settings()
        self.refresh()
        self.data_changed.emit()
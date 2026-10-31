"""System-tray icon: shows the recording state and controls the app."""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ..config import APP_NAME


def status_icon(recording: bool) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#dfe1e5"), 5))
    p.setBrush(QColor("#1e1f22"))
    p.drawEllipse(4, 4, 56, 56)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#e53935" if recording else "#6b6f76"))
    p.drawEllipse(18, 18, 28, 28)
    p.end()
    return QIcon(pix)


class TrayIcon(QSystemTrayIcon):
    """Left-click: start/stop recording (or open the window, see Settings).
    Middle-click: open the window. Right-click: menu."""
    show_requested = pyqtSignal()
    toggle_requested = pyqtSignal()
    console_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, window):
        super().__init__(status_icon(False), window)
        self.click_toggles = True

        self._menu = QMenu(window)  # owned by the main window so it stays alive
        self._state = self._menu.addAction("Not recording")
        self._state.setEnabled(False)
        self._menu.addSeparator()
        self._toggle = self._menu.addAction("Start Recording")
        self._show = self._menu.addAction("Show Window")
        self._console = self._menu.addAction("Switch to Console Mode")
        self._menu.addSeparator()
        self._quit = self._menu.addAction("Quit")

        self._toggle.triggered.connect(lambda: self.toggle_requested.emit())
        self._show.triggered.connect(lambda: self.show_requested.emit())
        self._console.triggered.connect(lambda: self.console_requested.emit())
        self._quit.triggered.connect(lambda: self.quit_requested.emit())

        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)
        self.setToolTip(APP_NAME)

    def _left_click_toggles(self) -> bool:
        # On macOS a click always opens the menu, so it never toggles directly.
        return self.click_toggles and sys.platform != "darwin"

    def _on_activated(self, reason) -> None:
        reasons = QSystemTrayIcon.ActivationReason
        if reason == reasons.Trigger:  # left click
            if self._left_click_toggles():
                self.toggle_requested.emit()
            else:
                self.show_requested.emit()
        elif reason == reasons.MiddleClick:
            self.show_requested.emit()
        elif reason == reasons.DoubleClick and not self._left_click_toggles():
            self.show_requested.emit()

    def set_state(self, recording: bool, hotkey: str | None, title: str = "") -> None:
        self.setIcon(status_icon(recording))
        self._toggle.setText("Stop Recording" if recording else "Start Recording")
        state = f"Recording: {title}" if recording else "Not recording"
        self._state.setText(state.replace("&", "&&"))

        action = "stop" if recording else "start"
        lines = [f"{APP_NAME}: {state.lower() if not recording else state}"]
        if self._left_click_toggles():
            lines.append(f"Left-click to {action} recording, right-click for the menu")
        else:
            lines.append("Left-click to open the window, right-click for the menu")
        if hotkey:
            lines.append(f"{hotkey} to {action} recording")
        self.setToolTip("\n".join(lines))

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
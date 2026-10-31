"""Main window: tabs, menu bar, global hotkey, tray icon and app-wide preferences."""
from __future__ import annotations

import json
from datetime import datetime

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QAction, QCursor, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QApplication, QDialog, QMainWindow, QMessageBox, QSystemTrayIcon, QTabWidget,
)

from ..config import APP_NAME, BACKGROUND_META, BACKGROUND_PNG, DATA_DIR
from ..capture.hotkey import GlobalHotkey
from ..preferences import Preferences
from ..capture.screens import capture_desktop
from .heatmap_tab import HeatmapTab
from .keyboard_tab import KeyboardTab
from .recorder_tab import RecorderTab
from .settings_dialog import SettingsDialog
from .tray import TrayIcon, status_icon


def hotkey_display(portable: str) -> str:
    seq = QKeySequence(portable, QKeySequence.SequenceFormat.PortableText)
    return seq.toString(QKeySequence.SequenceFormat.NativeText)


class MainWindow(QMainWindow):
    def __init__(self, store, controller, settings):
        super().__init__()
        self.store = store
        self.controller = controller
        self.settings = settings
        self.prefs = Preferences.load(settings)
        self._shut_down = False
        self._tray_hint_shown = False
        self._hotkey_error: str | None = None
        self.relaunch_command: list[str] | None = None  

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(status_icon(False))
        self.resize(1200, 800)

        self.recorder_tab = RecorderTab(controller, store)
        self.heatmap_tab = HeatmapTab(store, settings)
        self.keyboard_tab = KeyboardTab(store, settings)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.recorder_tab, "Recorder")
        self.tabs.addTab(self.heatmap_tab, "Heatmap")
        self.tabs.addTab(self.keyboard_tab, "Keyboard")
        self.setCentralWidget(self.tabs)

        self.hotkey = GlobalHotkey(self)
        self.hotkey.triggered.connect(self.toggle_recording)

        self.tray = TrayIcon(self) if QSystemTrayIcon.isSystemTrayAvailable() else None
        if self.tray is not None:
            self.tray.show_requested.connect(self.show_window)
            self.tray.toggle_requested.connect(self.toggle_recording)
            self.tray.quit_requested.connect(self.quit_app)
            self.tray.console_requested.connect(self.switch_to_console)

        controller.ignore_click = self._click_is_on_app
        self._build_menus()
        self._connect_signals()
        self._apply_preferences()
        self._restore_state()
        self.statusBar().showMessage(f"Data folder: {DATA_DIR}")

    @property
    def start_hidden(self) -> bool:
        return bool(self.prefs.start_in_tray and self.tray is not None and self.tray.isVisible())

    # ============================================================ menus
    def _add_action(self, menu, text, slot, shortcut=None, checkable=False) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        if checkable:
            action.triggered.connect(slot)                    # slot(checked: bool)
        else:
            action.triggered.connect(lambda _checked=False, f=slot: f())
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self._add_action(file_menu, "Capture Screen Background", self.capture_background, "Ctrl+B")
        self._add_action(file_menu, "Export Current View as PNG…", self.export_current_view, "Ctrl+E")
        self._add_action(file_menu, "Open Data Folder", self._open_data_folder)
        file_menu.addSeparator()
        settings_action = self._add_action(file_menu, "Settings…", self.open_settings, "Ctrl+,")
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        file_menu.addSeparator()
        self._add_action(file_menu, "Switch to Console Mode", self.switch_to_console)
        quit_action = self._add_action(file_menu, "Quit", self.quit_app, "Ctrl+Q")
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)

        rec_menu = bar.addMenu("&Recording")
        self.act_toggle = self._add_action(rec_menu, "Start Recording", self.toggle_recording)
        self._add_action(rec_menu, "Write Buffer to Database Now", self._flush_now)
        rec_menu.addSeparator()
        self.act_hotkey = self._add_action(
            rec_menu, "Global Hotkey", lambda on: self._set_pref("hotkey_enabled", on), checkable=True)
        self.act_keys = self._add_action(
            rec_menu, "Count Key Presses", lambda on: self._set_pref("count_keys", on), checkable=True)
        self.act_idle = self._add_action(
            rec_menu, "Auto-Stop When Idle", lambda on: self._set_pref("idle_stop_enabled", on),
            checkable=True)
        self.act_ignore = self._add_action(
            rec_menu, "Ignore Clicks on This Window",
            lambda on: self._set_pref("ignore_own_window", on), checkable=True)

        view_menu = bar.addMenu("&View")
        self._add_action(view_menu, "Recorder", lambda: self.tabs.setCurrentWidget(self.recorder_tab), "Ctrl+1")
        self._add_action(view_menu, "Heatmap", lambda: self.tabs.setCurrentWidget(self.heatmap_tab), "Ctrl+2")
        self._add_action(view_menu, "Keyboard", lambda: self.tabs.setCurrentWidget(self.keyboard_tab), "Ctrl+3")

        help_menu = bar.addMenu("&Help")
        self._add_action(help_menu, "About", self._show_about)

    def _connect_signals(self) -> None:
        status = self.statusBar()
        self.recorder_tab.status_message.connect(status.showMessage)
        self.recorder_tab.toggle_requested.connect(self.toggle_recording)
        self.heatmap_tab.status_message.connect(status.showMessage)
        self.keyboard_tab.status_message.connect(status.showMessage)
        self.heatmap_tab.data_changed.connect(self.recorder_tab.update_totals)
        self.heatmap_tab.data_changed.connect(self.keyboard_tab.on_data_changed)
        self.controller.storage_error.connect(lambda msg: status.showMessage(msg, 10_000))
        self.controller.warning.connect(lambda msg: status.showMessage(msg, 10_000))
        self.controller.click_recorded.connect(self.heatmap_tab.on_new_click)
        self.controller.key_recorded.connect(self.keyboard_tab.on_key_pressed)
        self.controller.recording_changed.connect(self._on_recording_changed)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.recorder_tab.sessions_changed.connect(self.heatmap_tab.on_data_changed)
        self.recorder_tab.sessions_changed.connect(self.keyboard_tab.on_data_changed)
        self.recorder_tab.console_requested.connect(self.switch_to_console)

    # ====================================================== preferences
    def _set_pref(self, name: str, value) -> None:
        setattr(self.prefs, name, value)
        self.prefs.save(self.settings)
        self._apply_preferences()

    def _apply_preferences(self) -> None:
        p = self.prefs
        self._hotkey_error = None
        if p.hotkey_enabled:
            try:
                self.hotkey.start(p.hotkey)
            except Exception as exc:
                self.hotkey.stop()
                self._hotkey_error = str(exc)
                self.statusBar().showMessage(f"Global hotkey unavailable: {exc}", 10_000)
        else:
            self.hotkey.stop()

        self.controller.apply_preferences(p)

        if self.tray is not None:
            self.tray.setVisible(p.tray_icon)
            self.tray.click_toggles = p.tray_click_toggles
        self._sync_ui()

    def _active_hotkey_label(self) -> str | None:
        if self.prefs.hotkey_enabled and self._hotkey_error is None:
            return hotkey_display(self.prefs.hotkey)
        return None

    def _sync_ui(self) -> None:
        """Refresh every menu item / label that reflects preferences or recording state."""
        p = self.prefs
        hotkey = self._active_hotkey_label()
        recording = self.controller.is_recording

        label = "Stop Recording" if recording else "Start Recording"
        self.act_toggle.setText(f"{label}\t{hotkey}" if hotkey else label)
        self.act_hotkey.setText(f"Global Hotkey ({hotkey_display(p.hotkey)})")
        self.act_hotkey.setChecked(p.hotkey_enabled)
        self.act_keys.setChecked(p.count_keys)
        self.act_idle.setText(f"Auto-Stop After {p.idle_minutes} min Idle")
        self.act_idle.setChecked(p.idle_stop_enabled)
        self.act_ignore.setChecked(p.ignore_own_window)

        autostop = f"After {p.idle_minutes} min idle" if p.idle_stop_enabled else "Off"
        self.recorder_tab.set_info(hotkey, autostop, p.flush_seconds, self._hotkey_error, p.count_keys)
        self.keyboard_tab.set_counting_state(p.count_keys)
        self.setWindowIcon(status_icon(recording))
        if self.tray is not None:
            self.tray.set_state(recording, hotkey, self.controller.session_title if recording else "")

    def open_settings(self) -> None:
        self.hotkey.stop()  # so pressing the hotkey in the editor doesn't toggle recording
        dialog = SettingsDialog(self.prefs, self.controller.idle.method,
                                tray_available=self.tray is not None, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.prefs = dialog.preferences()
            self.prefs.save(self.settings)
        self._apply_preferences()  # also restarts the hotkey listener

    # ======================================================== recording
    def toggle_recording(self) -> None:
        try:
            self.controller.toggle()
        except Exception as exc:
            self.show_window()
            QMessageBox.critical(self, "Could not start recording",
                                 f"The mouse listener failed to start:\n\n{exc}")

    def _on_recording_changed(self, recording: bool) -> None:
        self._sync_ui()
        self.heatmap_tab.on_data_changed()   # new/finished session appears in the lists
        self.keyboard_tab.on_data_changed()
        if not (self.tray is not None and self.tray.isVisible() and self.prefs.notifications):
            return
        reason = self.controller.last_stop_reason
        if self.isActiveWindow() and not reason:
            return  # you're looking at the app, no need for a popup
        title = self.controller.session_title
        hotkey = self._active_hotkey_label()
        if recording:
            hint = f" Press {hotkey} to stop." if hotkey else ""
            self.tray.notify("Recording started", f"{title}.{hint}")
        else:
            saved = (f"{self.controller.session_clicks:,} clicks and "
                     f"{self.controller.session_keys:,} key presses saved.")
            self.tray.notify(f"Recording stopped: {title}", f"{reason} {saved}" if reason else saved)

    def _click_is_on_app(self) -> bool:
        return self.prefs.ignore_own_window and QApplication.widgetAt(QCursor.pos()) is not None

    def _flush_now(self) -> None:
        clicks, keys = self.store.pending_count, self.store.pending_key_presses
        self.controller.flush()
        if not (clicks or keys):
            self.statusBar().showMessage("Nothing is waiting to be saved.", 5000)
        elif self.store.pending_count == 0 and self.store.pending_key_presses == 0:
            self.statusBar().showMessage(
                f"Wrote {clicks:,} clicks and {keys:,} key presses to the database.", 5000)

    # ===================================================== console mode
    def switch_to_console(self) -> None:
        """Close the window and carry on in console mode."""
        from ..cli import launch
        from ..cli.terminal import is_interactive

        same_terminal = is_interactive()  # started from a terminal we can keep using?
        if not same_terminal and not launch.can_open_terminal():
            QMessageBox.information(
                self, "Console mode",
                "A terminal window couldn't be opened automatically.\n\n"
                "Quit the app and run this in a terminal instead:\n\n"
                "    python main.py --console")
            return

        recording = self.controller.is_recording
        if same_terminal:
            detail = "The window will close and the app continues in the terminal it was started from."
            if recording:
                detail += " Recording carries on without a break."
        else:
            detail = "The window will close and console mode opens in a new terminal window."
            if recording:
                detail += " The current recording is saved and continues there as a new session."
        if QMessageBox.question(self, "Switch to console mode",
                                f"{detail}\n\nContinue?") != QMessageBox.StandardButton.Yes:
            return

        if same_terminal:
            self._detach_to_console()
        else:
            name = (self.store.session_name or self.controller.next_session_name or "").strip()
            self.relaunch_command = launch.console_command(start=recording, name=name)
            self.quit_app()  # app.py opens the new terminal once everything is saved

    def _detach_to_console(self) -> None:
        """Hide the window and hand the running store/controller to console mode."""
        from ..cli.console import attach_console

        self._shut_down = True  # from here on the console is responsible for shutting down
        self.hotkey.stop()      # the console starts its own hotkey listener
        self.controller.ignore_click = None
        self.settings.set("window/geometry", self.saveGeometry())
        self.settings.set("window/tab", self.tabs.currentIndex())
        self.settings.sync()
        if self.tray is not None:
            self.tray.hide()
        self.hide()
        attach_console(self.store, self.controller, self.prefs)

    # ======================================================= file menu
    def export_current_view(self) -> None:
        if self.tabs.currentWidget() is self.keyboard_tab:
            self.keyboard_tab.export_png()
        else:
            self.heatmap_tab.export_png()

    def capture_background(self) -> None:
        was_visible = self.isVisible()
        if was_visible:
            self.hide()  # keep this window out of the screenshot
        QTimer.singleShot(500, lambda: self._do_capture(was_visible))

    def _do_capture(self, restore_window: bool) -> None:
        error = None
        try:
            bounds = capture_desktop(BACKGROUND_PNG)
            BACKGROUND_META.write_text(json.dumps(
                {"bounds": bounds, "captured_at": datetime.now().isoformat(timespec="seconds")}))
        except Exception as exc:
            error = exc
        if restore_window:
            self.show_window()
        if error:
            QMessageBox.warning(self, "Capture failed", f"Could not capture the screen:\n{error}")
        else:
            self.statusBar().showMessage("Background captured.", 5000)
            self.heatmap_tab.on_background_changed()

    def _open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))

    def _show_about(self) -> None:
        hotkey = self._active_hotkey_label() or "off"
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Records where you click and how often you press each key.<br><br>"
            f"Global hotkey: {hotkey}<br>"
            f"Key counting: {'on' if self.prefs.count_keys else 'off'}<br>"
            f"Idle detection: {self.controller.idle.method}<br>"
            f"Data folder: {DATA_DIR}")

    # ================================================== window / quitting
    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _restore_state(self) -> None:
        geometry = self.settings.get("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.tabs.setCurrentIndex(self.settings.get("window/tab", 0))

    def _on_tab_changed(self, index: int) -> None:
        self.settings.set("window/tab", index)
        widget = self.tabs.widget(index)
        if widget is self.heatmap_tab:
            self.heatmap_tab.on_activated()
        elif widget is self.keyboard_tab:
            self.keyboard_tab.on_activated()

    def closeEvent(self, event) -> None:
        if (not self._shut_down and self.prefs.close_to_tray
                and self.tray is not None and self.tray.isVisible()):
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify(APP_NAME, "Still running in the tray. Use File ▸ Quit or the "
                                           "tray menu to exit.")
            return
        self._shutdown()
        event.accept()
        QApplication.quit()

    def quit_app(self) -> None:
        self._shutdown()
        QApplication.quit()

    def _shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        self.hotkey.stop()
        self.controller.shutdown()  # stops recording and flushes everything to the DB
        self.settings.set("window/geometry", self.saveGeometry())
        self.settings.set("window/tab", self.tabs.currentIndex())
        self.settings.sync()
        self.store.close()
        if self.tray is not None:
            self.tray.hide()
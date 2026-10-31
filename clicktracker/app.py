"""Application bootstrap: window mode (default) or console mode (--console)."""
from __future__ import annotations

import argparse
import sys

from PyQt6.QtCore import QCoreApplication, QLockFile

from .config import APP_NAME, BUFFER_PATH, DATA_DIR, DB_PATH, LOCK_PATH, SETTINGS_PATH

ALREADY_RUNNING = (f"{APP_NAME} is already running (in a window, in the system tray, "
                   f"or in a console). Only one copy can run at a time.")


def parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="main.py", description=f"{APP_NAME}: records mouse clicks and key-press counts.")
    parser.add_argument("--console", action="store_true",
                        help="run without a window; start/stop recording with the global hotkey")
    parser.add_argument("--start", action="store_true",
                        help="console mode: start recording immediately")
    parser.add_argument("--name", default="",
                        help="console mode: name for the sessions recorded in this run")
    parser.add_argument("--verbose", action="store_true",
                        help="console mode: also print every database write")
    args, unknown = parser.parse_known_args(argv[1:])
    return args, [argv[0], *unknown]  # leftover arguments are passed on to Qt


def make_instance_lock() -> QLockFile:
    lock = QLockFile(str(LOCK_PATH))
    lock.setStaleLockTime(0)  # only treat the lock as stale if its process has gone
    return lock


def run() -> int:
    args, qt_argv = parse_args(sys.argv)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QCoreApplication.setApplicationName(APP_NAME)
    lock = make_instance_lock()
    if args.console:
        from .cli.console import run_console
        return run_console(args, qt_argv, lock)
    return run_gui(qt_argv, lock)


def run_gui(qt_argv: list[str], lock: QLockFile) -> int:
    # Imported here so console mode doesn't load the widget/matplotlib code.
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from .capture.recorder import RecordingController
    from .settings import AppSettings
    from .storage.store import ClickStore
    from .ui.main_window import MainWindow
    from .ui.theme import apply_dark_theme

    app = QApplication(qt_argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # the main window decides when to quit (tray support)
    apply_dark_theme(app)

    if not lock.tryLock(100):
        QMessageBox.warning(None, APP_NAME, ALREADY_RUNNING)
        return 1

    settings = AppSettings(SETTINGS_PATH)
    store = ClickStore(DB_PATH, BUFFER_PATH)
    controller = RecordingController(store)

    window = MainWindow(store, controller, settings)
    if window.start_hidden:
        window.tray.notify(APP_NAME, "Running in the system tray.")
    else:
        window.show()

    if store.recovered:
        window.statusBar().showMessage(
            f"Recovered {store.recovered:,} buffered clicks left over from the last run.", 10_000)
    code = app.exec()

    # "Switch to Console Mode" when the app has no terminal of its own: release the
    # single-instance lock first, then open console mode in a new terminal window.
    if window.relaunch_command:
        lock.unlock()
        from .cli.launch import open_in_new_terminal
        open_in_new_terminal(window.relaunch_command)
    return code
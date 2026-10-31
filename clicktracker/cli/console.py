"""Console mode: no window. Recording is controlled by the global hotkey or typed commands,
and a live status line shows the current session."""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime

from PyQt6.QtCore import QCoreApplication, QLockFile, QObject, QTimer
from PyQt6.QtGui import QGuiApplication, QKeySequence

from ..capture.hotkey import GlobalHotkey
from ..capture.recorder import RecordingController
from ..config import APP_NAME, BUFFER_PATH, DATA_DIR, DB_PATH, SETTINGS_PATH
from ..preferences import Preferences
from ..settings import AppSettings
from ..storage.store import ClickStore
from .terminal import InputReader, StatusLine

HELP = """Commands (type one and press Enter):
  start / stop / toggle   control recording (same as the hotkey)
  name <text>             name the current session and the ones after it
  name                    (nothing after it) clear the name
  status                  print a summary line
  help                    show this list
  quit                    stop recording, save everything and exit (same as Ctrl+C)"""

_active_console: "ConsoleApp | None" = None  # keeps the console alive after switching from the window


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02}:{s % 3600 // 60:02}:{s % 60:02}"


def hotkey_text(portable: str) -> str:
    seq = QKeySequence(portable, QKeySequence.SequenceFormat.PortableText)
    return seq.toString(QKeySequence.SequenceFormat.NativeText)


class ConsoleApp(QObject):
    def __init__(self, store: ClickStore, controller: RecordingController, prefs: Preferences,
                 verbose: bool = False, parent=None):
        super().__init__(parent)
        self.store = store
        self.controller = controller
        self.prefs = prefs
        self.verbose = verbose
        self._quitting = False
        self._in_escape = False

        self.reader = InputReader(self)
        self.reader.char.connect(self._on_char)
        self.reader.line.connect(self.on_command)
        self.status = StatusLine(enabled=self.reader.interactive)

        self.hotkey = GlobalHotkey(self)
        self.hotkey.triggered.connect(self.toggle)

        controller.recording_changed.connect(self._on_recording_changed)
        controller.flushed.connect(self._on_flushed)
        controller.storage_error.connect(lambda msg: self.log(f"WARNING: {msg}"))
        controller.warning.connect(lambda msg: self.log(f"WARNING: {msg}"))

        # Redraws the status line. It also lets Python notice Ctrl+C while Qt's loop runs.
        self._ticker = QTimer(self)
        self._ticker.setInterval(250)
        self._ticker.timeout.connect(self._refresh)

    # ------------------------------------------------------------ startup
    def start(self, auto_start: bool = False, switched: bool = False) -> None:
        p = self.prefs
        idle = f"after {p.idle_minutes} min without input" if p.idle_stop_enabled else "off"
        print(f"{APP_NAME} - console mode" + (" (window closed)" if switched else ""))
        print(f"  Hotkey          : {self._start_hotkey()}")
        print(f"  Key counting    : {'on' if p.count_keys else 'off'}")
        print(f"  Idle auto-stop  : {idle}")
        print(f"  Database writes : every {p.flush_seconds} s")
        if self.controller.next_session_name:
            print(f"  Session name    : {self.controller.next_session_name}")
        print(f"  Data folder     : {DATA_DIR}")
        print("Commands: start, stop, name <text>, status, help, quit   (Ctrl+C also quits)\n",
              flush=True)

        if self.store.recovered and not switched:
            self.log(f"Recovered {self.store.recovered:,} buffered clicks left over from the last run.")
        self.reader.start()
        self._ticker.start()
        if auto_start and not self.controller.is_recording:
            self.start_recording()
        self._refresh()

    def _start_hotkey(self) -> str:
        if not self.prefs.hotkey_enabled:
            return "off (turn it on in the window app under File > Settings). Type 'start'/'stop'."
        try:
            self.hotkey.start(self.prefs.hotkey)
        except Exception as exc:
            return f"unavailable ({exc}). Type 'start'/'stop' instead."
        return f"{hotkey_text(self.prefs.hotkey)} (press it in any app to start/stop recording)"

    # -------------------------------------------------------- status line
    def _status_text(self) -> str:
        c, s = self.controller, self.store
        if not c.is_recording:
            if self.hotkey.is_active:
                return f"[ready] Press {hotkey_text(self.prefs.hotkey)} or type 'start' to record"
            return "[ready] Type 'start' to record"

        counts = f"{c.session_clicks:,} clicks"
        if self.prefs.count_keys:
            counts += f", {c.session_keys:,} key presses"
        if s.pending_count or s.pending_key_presses:
            seconds = c.seconds_until_flush()
            saved = f"saving in {seconds}s" if seconds else "saving..."
        else:
            saved = "saved"
        elapsed = fmt_duration(time.time() - c.session_started)
        return f"[REC {elapsed}] {c.session_title}: {counts} ({saved})"

    def _refresh(self) -> None:
        self.status.status = self._status_text()
        self.status.draw()

    def log(self, message: str) -> None:
        self.status.print(f"[{datetime.now():%H:%M:%S}] {message}")

    # ---------------------------------------------------------- recording
    def toggle(self) -> None:
        if self.controller.is_recording:
            self.controller.stop()
        else:
            self.start_recording()

    def start_recording(self) -> None:
        try:
            self.controller.start()
        except Exception as exc:
            self.log(f"Could not start recording: {exc}")

    def _on_recording_changed(self, recording: bool) -> None:
        c = self.controller
        if recording:
            self.log(f"Recording started: {c.session_title}")
        else:
            counts = f"{c.session_clicks:,} clicks"
            if self.prefs.count_keys:
                counts += f" and {c.session_keys:,} key presses"
            reason = f" ({c.last_stop_reason})" if c.last_stop_reason else ""
            self.log(f"Recording stopped: {c.session_title}. {counts} saved.{reason}")
        self._refresh()

    def _on_flushed(self, clicks: int, keys: int) -> None:
        if self.verbose:
            self.log(f"Saved to database: {clicks:,} clicks, {keys:,} key presses.")
        self._refresh()

    # -------------------------------------------------------------- input
    def _on_char(self, ch: str) -> None:
        """One key typed in the terminal: edit the command line shown after the prompt."""
        if self._quitting:
            return
        if self._in_escape:                      # swallow arrow-key sequences (macOS/Linux)
            if ch.isalpha() or ch == "~":
                self._in_escape = False
            return
        if ch == "\x1b":                          # Esc
            if sys.platform == "win32":
                self.status.typed = ""
            else:
                self._in_escape = True
        elif ch in ("\r", "\n"):                  # Enter: run the command
            text, self.status.typed = self.status.typed.strip(), ""
            if text:
                self.status.print(f"> {text}")
                self.on_command(text)
        elif ch in ("\x08", "\x7f"):              # Backspace
            self.status.typed = self.status.typed[:-1]
        elif ch == "\x03" or (ch == "\x04" and not self.status.typed):  # Ctrl+C / Ctrl+D
            self.quit()
            return
        elif ch.isprintable():
            self.status.typed += ch
        self.status.draw()

    def on_command(self, line: str) -> None:
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        if not cmd:
            return
        if cmd == "start":
            if self.controller.is_recording:
                self.log("Already recording.")
            else:
                self.start_recording()
        elif cmd == "stop":
            if self.controller.is_recording:
                self.controller.stop()
            else:
                self.log("Not recording.")
        elif cmd == "toggle":
            self.toggle()
        elif cmd == "name":
            self.controller.next_session_name = arg
            if self.controller.rename_current(arg):
                self.log(f"Current session renamed to: {self.controller.session_title}")
            else:
                self.log(f"Next session will be named: {arg}" if arg else "Next session will be unnamed.")
        elif cmd == "status":
            self.print_status()
        elif cmd in ("help", "?"):
            self.status.print(HELP)
        elif cmd in ("quit", "exit", "q"):
            self.quit()
        else:
            self.log(f"Unknown command '{cmd}'. Type 'help' for the list.")
        self._refresh()

    def print_status(self) -> None:
        c, s = self.controller, self.store
        if c.is_recording:
            self.log(self._status_text())
        else:
            upcoming = c.next_session_name or "(no name)"
            self.log(f"Not recording. {s.session_count():,} sessions and {s.total_clicks():,} clicks "
                     f"recorded so far. Next session name: {upcoming}")

    # ----------------------------------------------------------- shutdown
    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._ticker.stop()
        self.status.clear()
        self.status.enabled = False  # plain output from here on
        self.log("Saving and exiting...")
        self.hotkey.stop()
        self.controller.shutdown()   # stops recording and writes everything to the database
        self.store.close()
        self.reader.restore()
        QCoreApplication.quit()


# ---------------------------------------------------------------- helpers
def _prepare_streams() -> None:
    for stream in (sys.stdout, sys.stderr):  # never crash on characters the console can't show
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _install_signal_handlers(console: ConsoleApp) -> None:
    signal.signal(signal.SIGINT, lambda *_: console.quit())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_: console.quit())


def run_console(args, qt_argv: list[str], lock: QLockFile) -> int:
    """Entry point for `python main.py --console`."""
    _prepare_streams()
    # QGuiApplication (not QApplication): no windows, but screen information is available.
    app = QGuiApplication(qt_argv)
    app.setApplicationName(APP_NAME)
    if not lock.tryLock(100):
        print(f"{APP_NAME} is already running (in a window, the tray, or another console).")
        return 1

    prefs = Preferences.load(AppSettings(SETTINGS_PATH))
    store = ClickStore(DB_PATH, BUFFER_PATH)
    controller = RecordingController(store)
    controller.apply_preferences(prefs)
    controller.next_session_name = args.name.strip()

    console = ConsoleApp(store, controller, prefs, verbose=args.verbose)
    _install_signal_handlers(console)
    QTimer.singleShot(0, lambda: console.start(auto_start=args.start))
    return app.exec()


def attach_console(store: ClickStore, controller: RecordingController, prefs: Preferences) -> ConsoleApp:
    """Continue in the terminal after the window was closed ("Switch to Console Mode").
    The same store and controller are reused, so a recording in progress keeps going."""
    global _active_console
    _prepare_streams()
    console = ConsoleApp(store, controller, prefs)
    _install_signal_handlers(console)
    console.start(switched=True)
    _active_console = console
    return console
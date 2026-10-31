"""Open console mode in a new terminal window (used when the window app has no terminal)."""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import BASE_DIR

_LINUX_TERMINALS = (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"),
                    ("xfce4-terminal", "-x"), ("xterm", "-e"))


def console_command(start: bool = False, name: str = "") -> list[str]:
    """The command that starts this app in console mode."""
    python = Path(sys.executable)
    if sys.platform == "win32" and python.name.lower() == "pythonw.exe":
        candidate = python.with_name("python.exe")  # pythonw has no console
        if candidate.exists():
            python = candidate
    cmd = [str(python), str(BASE_DIR / "main.py"), "--console"]
    if start:
        cmd.append("--start")
    if name:
        cmd += ["--name", name]
    return cmd


def _linux_terminal() -> list[str] | None:
    for exe, flag in _LINUX_TERMINALS:
        if shutil.which(exe):
            return [exe, flag]
    return None


def can_open_terminal() -> bool:
    if sys.platform in ("win32", "darwin"):
        return True
    return _linux_terminal() is not None


def open_in_new_terminal(cmd: list[str]) -> None:
    if sys.platform == "win32":
        subprocess.Popen(cmd, cwd=str(BASE_DIR), creationflags=subprocess.CREATE_NEW_CONSOLE)
    elif sys.platform == "darwin":
        shell_cmd = f"cd {shlex.quote(str(BASE_DIR))} && {shlex.join(cmd)}"
        escaped = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript",
                          "-e", f'tell application "Terminal" to do script "{escaped}"',
                          "-e", 'tell application "Terminal" to activate'])
    else:
        subprocess.Popen([*_linux_terminal(), *cmd], cwd=str(BASE_DIR))
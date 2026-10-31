"""System-wide idle time: seconds since the last keyboard or mouse input."""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
from typing import Callable

FALLBACK_DESCRIPTION = "not available here (using time since your last click instead)"


class IdleDetector:
    def __init__(self):
        self._impl: Callable[[], float | None] | None = None
        self.method = FALLBACK_DESCRIPTION
        try:
            if sys.platform == "win32":
                self._impl, name = self._windows(), "Windows (GetLastInputInfo)"
            elif sys.platform == "darwin":
                self._impl, name = self._macos(), "macOS (CoreGraphics)"
            else:
                self._impl, name = self._x11(), "X11 (XScreenSaver extension)"
            if self.idle_seconds() is None:
                raise OSError("idle query returned nothing")
            self.method = name
        except Exception:
            self._impl = None

    @property
    def available(self) -> bool:
        return self._impl is not None

    def idle_seconds(self) -> float | None:
        if self._impl is None:
            return None
        try:
            value = self._impl()
        except Exception:
            return None
        return None if value is None else float(value)

    # ------------------------------------------------------------ backends
    @staticmethod
    def _windows():
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        user32 = ctypes.WinDLL("user32")
        kernel32 = ctypes.WinDLL("kernel32")
        user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
        user32.GetLastInputInfo.restype = wintypes.BOOL
        kernel32.GetTickCount.restype = wintypes.DWORD
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)

        def idle():
            if not user32.GetLastInputInfo(ctypes.byref(info)):
                return None
            # Both values are 32-bit tick counts; mask handles the 49-day wraparound.
            return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
        return idle

    @staticmethod
    def _macos():
        path = (ctypes.util.find_library("ApplicationServices")
                or "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib = ctypes.cdll.LoadLibrary(path)
        fn = lib.CGEventSourceSecondsSinceLastEventType
        fn.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        fn.restype = ctypes.c_double
        hid_system_state, any_input_event = 1, 0xFFFFFFFF
        return lambda: fn(hid_system_state, any_input_event)

    @staticmethod
    def _x11():
        class XScreenSaverInfo(ctypes.Structure):
            _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int),
                        ("kind", ctypes.c_int), ("til_or_since", ctypes.c_ulong),
                        ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]

        xlib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        xss = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xss") or "libXss.so.1")
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        xlib.XDefaultRootWindow.restype = ctypes.c_ulong
        xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
        xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                              ctypes.POINTER(XScreenSaverInfo)]
        xss.XScreenSaverQueryInfo.restype = ctypes.c_int

        display = xlib.XOpenDisplay(None)
        if not display:
            raise OSError("cannot open X display")
        root = xlib.XDefaultRootWindow(display)
        info = xss.XScreenSaverAllocInfo()

        def idle():
            if not xss.XScreenSaverQueryInfo(display, root, info):
                return None
            return info.contents.idle / 1000.0
        return idle
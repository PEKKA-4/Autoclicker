"""Live Windows input movement test triggered by a hotkey.

This version is meant to be run while you are already in the game. It listens for
F5 and then moves the cursor in a predictable pattern to see whether the game is
accepting the same low-level Windows input events.

Usage:
- Start this script while the game is open.
- Press F5 to begin the test.
- The cursor will move in a short pattern.
- Press F5 again to stop / exit.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from pynput.keyboard import Key, Listener as KeyboardListener

user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


def get_cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def set_cursor_pos(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def send_mouse_move(dx: int, dy: int) -> None:
    event = _Input()
    event.type = 0
    event.union.mi.dx = int(dx)
    event.union.mi.dy = int(dy)
    event.union.mi.mouseData = 0
    event.union.mi.dwFlags = MOUSEEVENTF_MOVE
    event.union.mi.time = 0
    event.union.mi.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


def click_left() -> None:
    event = _Input()
    event.type = 0
    event.union.mi.dx = 0
    event.union.mi.dy = 0
    event.union.mi.mouseData = 0
    event.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
    event.union.mi.time = 0
    event.union.mi.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))
    time.sleep(0.05)

    event = _Input()
    event.type = 0
    event.union.mi.dx = 0
    event.union.mi.dy = 0
    event.union.mi.mouseData = 0
    event.union.mi.dwFlags = MOUSEEVENTF_LEFTUP
    event.union.mi.time = 0
    event.union.mi.dwExtraInfo = None
    user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


class LiveInputTest:
    def __init__(self) -> None:
        self.running = False
        self._lock = threading.Lock()
        self.listener = KeyboardListener(on_press=self._on_key_press)

    def start(self) -> None:
        print("Listening for F5...")
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()

    def _on_key_press(self, key) -> None:
        if key == Key.f5:
            self.running = not self.running
            if self.running:
                print("F5 pressed: test started")
                threading.Thread(target=self._run_pattern, daemon=True).start()
            else:
                print("F5 pressed: test stopped")

    def _run_pattern(self) -> None:
        start_x, start_y = get_cursor_pos()
        print(f"Cursor start: ({start_x}, {start_y})")

        for i in range(30):
            if not self.running:
                return
            dx = 20 if i % 2 == 0 else -20
            dy = 10 if i % 3 == 0 else -10
            send_mouse_move(dx, dy)
            time.sleep(0.05)
            print(f"Tick {i}: {get_cursor_pos()}")

        click_left()
        print(f"Final position: {get_cursor_pos()}")
        self.running = False
        print("Pattern done. Press F5 to run again.")


if __name__ == "__main__":
    print("Live test is ready. Press F5 while the game is focused.")
    LiveInputTest().start()
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exited")

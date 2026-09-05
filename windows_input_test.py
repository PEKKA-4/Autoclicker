"""Minimal Windows input test app.

This script is meant to answer one question: does a normal Windows input API
actually move the cursor in a regular app? If the cursor moves here but not in a
specific game, then the issue is the game's input filtering, not the script.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040


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


def run_test() -> None:
    print("Windows input test app")
    print("======================")
    print("1) Move the mouse over a normal desktop window like Notepad or Paint.")
    print("2) Keep this window focused or let it run in the background.")
    print("3) Press Enter to begin the test.")
    input()

    x, y = get_cursor_pos()
    print(f"Starting cursor position: ({x}, {y})")

    print("Sending SetCursorPos movement...")
    for offset in range(0, 160, 20):
        set_cursor_pos(x + offset, y + (offset // 4))
        time.sleep(0.2)
        print(f"  SetCursorPos -> {get_cursor_pos()}")

    print("Sending relative mouse move events...")
    for _ in range(10):
        send_mouse_move(30, 0)
        time.sleep(0.15)
        print(f"  relative -> {get_cursor_pos()}")

    print("Sending a left click...")
    click_left()
    print(f"After click: {get_cursor_pos()}")

    print("\nIf the cursor moved in Notepad/Paint, then the system input layer is working.")
    print("If the cursor did not move there, then the target app or game is blocking it.")
    print("Press Enter to exit.")
    input()


if __name__ == "__main__":
    run_test()

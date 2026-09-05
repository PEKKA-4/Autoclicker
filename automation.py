"""Automation primitives for auto-clicking, anti-AFK circling and flicking.

Each class runs its own background thread and exposes start()/stop()/toggle().
The thread only does work while `active` is True; otherwise it idles cheaply.
"""

import ctypes
import math
import random
import threading
import time
from ctypes import wintypes

from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Button


# --- Windows-native input layer -------------------------------------------------
# pynput is fine for listening to hotkeys, but the actual cursor/keyboard actions are
# much more reliable when sent through the Windows input API used by desktop apps.

user32 = ctypes.windll.user32

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

KEYEVENTF_KEYDOWN = 0x0000
KEYEVENTF_KEYUP = 0x0002

VK_MAP = {
    "\b": 0x08,
    "\t": 0x09,
    "\n": 0x0D,
    "\r": 0x0D,
    " ": 0x20,
    "!": 0x31,
    '"': 0xDE,
    "#": 0x33,
    "$": 0x34,
    "%": 0x35,
    "&": 0x37,
    "'": 0xDE,
    "(": 0x39,
    ")": 0x30,
    "*": 0x38,
    "+": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    ":": 0xBA,
    ";": 0xBA,
    "<": 0xBC,
    "=": 0xBB,
    ">": 0xBE,
    "?": 0xBF,
    "@": 0x32,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "^": 0x36,
    "_": 0xBD,
    "`": 0xC0,
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
    "{": 0xDB,
    "|": 0xDC,
    "}": 0xDD,
    "~": 0xC0,
}

SPECIAL_KEYS = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps_lock": 0x14,
    "esc": 0x1B,
    "space": 0x20,
    "page_up": 0x21,
    "page_down": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "print_screen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
    "numlock": 0x90,
    "scroll_lock": 0x91,
    "lshift": 0xA0,
    "rshift": 0xA1,
    "lctrl": 0xA2,
    "rctrl": 0xA3,
    "lalt": 0xA4,
    "ralt": 0xA5,
}


class _KeyInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


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
    _fields_ = [("mi", _MouseInput), ("ki", _KeyInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


def _get_vk_code(key) -> int:
    if isinstance(key, str):
        normalized = key.strip().lower()
        if normalized in SPECIAL_KEYS:
            return SPECIAL_KEYS[normalized]
        if normalized in VK_MAP:
            return VK_MAP[normalized]
        if len(normalized) == 1:
            ch = normalized
            if ch.isalpha():
                return ord(ch.upper())
            if ch in VK_MAP:
                return VK_MAP[ch]
        raise ValueError(f"Unsupported key: {key!r}")

    if hasattr(key, "value"):
        value = str(key.value)
        if value.startswith("Key."):
            return _get_vk_code(value.split(".", 1)[1])
        if len(value) == 1:
            return _get_vk_code(value)

    if hasattr(key, "char") and key.char:
        return _get_vk_code(key.char)

    name = str(key).replace("Key.", "").lower()
    if name in SPECIAL_KEYS:
        return SPECIAL_KEYS[name]
    raise ValueError(f"Unsupported key: {key!r}")


def _send_keyboard_event(vk: int, down: bool) -> None:
    event = _Input(INPUT_KEYBOARD, _InputUnion())
    event.union.ki.wVk = vk
    event.union.ki.wScan = 0
    event.union.ki.dwFlags = KEYEVENTF_KEYUP if not down else KEYEVENTF_KEYDOWN
    event.union.ki.time = 0
    event.union.ki.dwExtraInfo = None
    ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


def _mouse_event(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
    event = _Input(INPUT_MOUSE, _InputUnion())
    event.union.mi.dx = dx
    event.union.mi.dy = dy
    event.union.mi.mouseData = data
    event.union.mi.dwFlags = flags
    event.union.mi.time = 0
    event.union.mi.dwExtraInfo = None
    ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(event))


class WinMouseController:
    def __init__(self) -> None:
        self._position = self._read_position()

    @staticmethod
    def _read_position() -> tuple[int, int]:
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return int(pt.x), int(pt.y)

    @property
    def position(self) -> tuple[int, int]:
        return self._read_position()

    @position.setter
    def position(self, value: tuple[int, int]) -> None:
        x, y = value
        current_x, current_y = self._read_position()
        dx = int(x - current_x)
        dy = int(y - current_y)
        _mouse_event(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
        self._position = (int(x), int(y))

    def move(self, dx: int, dy: int) -> None:
        _mouse_event(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
        self._position = self._read_position()

    def click(self, button: Button) -> None:
        self.press(button)
        self.release(button)

    def press(self, button: Button) -> None:
        if button == Button.left:
            _mouse_event(MOUSEEVENTF_LEFTDOWN)
        elif button == Button.right:
            _mouse_event(MOUSEEVENTF_RIGHTDOWN)
        elif button == Button.middle:
            _mouse_event(MOUSEEVENTF_MIDDLEDOWN)

    def release(self, button: Button) -> None:
        if button == Button.left:
            _mouse_event(MOUSEEVENTF_LEFTUP)
        elif button == Button.right:
            _mouse_event(MOUSEEVENTF_RIGHTUP)
        elif button == Button.middle:
            _mouse_event(MOUSEEVENTF_MIDDLEUP)


class WinKeyboardController:
    def press(self, key) -> None:
        _send_keyboard_event(_get_vk_code(key), True)

    def release(self, key) -> None:
        _send_keyboard_event(_get_vk_code(key), False)


class Toggleable:
    """Base class for a background loop that can be started, stopped and
    toggled active/inactive. Subclasses implement `_tick()` for one unit of
    work and may override `_on_toggle()` to react to state changes.
    """

    def __init__(self, step: float = 0.05) -> None:
        self._step = step
        self._running = False
        self._active = False
        self._paused = False
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @property
    def active(self) -> bool:
        return self._active

    def start(self) -> None:
        self._running = True
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def toggle(self) -> None:
        self._active = not self._active
        self._on_toggle()

    def pause(self) -> None:
        """Temporarily suspends ticking without changing the active toggle
        state — used to let another automation borrow the mouse briefly.
        """
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def _on_toggle(self) -> None:
        """Hook for subclasses, called right after active state flips."""

    def _tick(self) -> None:
        """Subclasses implement one unit of work while active. Must not
        block for longer than necessary, so toggling off stays responsive.
        """
        raise NotImplementedError

    def _loop(self) -> None:
        while self._running:
            if self._active and not self._paused:
                self._tick()
            else:
                time.sleep(self._step)


class AutoClicker(Toggleable):
    def __init__(self, clicks_per_second: float) -> None:
        super().__init__()
        self._mouse = WinMouseController()
        self.set_cps(clicks_per_second)

    def set_cps(self, clicks_per_second: float) -> None:
        clicks_per_second = max(clicks_per_second, 0.1)
        self._interval = 1.0 / clicks_per_second

    def _tick(self) -> None:
        self._mouse.click(Button.left)
        time.sleep(self._interval)


class CircleMover(Toggleable):
    """Moves the cursor in a short left/right/upward drift pattern.

    This matches the verified Windows input behavior from the live test script and
    keeps the cursor moving in a steady anti-AFK pattern without large jumps.
    """

    def __init__(self, radius: float = 15, speed: float = 2.0) -> None:
        super().__init__()
        self._radius = radius
        self._speed = speed
        self._mouse = WinMouseController()
        self._angle = 0.0
        self._center = (0, 0)
        self._direction = 1

    def _on_toggle(self) -> None:
        if self._active:
            self._center = self._mouse.position
            self._angle = 0.0
            self._direction = 1

    def _tick(self) -> None:
        # Match the proven live-test logic: a short relative drift using the same
        # Windows SendInput path that worked in-game.
        step_count = int(self._angle)
        dx = 20 if step_count % 2 == 0 else -20
        dy = -10 if step_count % 2 == 0 else -5
        self._mouse.move(dx, dy)
        self._angle += 1
        time.sleep(self._step)


class FlickMover(Toggleable):
    """Every `interval_seconds`, flicks the mouse to a captured point, clicks,
    then moves back to the position it had right before the flick.

    The flick point is absolute screen coordinates, set via
    `capture_current_position()` — call that while the cursor is wherever you
    want the flick to land (e.g. bound to a hotkey).
    """

    def __init__(
        self,
        interval_seconds: float = 60.0,
        move_steps: int = 10,
        move_delay: float = 0.01,
    ) -> None:
        super().__init__()
        self._mouse = WinMouseController()
        self._elapsed = 0.0
        self._flick_point: tuple[int, int] | None = None
        self._clicker_to_pause: AutoClicker | None = None
        self._move_steps = move_steps
        self._move_delay = move_delay
        self._last_flick_info = "not fired yet"
        self.set_interval(interval_seconds)

    def set_interval(self, interval_seconds: float) -> None:
        self._interval = max(interval_seconds, 1.0)

    @property
    def flick_point(self) -> tuple[int, int] | None:
        return self._flick_point

    @property
    def last_flick_info(self) -> str:
        return self._last_flick_info

    def capture_current_position(self) -> None:
        self._flick_point = self._mouse.position
        print(f"Flick point captured: {self._flick_point}")

    def attach_clicker(self, clicker: AutoClicker) -> None:
        """Pause this AutoClicker for the duration of each flick, so it
        can't sneak in extra clicks at the flick point while the cursor
        is there. Purely optional — flicking still works without it.
        """
        self._clicker_to_pause = clicker

    def _on_toggle(self) -> None:
        self._elapsed = 0.0  # restart the countdown whenever (de)activated

    def _tick(self) -> None:
        time.sleep(self._step)
        self._elapsed += self._step
        if self._elapsed >= self._interval:
            self._flick()
            self._elapsed = 0.0

    def _move_smooth(self, target: tuple[int, int]) -> None:
        """Moves the cursor to `target` in a series of relative mouse moves.

        This matches the verified in-game behavior: a sequence of smaller Windows
        input events is accepted more reliably than a single absolute jump.
        """
        start_x, start_y = self._mouse.position
        target_x, target_y = target
        for step in range(1, self._move_steps + 1):
            t = step / self._move_steps
            dx = int((target_x - start_x) * t) - int((target_x - start_x) * (step - 1) / self._move_steps)
            dy = int((target_y - start_y) * t) - int((target_y - start_y) * (step - 1) / self._move_steps)
            self._mouse.move(dx, dy)
            time.sleep(self._move_delay)

    def _flick(self) -> None:
        timestamp = time.strftime("%H:%M:%S")

        if self._flick_point is None:
            self._last_flick_info = f"{timestamp}: skipped, no point captured"
            print(f"Flick skipped: no point captured yet ({timestamp})")
            return

        if self._clicker_to_pause is not None:
            self._clicker_to_pause.pause()
            # Give an already-started click time to finish before we move
            # the cursor away, otherwise it could land at the flick point.
            time.sleep(0.1)

        origin = self._mouse.position
        print(f"Flicking: {origin} -> {self._flick_point} ({timestamp})")
        self._move_smooth(self._flick_point)
        self._mouse.click(Button.left)
        self._move_smooth(origin)
        self._last_flick_info = f"{timestamp}: {origin} -> {self._flick_point}"
        print(f"Flick done, back at {self._mouse.position}")

        if self._clicker_to_pause is not None:
            self._clicker_to_pause.resume()


class AntiAFKStepper(Toggleable):
    """Anti-AFK-kick nudge: taps one key briefly, then the opposite key,
    right after each other (e.g. S then W). Net position stays ~unchanged,
    but the server still sees movement, which is enough to reset most
    AFK-kick timers without actually walking you anywhere.

    Keys are configurable (default W/S) so this also works as A/D, or any
    other opposing pair. Interval has random jitter so the timing doesn't
    look like a fixed, obviously-automated pattern.
    """

    def __init__(
        self,
        back_key: str = "s",
        forward_key: str = "w",
        interval_seconds: float = 45.0,
        jitter_seconds: float = 15.0,
        tap_duration: float = 0.05,
    ) -> None:
        super().__init__()
        self._keyboard = WinKeyboardController()
        self._elapsed = 0.0
        self._last_step_info = "not fired yet"
        self._tap_duration = max(tap_duration, 0.01)
        self.set_keys(back_key, forward_key)
        self.set_interval(interval_seconds, jitter_seconds)

    def set_keys(self, back_key: str, forward_key: str) -> None:
        back_key = (back_key or "").strip().lower()
        forward_key = (forward_key or "").strip().lower()
        if not back_key or not forward_key:
            raise ValueError("Both keys must be non-empty single characters")
        self._back_key = back_key[0]
        self._forward_key = forward_key[0]

    def set_interval(self, interval_seconds: float, jitter_seconds: float = 0.0) -> None:
        self._interval = max(interval_seconds, 1.0)
        # Jitter can't exceed the interval itself, or we could roll <= 0.
        self._jitter = max(min(jitter_seconds, self._interval - 1.0), 0.0)
        self._next_interval = self._roll_interval()

    @property
    def keys(self) -> tuple[str, str]:
        return self._back_key, self._forward_key

    @property
    def last_step_info(self) -> str:
        return self._last_step_info

    def _roll_interval(self) -> float:
        return self._interval + random.uniform(-self._jitter, self._jitter)

    def _on_toggle(self) -> None:
        self._elapsed = 0.0  # restart the countdown whenever (de)activated
        self._next_interval = self._roll_interval()

    def _tick(self) -> None:
        time.sleep(self._step)
        self._elapsed += self._step
        if self._elapsed >= self._next_interval:
            self._step_back_and_forward()
            self._elapsed = 0.0
            self._next_interval = self._roll_interval()

    def _tap(self, key: str) -> None:
        self._keyboard.press(key)
        time.sleep(self._tap_duration)
        self._keyboard.release(key)

    def _step_back_and_forward(self) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self._tap(self._back_key)
        time.sleep(self._tap_duration)
        self._tap(self._forward_key)
        self._last_step_info = (
            f"{timestamp}: {self._back_key.upper()} -> {self._forward_key.upper()}"
        )
        print(
            f"Anti-AFK step: {self._back_key.upper()} then "
            f"{self._forward_key.upper()} ({timestamp})"
        )
import json
from dataclasses import asdict, dataclass

from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener
from pynput.mouse import Listener as MouseListener


@dataclass
class SequenceEvent:
    action: str
    control: str
    delay: float
    x: int | None = None
    y: int | None = None


class SequenceRecorder:
    """Records keyboard + mouse events with exact inter-event timing.

    Not a Toggleable: it's event-driven (pynput listeners), not part of the
    _tick() polling loop. `ignored_keys` should contain whatever hotkey(s)
    start/stop the recording itself, so they don't end up inside the
    recorded sequence.
    """

    def __init__(
        self,
        ignored_keys: set[Key] | None = None,
        min_move_distance: float = 0.0,
    ) -> None:
        self.events: list[SequenceEvent] = []
        self._ignored_keys = ignored_keys or set()
        self._min_move_distance = min_move_distance
        self._last_pos: tuple[float, float] | None = None
        self._record_origin: tuple[float, float] | None = None
        self._last_time: float | None = None
        self._recording = False
        self._lock = threading.Lock()
        self._kb_listener: KeyboardListener | None = None
        self._mouse_listener: MouseListener | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._recording:
            return
        self.events.clear()
        self._last_time = None
        self._last_pos = None
        self._record_origin = None
        self._recording = True
        self._kb_listener = KeyboardListener(
            on_press=lambda k: self._record_key("key_down", k),
            on_release=lambda k: self._record_key("key_up", k),
        )
        self._mouse_listener = MouseListener(on_click=self._on_click, on_move=self._on_move)
        self._kb_listener.start()
        self._mouse_listener.start()

    def stop(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._kb_listener:
            self._kb_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()

    def _record_key(self, action: str, key) -> None:
        if key in self._ignored_keys:
            return
        control = key.char if isinstance(key, KeyCode) and key.char else str(key).replace("Key.", "")
        self._append(action, control)

    def _on_click(self, x: int, y: int, button: Button, pressed: bool) -> None:
        self._last_pos = (x, y)
        self._append("mouse_down" if pressed else "mouse_up", button.name, x=0, y=0)

    def _on_move(self, x: int, y: int) -> None:
        if self._last_pos is None:
            self._last_pos = (x, y)
            self._record_origin = (x, y)
            return

        dx = x - self._last_pos[0]
        dy = y - self._last_pos[1]
        distance = (dx * dx + dy * dy) ** 0.5
        if self._min_move_distance > 0.0 and distance < self._min_move_distance:
            self._last_pos = (x, y)
            return

        self._last_pos = (x, y)
        # Store the actual delta from the prior pointer position. This is what the
        # working Windows SendInput path expects, instead of trying to replay an
        # absolute coordinate.
        self._append("mouse_move", "", x=int(dx), y=int(dy))

    def _append(self, action: str, control: str, x: int | None = None, y: int | None = None) -> None:
        now = time.perf_counter()
        with self._lock:
            delay = 0.0 if self._last_time is None else now - self._last_time
            self._last_time = now
            self.events.append(SequenceEvent(action, control, delay, x, y))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in self.events], f, indent=2)

    def load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            self.events = [SequenceEvent(**e) for e in json.load(f)]


class SequencePlayer(Toggleable):
    """Replays a recorded sequence, preserving the originally recorded pauses.

    `get_events` is a callable rather than a fixed list so the player always
    plays whatever is currently in the recorder (freshly recorded or loaded
    from disk) without needing to be re-created.
    """

    def __init__(self, get_events, loop: bool = True) -> None:
        # Use a short scheduler step and carry elapsed-time remainder forward so
        # rapid recorded events are replayed without being stretched or skipped.
        super().__init__(step=0.001)
        self._keyboard = WinKeyboardController()
        self._mouse = WinMouseController()
        self._get_events = get_events
        self.loop = loop
        self._movement_scale = 0.50
        self._movement_remainder = [0.0, 0.0]
        self._index = 0
        self._elapsed = 0.0
        self._last_play_info = "not played yet"

    @property
    def last_play_info(self) -> str:
        return self._last_play_info

    def _on_toggle(self) -> None:
        self._index = 0
        self._elapsed = 0.0
        self._movement_remainder = [0.0, 0.0]

    def _tick(self) -> None:
        time.sleep(self._step)
        events = self._get_events()
        if not events:
            return

        self._elapsed += self._step
        while self._index < len(events):
            target = events[self._index]
            if self._elapsed < target.delay:
                break
            self._elapsed -= target.delay
            self._execute(target)
            self._index += 1

        if self._index >= len(events):
            if self.loop:
                self._index = 0
            else:
                self._active = False  # stop after one full pass

    def _execute(self, event: SequenceEvent) -> None:
        if event.action == "key_down":
            self._keyboard.press(self._resolve_key(event.control))
        elif event.action == "key_up":
            self._keyboard.release(self._resolve_key(event.control))
        elif event.action == "mouse_down":
            self._mouse.press(getattr(Button, event.control))
        elif event.action == "mouse_up":
            self._mouse.release(getattr(Button, event.control))
        elif event.action == "mouse_move":
            if event.x is not None and event.y is not None:
                scaled_x = event.x * self._movement_scale + self._movement_remainder[0]
                scaled_y = event.y * self._movement_scale + self._movement_remainder[1]
                move_x = int(scaled_x + (1e-9 if scaled_x >= 0 else -1e-9))
                move_y = int(scaled_y + (1e-9 if scaled_y >= 0 else -1e-9))
                self._movement_remainder[0] = scaled_x - move_x
                self._movement_remainder[1] = scaled_y - move_y
                if move_x or move_y:
                    self._mouse.move(move_x, move_y)
        self._last_play_info = f"{time.strftime('%H:%M:%S')}: {event.action} {event.control}"

    @staticmethod
    def _resolve_key(control: str):
        try:
            return getattr(Key, control)
        except AttributeError:
            return control  # plain character key
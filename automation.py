"""Automation primitives for auto-clicking, anti-AFK circling and flicking.

Each class runs its own background thread and exposes start()/stop()/toggle().
The thread only does work while `active` is True; otherwise it idles cheaply.
"""

import math
import threading
import time

from pynput.mouse import Button, Controller as MouseController


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
        self._mouse = MouseController()
        self.set_cps(clicks_per_second)

    def set_cps(self, clicks_per_second: float) -> None:
        clicks_per_second = max(clicks_per_second, 0.1)
        self._interval = 1.0 / clicks_per_second

    def _tick(self) -> None:
        self._mouse.click(Button.left)
        time.sleep(self._interval)


class CircleMover(Toggleable):
    """Moves the mouse in a small circle around the position it had when
    activated (anti-AFK).
    """

    def __init__(self, radius: float = 15, speed: float = 2.0) -> None:
        super().__init__()
        self._radius = radius
        self._speed = speed
        self._mouse = MouseController()
        self._angle = 0.0
        self._center = (0, 0)

    def _on_toggle(self) -> None:
        if self._active:
            self._center = self._mouse.position
            self._angle = 0.0

    def _tick(self) -> None:
        self._angle += self._speed * self._step
        cx, cy = self._center
        x = cx + self._radius * math.cos(self._angle)
        y = cy + self._radius * math.sin(self._angle)
        self._mouse.position = (x, y)
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
        self._mouse = MouseController()
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
        """Moves the cursor to `target` over several small steps instead of
        one instant jump — easier to see, and some apps only react to a
        series of move events rather than a single teleport.
        """
        start_x, start_y = self._mouse.position
        target_x, target_y = target
        for step in range(1, self._move_steps + 1):
            t = step / self._move_steps
            self._mouse.position = (
                start_x + (target_x - start_x) * t,
                start_y + (target_y - start_y) * t,
            )
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
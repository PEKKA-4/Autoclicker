"""Tkinter control panel for the auto clicker / anti-AFK tool."""

import tkinter as tk
from tkinter import ttk

from pynput.keyboard import Key

from automation import AutoClicker, CircleMover, FlickMover
from hotkeys import start_hotkey_listener

CLICKER_KEY = Key.f6
CIRCLE_KEY = Key.f7
FLICK_KEY = Key.f8
CAPTURE_KEY = Key.f5


class App:
    def __init__(self) -> None:
        self.clicker = AutoClicker(clicks_per_second=10)
        self.mover = CircleMover()
        self.flicker = FlickMover(interval_seconds=60)
        self.flicker.attach_clicker(self.clicker)
        self._exit_requested = False

        self.root = tk.Tk()
        self.root.title("Auto Clicker Control Panel")
        self.root.geometry("320x310")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_widgets()
        self._start_backends()
        self._poll_status()

    # ---- UI ----

    def _build_widgets(self) -> None:
        padding = {"padx": 10, "pady": 6}

        clicker_frame = ttk.LabelFrame(self.root, text=f"Auto Clicker ({self._key_name(CLICKER_KEY)})")
        clicker_frame.pack(fill="x", **padding)

        ttk.Label(clicker_frame, text="Clicks per second:").grid(row=0, column=0, sticky="w")
        self.cps_var = tk.StringVar(value="10")
        ttk.Entry(clicker_frame, textvariable=self.cps_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Button(clicker_frame, text="Apply", command=self._apply_cps).grid(row=0, column=2)

        self.clicker_status = ttk.Label(clicker_frame, text="OFF", foreground="red")
        self.clicker_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        circle_frame = ttk.LabelFrame(self.root, text=f"Anti-AFK Circle ({self._key_name(CIRCLE_KEY)})")
        circle_frame.pack(fill="x", **padding)

        self.circle_status = ttk.Label(circle_frame, text="OFF", foreground="red")
        self.circle_status.pack(anchor="w")

        flick_frame = ttk.LabelFrame(self.root, text=f"Flick Click ({self._key_name(FLICK_KEY)})")
        flick_frame.pack(fill="x", **padding)

        ttk.Label(flick_frame, text="Flick every (seconds):").grid(row=0, column=0, sticky="w")
        self.interval_var = tk.StringVar(value="60")
        ttk.Entry(flick_frame, textvariable=self.interval_var, width=8).grid(row=0, column=1, padx=5)
        ttk.Button(flick_frame, text="Apply", command=self._apply_interval).grid(row=0, column=2)

        self.flick_status = ttk.Label(flick_frame, text="OFF", foreground="red")
        self.flick_status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        self.flick_point_label = ttk.Label(flick_frame, text="Point: not set", foreground="orange")
        self.flick_point_label.grid(row=2, column=0, columnspan=3, sticky="w")

        self.last_flick_label = ttk.Label(flick_frame, text="Last flick: not fired yet", foreground="gray")
        self.last_flick_label.grid(row=3, column=0, columnspan=3, sticky="w")

        ttk.Label(
            flick_frame,
            text=f"Move cursor to target, press {self._key_name(CAPTURE_KEY)} to capture it.",
            wraplength=270,
            foreground="gray",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))

        ttk.Label(
            self.root,
            text="Hotkeys work globally, even outside this window. Esc quits.",
            wraplength=290,
            foreground="gray",
        ).pack(pady=10)

    @staticmethod
    def _key_name(key: Key) -> str:
        return key.name.upper()

    # ---- settings ----

    def _apply_cps(self) -> None:
        try:
            cps = float(self.cps_var.get())
        except ValueError:
            self.cps_var.set("10")
            return
        self.clicker.set_cps(cps)

    def _apply_interval(self) -> None:
        try:
            seconds = float(self.interval_var.get())
        except ValueError:
            self.interval_var.set("60")
            return
        self.flicker.set_interval(seconds)

    # ---- backend wiring ----

    def _start_backends(self) -> None:
        self.clicker.start()
        self.mover.start()
        self.flicker.start()
        self.listener = start_hotkey_listener(
            bindings={
                CLICKER_KEY: self.clicker.toggle,
                CIRCLE_KEY: self.mover.toggle,
                FLICK_KEY: self.flicker.toggle,
                CAPTURE_KEY: self.flicker.capture_current_position,
            },
            on_exit=self._request_exit,
        )

    def _request_exit(self) -> None:
        # Called from the listener thread — only ever flip a flag here.
        # The actual teardown happens on the main thread via _poll_status().
        self._exit_requested = True

    def _poll_status(self) -> None:
        if self._exit_requested:
            self._on_close()
            return
        self._set_status(self.clicker_status, self.clicker.active)
        self._set_status(self.circle_status, self.mover.active)
        self._set_status(self.flick_status, self.flicker.active)
        self._set_flick_point_label()
        self.root.after(150, self._poll_status)

    def _set_flick_point_label(self) -> None:
        point = self.flicker.flick_point
        if point is None:
            self.flick_point_label.config(text="Point: not set", foreground="orange")
        else:
            self.flick_point_label.config(text=f"Point: {point}", foreground="green")
        self.last_flick_label.config(text=f"Last flick: {self.flicker.last_flick_info}")

    @staticmethod
    def _set_status(label: ttk.Label, active: bool) -> None:
        label.config(text="ON" if active else "OFF", foreground="green" if active else "red")

    # ---- lifecycle ----

    def _on_close(self) -> None:
        self.clicker.stop()
        self.mover.stop()
        self.flicker.stop()
        self.listener.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
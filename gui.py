"""Tkinter control panel for the auto clicker / anti-AFK tool."""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from pynput.keyboard import Key

from automation import AntiAFKStepper, AutoClicker, CircleMover, FlickMover, SequencePlayer, SequenceRecorder
from hotkeys import start_hotkey_listener

CLICKER_KEY = Key.f6
CIRCLE_KEY = Key.f7
FLICK_KEY = Key.f8
CAPTURE_KEY = Key.f5
STEPPER_KEY = Key.f4
RECORD_KEY = Key.f10
PLAYBACK_KEY = Key.f11


class App:
    def __init__(self) -> None:
        self.clicker = AutoClicker(clicks_per_second=100)
        self.mover = CircleMover()
        self.flicker = FlickMover(interval_seconds=60)
        self.flicker.attach_clicker(self.clicker)
        self.stepper = AntiAFKStepper(back_key="s", forward_key="w", interval_seconds=45, jitter_seconds=15)
        self.recorder = SequenceRecorder(ignored_keys={RECORD_KEY, PLAYBACK_KEY})
        self.player = SequencePlayer(get_events=lambda: self.recorder.events, loop=True)
        self._exit_requested = False

        self.root = tk.Tk()
        self.root.title("Auto Clicker Control Panel")
        self.root.geometry("330x650")
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
        self.cps_var = tk.StringVar(value="100")
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

        step_frame = ttk.LabelFrame(self.root, text=f"Anti-AFK Movement ({self._key_name(STEPPER_KEY)})")
        step_frame.pack(fill="x", **padding)

        ttk.Label(step_frame, text="Back key:").grid(row=0, column=0, sticky="w")
        self.back_key_var = tk.StringVar(value="s")
        ttk.Entry(step_frame, textvariable=self.back_key_var, width=4).grid(row=0, column=1, sticky="w", padx=5)

        ttk.Label(step_frame, text="Forward key:").grid(row=0, column=2, sticky="w")
        self.forward_key_var = tk.StringVar(value="w")
        ttk.Entry(step_frame, textvariable=self.forward_key_var, width=4).grid(row=0, column=3, sticky="w", padx=5)

        ttk.Label(step_frame, text="Every (s):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.step_interval_var = tk.StringVar(value="45")
        ttk.Entry(step_frame, textvariable=self.step_interval_var, width=6).grid(row=1, column=1, sticky="w", pady=(4, 0))

        ttk.Label(step_frame, text="+/- jitter (s):").grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.step_jitter_var = tk.StringVar(value="15")
        ttk.Entry(step_frame, textvariable=self.step_jitter_var, width=6).grid(row=1, column=3, sticky="w", pady=(4, 0))

        ttk.Button(step_frame, text="Apply", command=self._apply_step_settings).grid(row=2, column=3, sticky="e", pady=(4, 0))

        self.step_status = ttk.Label(step_frame, text="OFF", foreground="red")
        self.step_status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.step_last_label = ttk.Label(step_frame, text="Last step: not fired yet", foreground="gray")
        self.step_last_label.grid(row=3, column=0, columnspan=4, sticky="w")

        ttk.Label(
            step_frame,
            text="Taps back key then forward key on an interval, e.g. S/W or A/D, to dodge AFK kicks without actually moving you.",
            wraplength=270,
            foreground="gray",
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(2, 0))

        # --- Sequence Recorder / Player ---

        seq_frame = ttk.LabelFrame(
            self.root, text=f"Sequence ({self._key_name(RECORD_KEY)} rec, {self._key_name(PLAYBACK_KEY)} play)"
        )
        seq_frame.pack(fill="x", **padding)

        self.record_status = ttk.Label(seq_frame, text="REC: OFF", foreground="red")
        self.record_status.grid(row=0, column=0, sticky="w")

        self.seq_count_label = ttk.Label(seq_frame, text="0 events", foreground="gray")
        self.seq_count_label.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(seq_frame, text="Loop", variable=self.loop_var, command=self._apply_loop).grid(
            row=0, column=2, sticky="e"
        )

        self.player_status = ttk.Label(seq_frame, text="PLAY: OFF", foreground="red")
        self.player_status.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.player_last_label = ttk.Label(seq_frame, text="Last: not played yet", foreground="gray")
        self.player_last_label.grid(row=2, column=0, columnspan=3, sticky="w")

        ttk.Button(seq_frame, text="Save...", command=self._save_sequence).grid(row=3, column=0, pady=(4, 0), sticky="w")
        ttk.Button(seq_frame, text="Load...", command=self._load_sequence).grid(row=3, column=1, pady=(4, 0), sticky="w")

        ttk.Label(
            seq_frame,
            text="Records key presses and mouse clicks with their exact original pauses, then replays them on a loop.",
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

    def _apply_step_settings(self) -> None:
        try:
            self.stepper.set_keys(self.back_key_var.get(), self.forward_key_var.get())
        except ValueError:
            self.back_key_var.set("s")
            self.forward_key_var.set("w")
            return
        try:
            interval = float(self.step_interval_var.get())
            jitter = float(self.step_jitter_var.get())
        except ValueError:
            self.step_interval_var.set("45")
            self.step_jitter_var.set("15")
            return
        self.stepper.set_interval(interval, jitter)

    def _apply_loop(self) -> None:
        self.player.loop = self.loop_var.get()

    # ---- sequence recorder / player ----

    def _toggle_recording(self) -> None:
        if self.player.active:
            return  # don't record while a sequence is actively being played back
        if self.recorder.is_recording:
            self.recorder.stop()
        else:
            self.recorder.start()

    def _toggle_playback(self) -> None:
        if self.recorder.is_recording:
            return  # don't play while still recording
        self.player.toggle()

    def _save_sequence(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.recorder.save(path)
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))

    def _load_sequence(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.recorder.load(path)
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Load failed", str(exc))

    # ---- backend wiring ----

    def _start_backends(self) -> None:
        self.clicker.start()
        self.mover.start()
        self.flicker.start()
        self.stepper.start()
        self.player.start()
        self.listener = start_hotkey_listener(
            bindings={
                CLICKER_KEY: self.clicker.toggle,
                CIRCLE_KEY: self.mover.toggle,
                FLICK_KEY: self.flicker.toggle,
                CAPTURE_KEY: self.flicker.capture_current_position,
                STEPPER_KEY: self.stepper.toggle,
                RECORD_KEY: self._toggle_recording,
                PLAYBACK_KEY: self._toggle_playback,
            },
            on_exit=self._request_exit,
        )

    def _request_exit(self) -> None:
        self._exit_requested = True

    def _poll_status(self) -> None:
        if self._exit_requested:
            self._on_close()
            return
        self._set_status(self.clicker_status, self.clicker.active)
        self._set_status(self.circle_status, self.mover.active)
        self._set_status(self.flick_status, self.flicker.active)
        self._set_flick_point_label()
        self._set_status(self.step_status, self.stepper.active)
        self.step_last_label.config(text=f"Last step: {self.stepper.last_step_info}")

        self.record_status.config(
            text="REC: ON" if self.recorder.is_recording else "REC: OFF",
            foreground="green" if self.recorder.is_recording else "red",
        )
        self.seq_count_label.config(text=f"{len(self.recorder.events)} events")
        self.player_status.config(
            text="PLAY: ON" if self.player.active else "PLAY: OFF",
            foreground="green" if self.player.active else "red",
        )
        self.player_last_label.config(text=f"Last: {self.player.last_play_info}")

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
        self.stepper.stop()
        self.player.stop()
        if self.recorder.is_recording:
            self.recorder.stop()
        self.listener.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
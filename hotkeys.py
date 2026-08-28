"""Global hotkey listener that runs in its own background thread."""

from typing import Callable, Dict

from pynput.keyboard import Key, Listener as KeyboardListener


def start_hotkey_listener(
    bindings: Dict[Key, Callable[[], None]], on_exit: Callable[[], None]
) -> KeyboardListener:
    """Starts a non-blocking global keyboard listener.

    `bindings` maps a Key to a zero-arg callback triggered on press.
    `on_exit` is called once when Esc is pressed; the listener then stops itself.
    """

    def on_press(key):
        if key in bindings:
            bindings[key]()
        elif key == Key.esc:
            on_exit()
            return False  # stops the listener

    listener = KeyboardListener(on_press=on_press)
    listener.start()  # non-blocking, runs in its own thread
    return listener
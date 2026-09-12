"""Exercise native command delivery while every simulator window is hidden."""

import ctypes
import os
import time
import tkinter as tk
from unittest.mock import patch

from doors_ransom import GLOBAL_COMMAND_HOTKEYS, WM_HOTKEY, RansomSimulator


def wait_until(root, condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise AssertionError("Native hotkey command was not delivered")
        root.update()
        time.sleep(0.005)


def main():
    if os.name != "nt":
        print("HOTKEY TEST SKIPPED: Windows only")
        return
    root = tk.Tk()
    root.withdraw()
    app = RansomSimulator(root, enable_global_hotkeys=True,
                          enable_shell_effects=False, use_saved_settings=False)
    listener = app.global_hotkey_thread
    user32 = ctypes.windll.user32
    user32.PostThreadMessageW.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                         ctypes.c_size_t, ctypes.c_ssize_t]
    user32.PostThreadMessageW.restype = ctypes.c_bool
    try:
        assert app.global_hotkey_ready.wait(2.0), "Hotkey registration stalled"
        missing = set(GLOBAL_COMMAND_HOTKEYS) - app.global_hotkey_registered_ids
        assert not missing, f"Hotkey combinations could not be registered: {missing}"
        assert not root.winfo_viewable(), "Test must run without simulator focus"

        def deliver(command_id):
            _command, modifiers, virtual_key = GLOBAL_COMMAND_HOTKEYS[command_id]
            assert user32.PostThreadMessageW(
                app.global_hotkey_thread_id, WM_HOTKEY, command_id,
                (virtual_key << 16) | (modifiers & 0xFFFF)), "PostThreadMessageW failed"

        # Send the same native messages Windows supplies to the registered
        # worker. No real keyboard/mouse events or unrelated windows are used.
        for command_id, (command, _modifiers, _key) in GLOBAL_COMMAND_HOTKEYS.items():
            if command == "test":
                app.armed = True
                app.stage = "waiting"
                with patch.object(app, "_show_intro") as show_intro:
                    deliver(command_id)
                    wait_until(root, lambda: show_intro.call_count == 1)
                assert app.armed
            elif command == "restore":
                app.stage = "ransom"
                app.note_window = tk.Toplevel(root)
                app.note_window.withdraw()
                old_note = app.note_window
                deliver(command_id)
                wait_until(root, lambda: app.stage == "waiting")
                assert app.armed and not app._closing
                assert not old_note.winfo_exists(), "Minus left an encounter window"
            else:
                # Verify every asterisk layout routes to quit. Close for real
                # below so we can also verify the registration cleanup.
                with patch.object(app, "quit_app") as quit_app:
                    deliver(command_id)
                    wait_until(root, lambda: quit_app.call_count == 1)

        exit_id = next(key for key, entry in GLOBAL_COMMAND_HOTKEYS.items() if entry[0] == "exit")
        deliver(exit_id)
        wait_until(root, lambda: app._closing)
        assert not listener.is_alive(), "Asterisk left the hotkey worker running"
        assert not app.global_hotkey_registered_ids, "Exit left registered hotkeys"
        assert not app.after_ids and app.global_hotkey_after_id is None

        # Another process/thread must be able to claim every key after exit.
        registered = []
        try:
            for command_id, (_command, modifiers, virtual_key) in GLOBAL_COMMAND_HOTKEYS.items():
                assert user32.RegisterHotKey(None, command_id, modifiers, virtual_key)
                registered.append(command_id)
        finally:
            for command_id in registered:
                user32.UnregisterHotKey(None, command_id)
        print("HOTKEY TEST OK: hidden + trigger, - restore, all * layouts, complete exit and key release")
    finally:
        app.quit_app()


if __name__ == "__main__":
    main()

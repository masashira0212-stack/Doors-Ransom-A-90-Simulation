"""Regressions for the game's own backdrop covering its native popups."""

import ctypes
import time
import tkinter as tk

from doors_ransom import RansomSimulator


user32 = ctypes.windll.user32
user32.GetParent.argtypes = [ctypes.c_void_p]
user32.GetParent.restype = ctypes.c_void_p
user32.GetTopWindow.argtypes = [ctypes.c_void_p]
user32.GetTopWindow.restype = ctypes.c_void_p
user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetWindow.restype = ctypes.c_void_p
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsIconic.argtypes = [ctypes.c_void_p]
user32.GetForegroundWindow.restype = ctypes.c_void_p


def hwnd(window):
    child = window.winfo_id()
    return int(user32.GetParent(child) or child)


def ranks():
    result = {}
    current = user32.GetTopWindow(None)
    while current and int(current) not in result and len(result) < 4096:
        result[int(current)] = len(result)
        current = user32.GetWindow(current, 2)  # GW_HWNDNEXT
    return result


def pump(root, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.004)


def assert_visible(app):
    z = ranks()
    backgrounds = [app.desktop_overlay, app.taskbar_overlay]
    controls = [app.note_window] + [r["window"] for r in app.glitch_windows]
    controls += [r["window"] for r in app.coin_windows.values()]
    for window in controls:
        handle = hwnd(window)
        assert user32.IsWindowVisible(handle) and not user32.IsIconic(handle), "game window stayed hidden"
        for background in backgrounds:
            assert z[handle] < z[hwnd(background)], "opaque background covered a game window"
    assert float(app.note_window.attributes("-alpha")) == 1.0, "payment note became transparent"


def main():
    root = tk.Tk()
    root.withdraw()
    app = RansomSimulator(root, enable_shell_effects=True, use_saved_settings=False)
    app.volume_var.set(0)
    app.audio.set_volume(0)
    try:
        app.start_ransom_preview()
        pump(root, 0.1)
        assert_visible(app)
        app.desktop_overlay.lift()  # perturb only a test-owned window
        root.update_idletasks()
        z = ranks()
        print("REPRO: backdrop above RANSOM =", z[hwnd(app.desktop_overlay)] < z[hwnd(app.note_window)], flush=True)
        foreground = user32.GetForegroundWindow()
        pump(root, 0.3)
        assert_visible(app)
        assert user32.GetForegroundWindow() == foreground, "repair stole keyboard focus"

        # Missed hide/minimize notification must recover too.
        app.note_window.unbind("<Unmap>")
        app.note_window.withdraw()
        app.note_window.attributes("-alpha", 0.0)
        popup = app.glitch_windows[0]
        popup["window"].unbind("<Unmap>")
        popup["window"].withdraw()
        pump(root, 0.3)
        assert_visible(app)
        assert app.note_window.state() == "normal", "Tk note state did not follow the native restore"
        assert popup["window"].state() == "normal", "Tk popup state did not follow the native restore"
        # Losing topmost status is different from becoming unmapped.
        app.note_window.attributes("-topmost", False)
        pump(root, 0.3)
        assert_visible(app)
        app._move_note_window()
        pump(root, 0.15)
        assert_visible(app)

        # Intentional fade remains intact; a fresh replacement appears.
        fading = app.glitch_windows[0]
        fading["next_toggle"] = time.monotonic() - 1
        pump(root, 0.08)
        assert 0 < float(fading["window"].attributes("-alpha")) < 1, "visibility repair cancelled the intended fade"
        pump(root, 0.6)
        assert fading not in app.glitch_windows
        assert len(app.glitch_windows) == app.glitch_window_target
        assert_visible(app)

        app.restore_and_continue()
        pump(root, 0.3)
        assert app.note_window is None and app.desktop_overlay is None
        assert not app.glitch_windows, "visibility watchdog resurrected a finished encounter"
        print("VISIBILITY OK: background ordering, hidden-window recovery, fades, focus, and cleanup")
    finally:
        app.quit_app()


if __name__ == "__main__":
    main()

"""Coin dragging and payment must not jitter or restack the whole game visibly."""

import ctypes
from dataclasses import replace
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

from doors_ransom import RansomSimulator
from visibility_test import assert_visible, hwnd, pump, user32


class RECT(ctypes.Structure):
    _fields_ = [(name, ctypes.c_long) for name in ("left", "top", "right", "bottom")]


def position(window):
    rect = RECT()
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
    if not user32.GetWindowRect(hwnd(window), ctypes.byref(rect)):
        raise AssertionError("Cannot read test coin bounds")
    return rect.left, rect.top


def main():
    root = tk.Tk()
    root.withdraw()
    app = RansomSimulator(root, enable_shell_effects=True, use_saved_settings=False)
    app.settings = replace(app.settings, honeypot_chance_percent=0)
    app.volume_var.set(0)
    app.audio.set_volume(0)
    try:
        app.start_ransom_preview()
        pump(root, 0.1)
        app._cancel_callbacks()
        scheduled = []
        # Exercise the drag coalescer deterministically, without moving the
        # user's real pointer or relying on an unrelated watchdog tick.
        with patch.object(app, "_later", side_effect=lambda delay, callback: scheduled.append((delay, callback))):
            coin_id, coin = next(iter(app.coin_windows.items()))
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            assert get_style(hwnd(coin["window"]), -20) & 0x08000000, "coin can activate on click"
            assert coin["canvas"].bind("<B1-Motion>"), "coin does not receive direct drag motion"
            foreground = user32.GetForegroundWindow()
            app._begin_coin_drag(coin_id, SimpleNamespace(x_root=coin["x"] + 6, y_root=coin["y"] + 6))
            assert root.grab_current() is coin["canvas"]
            token = coin["motion_generation"]
            with patch.object(app, "_coin_pointer_position", return_value=(coin["x"] + 6, coin["y"] + 6)), \
                 patch.object(app, "_coin_hits_note", return_value=True):
                app._animate_coin_drag(coin_id, token)
                assert app.balance == 500 and coin_id in app.coin_windows, "a press without dragging paid a coin"
            with patch.object(app, "_coin_hits_note", return_value=False):
                # Many queued motion events must collapse into one native move
                # using the newest pointer position. This keeps the coin under
                # a fast cursor without flooding SetWindowPos calls.
                with patch.object(app, "_move_coin_window", wraps=app._move_coin_window) as move:
                    for step in range(32):
                        x, y = 140.0 + step * 5, 240.0 + step * 2
                        result = app._queue_coin_drag_motion(
                            coin_id, SimpleNamespace(x_root=x + 6, y_root=y + 6)
                        )
                        assert result == "break", "drag motion did not remain captured"
                    assert coin["drag_apply_pending"], "drag motion was not queued"
                    root.update()
                    assert position(coin["window"]) == (round(x), round(y)), "coin did not use the newest pointer position"
                    assert move.call_count == 1, "drag motion was not coalesced"
                    # A stationary cursor causes no redundant native move.
                    app._queue_coin_drag_motion(coin_id, SimpleNamespace(x_root=x + 6, y_root=y + 6))
                    root.update()
                    assert move.call_count == 1, "stationary coin jittered"
                with patch.object(app, "_restack_ransom_windows", wraps=app._restack_ransom_windows) as batch:
                    app._repair_ransom_visibility()
                    assert batch.call_count == 0, "dragging rebuilt the popup stack"
                    assert app.ransom_stack_repair_deferred, "drag did not defer visibility repair"
                app._animate_coin_drag(coin_id, token - 1)
                assert not coin["drag_apply_pending"], "stale drag callback restarted work"
            assert_visible(app)
            assert user32.GetForegroundWindow() == foreground, "drag stole focus"

            popups = [app.note_window] + [r["window"] for r in app.glitch_windows]
            original_handles = [hwnd(window) for window in popups]
            # Payment must repair immediately, not after the 100ms poll.
            app.desktop_overlay.lift()
            root.update_idletasks()
            with patch.object(app, "_raise_without_activation", wraps=app._raise_without_activation) as raise_one, \
                 patch.object(app, "_restack_ransom_windows", wraps=app._restack_ransom_windows) as batch:
                app._collect_coin(coin_id)
                assert batch.call_count == 1, "payment did not atomically restore the game stack"
                assert raise_one.call_count == 0, "payment exposed sequentially raised windows"
            assert coin_id not in app.coin_windows and len(app.retiring_coin_windows) == 1
            retiring = app.retiring_coin_windows[0]
            assert float(retiring["window"].attributes("-alpha")) == 0.0
            retire_callbacks = [callback for delay, callback in scheduled if delay == app.COIN_RETIRE_DELAY_MS]
            assert len(retire_callbacks) == 1, "payment did not defer coin destruction"
            retire_callbacks[0]()
            assert not app.retiring_coin_windows
            assert root.grab_current() is None
            assert_visible(app)
            assert user32.GetForegroundWindow() == foreground
            assert [hwnd(window) for window in popups] == original_handles
            assert app.balance == 490

            for _ in range(12):
                app._spawn_coin()
                coin_id, coin = next(iter(app.coin_windows.items()))
                app._begin_coin_drag(coin_id, SimpleNamespace(x_root=coin["x"] + 6, y_root=coin["y"] + 6))
                app._collect_coin(coin_id)
                assert_visible(app)
                assert user32.GetForegroundWindow() == foreground
            print("COIN INTERACTION OK: coalesced direct drag, stable stack, atomic payment, no focus changes")
    finally:
        app.quit_app()


if __name__ == "__main__":
    main()

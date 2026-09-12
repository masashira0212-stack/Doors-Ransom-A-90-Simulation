"""One-shot test proving shell effects are visual-only and shutdown-safe."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk
import time

from doors_ransom import RansomSimulator


def current_wallpaper() -> str:
    buffer = ctypes.create_unicode_buffer(32_768)
    ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0)
    return buffer.value


def taskbar_handles() -> list[int]:
    user32 = ctypes.windll.user32
    result: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        class_name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
            result.append(int(hwnd))
        return True

    user32.EnumWindows(callback, 0)
    return result


def main() -> int:
    root = tk.Tk()
    root.withdraw()
    simulator = RansomSimulator(root, headless=True, enable_shell_effects=True, use_saved_settings=False)
    simulator.volume_var.set(0)
    simulator.audio.set_volume(0)
    wallpaper_before = current_wallpaper()
    user32 = ctypes.windll.user32
    taskbar_visibility = {hwnd: bool(user32.IsWindowVisible(hwnd)) for hwnd in taskbar_handles()}

    # None of these legacy mutators may be reached by the current runtime.
    forbidden_calls: list[str] = []
    for method_name in (
        "_minimize_open_windows",
        "_hide_taskbars",
        "_set_actual_cursor_variant",
        "_apply_red_wallpaper",
        "_replace_desktop_shortcut_icons",
        "_set_actual_icon_variant",
    ):
        setattr(simulator, method_name, lambda name=method_name: forbidden_calls.append(name))

    try:
        simulator.stage = "ransom"
        setup_started = time.monotonic()
        simulator._create_shell_overlays()
        root.update()
        setup_elapsed = time.monotonic() - setup_started
        if setup_elapsed > 2.0:
            raise AssertionError(f"visual shell setup took {setup_elapsed:.3f}s")
        if forbidden_calls:
            raise AssertionError(f"legacy Windows mutators were called: {forbidden_calls}")
        if not simulator.system_effects_active:
            raise AssertionError("visual effects did not activate")
        if not simulator._window_exists(simulator.desktop_overlay):
            raise AssertionError("red desktop visual layer was not created")
        if not simulator._window_exists(simulator.taskbar_overlay):
            raise AssertionError("taskbar visual layer was not created")
        if simulator.cursor_overlay is not None:
            raise AssertionError("a duplicate cursor overlay was created")
        for canvas in (simulator.desktop_canvas, simulator.taskbar_canvas):
            if "red_cursor.cur" not in str(canvas.cget("cursor")):
                raise AssertionError("game background is missing its native red cursor")
        if current_wallpaper() != wallpaper_before:
            raise AssertionError("Windows wallpaper was modified")
        if any(visible != bool(user32.IsWindowVisible(hwnd)) for hwnd, visible in taskbar_visibility.items()):
            raise AssertionError("native taskbar visibility was modified")
        recovery_path = Path(os.environ["LOCALAPPDATA"]) / "DoorsRansomSafeSimulator" / "recovery.json"
        if recovery_path.exists():
            raise AssertionError("new runtime unexpectedly wrote a recovery state")

        simulator._destroy_shell_overlays()
        root.update()
        if simulator.system_effects_active:
            raise AssertionError("visual effects did not clear")
        if current_wallpaper() != wallpaper_before:
            raise AssertionError("wallpaper changed after cleanup")
        if any(visible != bool(user32.IsWindowVisible(hwnd)) for hwnd, visible in taskbar_visibility.items()):
            raise AssertionError("taskbar changed after cleanup")
        print(f"VISUAL-ONLY SYSTEM EFFECTS TEST OK / setup={setup_elapsed:.3f}s")
        return 0
    finally:
        simulator.quit_app()


if __name__ == "__main__":
    raise SystemExit(main())

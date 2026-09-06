"""Terminate a test instance mid-effect and verify persistent shell state."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import winreg

from system_effects_smoke import current_wallpaper, taskbar_handles


def snapshot() -> dict:
    registry = {}
    for branch, names in ((r"Control Panel\Desktop", ("Wallpaper", "WallpaperStyle", "TileWallpaper")),
                          (r"Control Panel\Colors", ("Background",))):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, branch) as key:
            for name in names:
                registry[f"{branch}/{name}"] = winreg.QueryValueEx(key, name)
    shortcuts = {}
    for folder_id in (0x10, 0x19):  # user's Desktop and Public Desktop
        folder = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, folder_id, None, 0, folder) != 0:
            continue
        for path in Path(folder.value).iterdir():
            if path.is_file() and path.suffix.lower() in {".lnk", ".url"}:
                shortcuts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    recovery = Path(os.environ["LOCALAPPDATA"]) / "DoorsRansomSafeSimulator" / "recovery.json"
    return {
        "wallpaper": current_wallpaper(), "registry": registry, "shortcuts": shortcuts,
        "taskbars": {h: bool(ctypes.windll.user32.IsWindowVisible(h)) for h in taskbar_handles()},
        "recovery": recovery.read_bytes() if recovery.is_file() else None,
    }


def child() -> int:
    import tkinter as tk
    from doors_ransom import RansomSimulator

    root = tk.Tk()
    root.withdraw()
    app = RansomSimulator(root, enable_shell_effects=True, use_saved_settings=False)
    app.audio.set_volume(0)
    root.after(10000, lambda: os._exit(2))
    app.start_ransom_preview()
    root.update()
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    windows = [app.desktop_overlay, app.taskbar_overlay, app.note_window]
    windows += [entry["window"] for entry in app.glitch_windows]
    handles = [int(user32.GetParent(w.winfo_id()) or w.winfo_id()) for w in windows]
    print(json.dumps(handles), flush=True)
    root.mainloop()
    return 0


def main() -> int:
    if "--child" in sys.argv:
        return child()
    before = snapshot()
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        line = process.stdout.readline()
        if not line:
            raise AssertionError(f"preview failed: {process.stderr.read()}")
        handles = json.loads(line)
        assert handles and all(ctypes.windll.user32.IsWindow(h) for h in handles)
        assert snapshot() == before, "shell state changed while effects were visible"
        process.terminate()  # exact child spawned by this test; no cleanup callback
        process.wait(timeout=10)
        deadline = time.monotonic() + 2
        while any(ctypes.windll.user32.IsWindow(h) for h in handles) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not any(ctypes.windll.user32.IsWindow(h) for h in handles), "effect windows survived process termination"
        assert snapshot() == before, "shell state changed after forced termination"
        print(f"FORCED-EXIT OK: {len(handles)} effect windows closed; "
              f"{len(before['shortcuts'])} shortcuts, wallpaper, taskbars, and recovery state unchanged")
        return 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())

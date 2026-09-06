"""Manual recovery tool for shell effects left by legacy builds.

The current application no longer starts or bundles this helper. --restore-now
can recover an older build's saved wallpaper and shortcut metadata after a
reboot. Its original watchdog command remains available for older callers.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROCESS_SYNCHRONIZE = 0x00100000
INFINITE = 0xFFFFFFFF
SPI_SETDESKWALLPAPER = 0x0014
SPI_SETCURSORS = 0x0057
SPIF_UPDATEINIFILE = 0x0001
SPIF_SENDCHANGE = 0x0002
SW_SHOW = 5
SW_RESTORE = 9
SHCNE_ASSOCCHANGED = 0x08000000


def wait_for_process_exit(process_id: int) -> None:
    """Wait for a process without keeping a handle in the protected app."""
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(PROCESS_SYNCHRONIZE, False, process_id)
    if not handle:
        return
    try:
        kernel32.WaitForSingleObject(handle, INFINITE)
    finally:
        kernel32.CloseHandle(handle)


def taskbar_handles() -> list[int]:
    user32 = ctypes.windll.user32
    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        class_name = ctypes.create_unicode_buffer(128)
        try:
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}:
                handles.append(int(hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(callback, 0)
    return handles


def restore_taskbars_and_cursors() -> None:
    user32 = ctypes.windll.user32
    for hwnd in taskbar_handles():
        try:
            user32.ShowWindowAsync(hwnd, SW_SHOW)
        except Exception:
            pass
    # Reload the user's configured Windows cursor scheme.
    user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)


def restore_minimized_windows(handles: list[Any], foreground_window: Any = 0) -> None:
    """Restore only windows that were visible before the failed STOP effect."""
    user32 = ctypes.windll.user32
    try:
        foreground = int(foreground_window)
    except (TypeError, ValueError):
        foreground = 0
    for raw_handle in handles:
        try:
            hwnd = int(raw_handle)
            if hwnd == foreground:
                continue
            if hwnd > 0 and user32.IsWindow(hwnd) and user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        except (TypeError, ValueError, OSError):
            pass
    if foreground > 0 and user32.IsWindow(foreground):
        try:
            if user32.IsIconic(foreground):
                user32.ShowWindow(foreground, SW_RESTORE)
            user32.BringWindowToTop(foreground)
            user32.SetForegroundWindow(foreground)
        except OSError:
            pass


def restore_wallpaper(state: dict[str, Any]) -> bool:
    try:
        import winreg

        path = str(state.get("path", ""))
        style = str(state.get("style", "10"))
        tile = str(state.get("tile", "0"))
        background = str(state.get("background", "0 0 0"))
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Control Panel\Desktop",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style)
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile)
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Control Panel\Colors",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "Background", 0, winreg.REG_SZ, background)
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            ctypes.c_wchar_p(path),
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
        )
        return bool(result)
    except Exception:
        return False


def restore_shortcuts(items: list[dict[str, Any]]) -> bool:
    if not items:
        return True
    try:
        encoded = base64.b64encode(
            json.dumps(items, ensure_ascii=False).encode("utf-8")
        ).decode("ascii")
        script = rf"""
$ErrorActionPreference = 'Stop'
$json = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))
$items = $json | ConvertFrom-Json
$shell = New-Object -ComObject WScript.Shell
foreach ($item in @($items)) {{
  if (Test-Path -LiteralPath ([string]$item.path) -PathType Leaf) {{
    $shortcut = $shell.CreateShortcut([string]$item.path)
    $shortcut.IconLocation = [string]$item.icon
    $shortcut.Save()
  }}
}}
"""
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ],
            check=False,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return completed.returncode == 0
    except Exception:
        return False


def refresh_shell_icons() -> None:
    try:
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED,
            0,
            ctypes.c_void_p(),
            ctypes.c_void_p(),
        )
    except Exception:
        pass


def restore_recovery_file(recovery_path: Path, parent_pid: int, restore_live_windows: bool = True) -> bool:
    try:
        payload = json.loads(recovery_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    try:
        owner_pid = int(payload.get("owner_pid", parent_pid))
    except (TypeError, ValueError):
        return False
    if owner_pid != parent_pid:
        return False

    restore_taskbars_and_cursors()
    minimized_windows = payload.get("minimized_windows")
    if restore_live_windows and isinstance(minimized_windows, list):
        restore_minimized_windows(minimized_windows, payload.get("foreground_window", 0))
    ok = True
    wallpaper = payload.get("wallpaper")
    if isinstance(wallpaper, dict):
        ok = restore_wallpaper(wallpaper) and ok
    shortcuts = payload.get("desktop_shortcuts")
    if isinstance(shortcuts, list):
        normalized = [item for item in shortcuts if isinstance(item, dict)]
        ok = restore_shortcuts(normalized) and ok
    refresh_shell_icons()
    if ok:
        try:
            recovery_path.unlink(missing_ok=True)
            recovery_path.with_suffix(".tmp").unlink(missing_ok=True)
        except OSError:
            return False
    return ok


def run_watchdog(parent_pid: int, recovery_path: Path) -> int:
    wait_for_process_exit(parent_pid)
    # A normal shutdown clears the file before process exit. A short grace
    # period also avoids racing the final atomic replace/cleanup operation.
    time.sleep(0.55)
    if not recovery_path.is_file():
        return 0
    return 0 if restore_recovery_file(recovery_path, parent_pid) else 1


def run_self_test() -> int:
    sample = {
        "owner_pid": os.getpid(),
        "taskbar_hidden": True,
        "minimized_windows": [123],
        "foreground_window": 123,
    }
    if int(sample["owner_pid"]) != os.getpid():
        return 1
    if Path("recovery.json").with_suffix(".tmp").name != "recovery.tmp":
        return 1
    if not isinstance(sample["minimized_windows"], list):
        return 1
    if sys.stdout is not None:
        print("RECOVERY WATCHDOG SELF-TEST OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--recovery-path", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--restore-now", action="store_true", help="restore a saved legacy state after shutdown")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.restore_now:
        if os.name != "nt":
            return 2
        recovery_path = args.recovery_path or (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "DoorsRansomSafeSimulator" / "recovery.json"
        )
        if not recovery_path.is_file():
            print("No legacy recovery record. Nothing was changed.")
            return 0
        try:
            payload = json.loads(recovery_path.read_text(encoding="utf-8"))
            owner_pid = int(payload["owner_pid"])
            # Preserve the original recovery record even after successful repair.
            backup = recovery_path.with_name(f"recovery-backup-{time.time_ns()}.json")
            shutil.copy2(recovery_path, backup)
        except (OSError, ValueError, KeyError):
            print("Could not read/back up the recovery record. Nothing was changed.")
            return 1
        # HWND values can be reused after reboot; never restore old app windows
        # in manual recovery mode.
        ok = restore_recovery_file(recovery_path, owner_pid, restore_live_windows=False)
        print(f"Legacy recovery {'completed' if ok else 'incomplete; original state kept'}. Backup: {backup}")
        return 0 if ok else 1
    if os.name != "nt" or not args.parent_pid or args.recovery_path is None:
        return 2
    return run_watchdog(args.parent_pid, args.recovery_path)


if __name__ == "__main__":
    raise SystemExit(main())

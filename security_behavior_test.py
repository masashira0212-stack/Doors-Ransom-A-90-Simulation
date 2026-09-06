"""Source-level guardrails for the harmless visual-simulator build.

This is intentionally a narrow regression test.  It guards against putting
OS-wide input observation, persistence, elevation, or network code back into
the executable while still allowing the app to draw and move its *own* Tk
windows for the visual encounter.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
MAIN_SOURCE = (PROJECT_DIR / "doors_ransom.py").read_text(encoding="utf-8")
SPEC_SOURCE = (PROJECT_DIR / "ransom.spec").read_text(encoding="utf-8")


def require_absent(token: str) -> None:
    if token in MAIN_SOURCE:
        raise AssertionError(f"main runtime contains prohibited capability: {token}")


def main() -> int:
    # Global keyboard/mouse polling and hooks do not belong in a local minigame.
    # The app may register only its three documented user commands (+, -, *).
    for token in (
        "GetAsyncKeyState",
        "SetWindowsHookEx",
        "keybd_event",
        "mouse_event",
        "SendInput",
    ):
        require_absent(token)

    if "RegisterHotKey" not in MAIN_SOURCE or "GLOBAL_COMMAND_HOTKEYS" not in MAIN_SOURCE:
        raise AssertionError("documented command hotkeys are not implemented")
    if "GetMessageW" not in MAIN_SOURCE or "WM_HOTKEY" not in MAIN_SOURCE:
        raise AssertionError("command hotkeys do not use Windows hotkey messages")

    # No network, persistence, privilege elevation, or user-file operations.
    for token in (
        "import socket",
        "import requests",
        "import urllib",
        "import winreg",
        "subprocess.",
        "os.startfile",
        "ShellExecute",
        "SPI_SETDESKWALLPAPER",
    ):
        require_absent(token)

    if "uac_admin=True" in SPEC_SOURCE or "uac_uiaccess=True" in SPEC_SOURCE:
        raise AssertionError("packaging requests elevated or UIAccess privileges")
    if "recovery_watchdog" in SPEC_SOURCE:
        raise AssertionError("legacy recovery code must not be bundled into ransom.exe")

    print("SECURITY BEHAVIOR OK: only explicit +, -, * hotkeys; no polling/hooks, network, persistence, elevation, or wallpaper writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Source-level guardrails for the harmless visual-simulator build.

This is intentionally a narrow regression test.  It guards against putting
OS-wide input observation, persistence, elevation, or network code back into
the executable while still allowing the app to draw and move its *own* Tk
windows for the visual encounter.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
MAIN_SOURCE = (PROJECT_DIR / "doors_ransom.py").read_text(encoding="utf-8")
RUNTIME_SOURCE = "\n".join((PROJECT_DIR / name).read_text(encoding="utf-8") for name in (
    "doors_ransom.py", "ransom_hotkeys.py", "ransom_config.py", "ransom_setting.py"))
CONFIG_SOURCE = (PROJECT_DIR / "ransom_config.py").read_text(encoding="utf-8")
SPEC_SOURCE = (PROJECT_DIR / "ransom.spec").read_text(encoding="utf-8")


def require_absent(token: str) -> None:
    if token in RUNTIME_SOURCE:
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
    # One opt-in, direct executable launch is allowed after a RANSOM timeout.
    # It is parsed by the configuration module and must not invoke a shell.
    for token in (
        "import socket",
        "import requests",
        "import urllib",
        "import winreg",
        "os.startfile",
        "ShellExecute",
        "SPI_SETDESKWALLPAPER",
    ):
        require_absent(token)

    if MAIN_SOURCE.count("subprocess.Popen(") != 1:
        raise AssertionError("runtime must expose only one controlled failure-action launch")
    for required in ("failure_command_arguments(", "shell=False", "close_fds=True", "is_absolute()"):
        if required not in RUNTIME_SOURCE:
            raise AssertionError(f"controlled failure action is missing: {required}")
    for prohibited in ("shell=True", "subprocess.run(", "subprocess.call(", "subprocess.check_call(", "subprocess.check_output("):
        require_absent(prohibited)
    if 'failure_command: str = ""' not in CONFIG_SOURCE:
        raise AssertionError("failure action must remain opt-in by default")

    if "uac_admin=True" in SPEC_SOURCE or "uac_uiaccess=True" in SPEC_SOURCE:
        raise AssertionError("packaging requests elevated or UIAccess privileges")
    if "recovery_watchdog" in SPEC_SOURCE:
        raise AssertionError("legacy recovery code must not be bundled into ransom.exe")
    if "exclude_binaries=True" not in SPEC_SOURCE or "COLLECT(" not in SPEC_SOURCE:
        raise AssertionError("release must use an inspectable portable-folder package")

    print("SECURITY BEHAVIOR OK: inspectable portable package; explicit configurable hotkeys; one opt-in direct failure action; no key polling/hooks, network, persistence, elevation, or wallpaper writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

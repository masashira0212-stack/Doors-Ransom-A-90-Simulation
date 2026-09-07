"""Explicit command bindings; never keyboard hooks or background key capture."""

from __future__ import annotations

import ctypes
import os


SETTINGS_TITLE = "Ransom settings"
MOD_NOREPEAT = 0x4000
MODIFIERS = {"Ctrl": 2, "Alt": 1, "Shift": 4}
KEYS = {
    **{chr(code): code for code in range(65, 91)},
    **{str(n): 48 + n for n in range(10)},
    **{f"F{n}": 111 + n for n in range(1, 25) if n != 12},
    **{f"Num{n}": 96 + n for n in range(10)},
    "Backspace": 8, "Tab": 9, "Enter": 13, "Space": 32,
    "PageUp": 33, "PageDown": 34, "End": 35, "Home": 36,
    "Left": 37, "Up": 38, "Right": 39, "Down": 40,
    "Insert": 45, "Delete": 46,
    "NumMultiply": 106, "NumAdd": 107, "NumSubtract": 109,
    "NumDecimal": 110, "NumDivide": 111,
    "Semicolon": 186, "Equals": 187, "Comma": 188, "Minus": 189,
    "Period": 190, "Slash": 191, "Backtick": 192,
    "LeftBracket": 219, "Backslash": 220, "RightBracket": 221,
    "Quote": 222, "OEM102": 226,
}
ALIASES = {"+": ((0, 107), (4, 187), (0, 187)),
           "-": ((0, 109), (0, 189)),
           "*": ((0, 106), (4, 56), (4, 186))}
DEFAULT_COMMAND_HOTKEYS = {
    0x5253: ("test", MOD_NOREPEAT, 0x6B),
    0x5254: ("test", MOD_NOREPEAT | 4, 0xBB),
    0x5255: ("restore", MOD_NOREPEAT, 0x6D),
    0x5256: ("restore", MOD_NOREPEAT, 0xBD),
    0x5257: ("exit", MOD_NOREPEAT, 0x6A),
    0x5258: ("exit", MOD_NOREPEAT | 4, 0x38),
    0x5259: ("exit", MOD_NOREPEAT | 4, 0xBA),
    0x525A: ("test", MOD_NOREPEAT, 0xBB),
}


def binding_combinations(binding: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(binding, str):
        raise ValueError("Hotkeys must be key names.")
    if binding in ALIASES:
        return ALIASES[binding]
    parts = binding.split("+")
    if parts[-1] not in KEYS or any(p not in MODIFIERS for p in parts[:-1]):
        raise ValueError("Unsupported hotkey. Click a hotkey button and press a key (not F12).")
    if len(set(parts[:-1])) != len(parts[:-1]):
        raise ValueError("A hotkey modifier cannot be repeated.")
    modifiers = sum(MODIFIERS[p] for p in parts[:-1])
    key = KEYS[parts[-1]]
    if (modifiers, key) in {(1, 9), (1, 115), (2, 27), (3, 46)}:
        raise ValueError("This key combination is reserved by Windows.")
    return ((modifiers, key),)


def validate_bindings(trigger: str, restore: str, exit_key: str) -> None:
    used: set[tuple[int, int]] = set()
    for binding in (trigger, restore, exit_key):
        combinations = set(binding_combinations(binding))
        if used & combinations:
            raise ValueError("Trigger, Restore, and Exit must use different keys.")
        used.update(combinations)


def command_hotkeys(settings) -> dict[int, tuple[str, int, int]]:
    result = {}
    for command, binding in (("test", settings.trigger_hotkey),
                             ("restore", settings.restore_hotkey),
                             ("exit", settings.exit_hotkey)):
        if binding == {"test": "+", "restore": "-", "exit": "*"}[command]:
            result.update({i: row for i, row in DEFAULT_COMMAND_HOTKEYS.items() if row[0] == command})
        else:
            modifiers, key = binding_combinations(binding)[0]
            result[{"test": 0x5253, "restore": 0x5255, "exit": 0x5257}[command]] = (
                command, modifiers | MOD_NOREPEAT, key)
    return result


def event_combination(event) -> tuple[int, int]:
    state = int(getattr(event, "state", 0))
    modifiers = (4 if state & 1 else 0) | (2 if state & 4 else 0) | (1 if state & (8 | 0x20000) else 0)
    return modifiers, int(getattr(event, "keycode", 0))


def capture_binding(event) -> str | None:
    """Only called on a KeyPress inside the focused settings window."""
    modifiers, key = event_combination(event)
    if key in {16, 17, 18, 160, 161, 162, 163, 164, 165}:
        return None
    name = next((name for name, value in KEYS.items() if value == key), None)
    if name is None:
        raise ValueError("Use a letter, number, function key (not F12), or punctuation key.")
    binding = "+".join([name for name, mask in MODIFIERS.items() if modifiers & mask] + [name])
    binding_combinations(binding)
    return binding


def settings_has_focus() -> bool:
    if os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    settings_window = user32.FindWindowW(None, SETTINGS_TITLE)
    return bool(settings_window and settings_window == user32.GetForegroundWindow())


def check_available(settings) -> None:
    """Briefly check these commands only; release every registration afterward."""
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    user32.RegisterHotKey.restype = ctypes.c_bool
    registered = []
    commands = set()
    try:
        for offset, (command, modifiers, key) in enumerate(command_hotkeys(settings).values()):
            command_id = 0x5300 + offset
            if user32.RegisterHotKey(None, command_id, modifiers, key):
                registered.append(command_id)
                commands.add(command)
        missing = {"test", "restore", "exit"} - commands
        if missing:
            raise ValueError("Hotkey already in use: " + ", ".join(sorted(missing)) + ". Choose another key.")
    finally:
        for command_id in registered:
            user32.UnregisterHotKey(None, command_id)

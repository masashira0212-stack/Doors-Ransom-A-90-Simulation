"""Validated settings shared by the encounter and its standalone editor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shlex
import tempfile

from ransom_hotkeys import validate_bindings


@dataclass(frozen=True)
class RansomSettings:
    required_coins: int = 500
    min_spawn_seconds: float = 60.0
    max_spawn_seconds: float = 180.0
    stop_grace_seconds: float = 0.25
    trigger_hotkey: str = "+"
    restore_hotkey: str = "-"
    exit_hotkey: str = "*"
    honeypot_chance_percent: float = 1.0
    honeypot_value: int = 500
    ransom_seconds: float = 90.0
    popup_scale_percent: int = 100
    failure_command: str = ""

    @classmethod
    def from_values(cls, coins: object, minimum: object, maximum: object,
                    stop_grace: object = 0.25, trigger_hotkey: str = "+",
                    restore_hotkey: str = "-", exit_hotkey: str = "*",
                    honeypot_chance: object = 1.0, honeypot_value: object = 500,
                    ransom_seconds: object = 90.0, popup_scale_percent: object = 100,
                    failure_command: object = "") -> RansomSettings:
        try:
            if any(isinstance(value, bool) for value in (coins, minimum, maximum, stop_grace)):
                raise ValueError
            coin_number, lo, hi, grace = float(coins), float(minimum), float(maximum), float(stop_grace)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Enter numbers for the coin amount, intervals, and STOP grace.") from None
        if not all(math.isfinite(value) for value in (coin_number, lo, hi, grace)):
            raise ValueError("Infinity and NaN are not allowed.")
        if (not coin_number.is_integer() or not 0 <= coin_number <= 9990
                or (coin_number > 10 and coin_number % 10)):
            raise ValueError("Required coins must be 0-9990. Above 10, use steps of 10.")
        if not 1 <= lo <= hi <= 86400:
            raise ValueError("Intervals must be 1-86400 seconds, with minimum <= maximum.")
        if not 0 <= grace <= 5:
            raise ValueError("STOP grace must be 0-5 seconds.")
        validate_bindings(trigger_hotkey, restore_hotkey, exit_hotkey)
        try:
            if isinstance(honeypot_chance, bool) or isinstance(honeypot_value, bool):
                raise ValueError
            chance, value = float(honeypot_chance), float(honeypot_value)
            if not math.isfinite(chance) or not 0 <= chance <= 100:
                raise ValueError
            if not math.isfinite(value) or not value.is_integer() or not 1 <= value <= 9990:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Honeypot chance must be 0-100%. Payment must be a whole number, 1-9990.") from None
        try:
            if isinstance(ransom_seconds, bool) or isinstance(popup_scale_percent, bool):
                raise ValueError
            duration, scale = float(ransom_seconds), float(popup_scale_percent)
            if not math.isfinite(duration) or not 10 <= duration <= 100:
                raise ValueError
            if not math.isfinite(scale) or not scale.is_integer() or not 50 <= scale <= 150:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Ransom timer must be 10-100 seconds. Popup scale must be a whole percentage from 50 to 150.") from None
        command = validate_failure_command(failure_command)
        return cls(int(coin_number), lo, hi, grace, trigger_hotkey, restore_hotkey,
                   exit_hotkey, chance, int(value), duration, int(scale), command)

    def validated(self) -> RansomSettings:
        return self.from_values(self.required_coins, self.min_spawn_seconds,
                                self.max_spawn_seconds, self.stop_grace_seconds,
                                self.trigger_hotkey, self.restore_hotkey, self.exit_hotkey,
                                self.honeypot_chance_percent, self.honeypot_value,
                                self.ransom_seconds, self.popup_scale_percent,
                                self.failure_command)


DEFAULT_SETTINGS = RansomSettings()


_BLOCKED_FAILURE_EXECUTABLES = {
    "cmd.exe", "command.com", "powershell.exe", "pwsh.exe", "wscript.exe",
    "cscript.exe", "mshta.exe", "rundll32.exe", "regsvr32.exe", "msiexec.exe",
    "schtasks.exe", "wmic.exe", "curl.exe", "bitsadmin.exe", "certutil.exe",
}


def failure_command_arguments(value: object) -> list[str]:
    """Parse the opt-in failure action without invoking a command shell.

    The setting is deliberately limited to a direct, absolute .exe path plus
    optional arguments.  Batch files and command interpreters would make a
    harmless visual simulator silently inherit unrestricted shell behavior.
    """
    if not isinstance(value, str):
        raise ValueError("Failure command must be text.")
    command = value.strip()
    if not command:
        return []
    if len(command) > 2048 or "\x00" in command or "\r" in command or "\n" in command:
        raise ValueError("Failure command must be one line, up to 2048 characters.")
    try:
        arguments = shlex.split(command, posix=False)
    except ValueError:
        raise ValueError("Failure command has unmatched quotes.") from None
    if not arguments:
        return []
    executable = Path(arguments[0].strip('"')).expanduser()
    if not executable.is_absolute() or executable.suffix.lower() != ".exe":
        raise ValueError("Failure command must start with an absolute .exe path in quotes when it has spaces.")
    if executable.name.lower() in _BLOCKED_FAILURE_EXECUTABLES:
        raise ValueError("Command shells and script hosts are not allowed for the failure action.")
    arguments[0] = str(executable)
    return arguments


def validate_failure_command(value: object) -> str:
    failure_command_arguments(value)
    return value.strip() if isinstance(value, str) else ""


def default_settings_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DoorsRansomSafeSimulator" / "settings.json"


def settings_signature(path: Path) -> tuple[int, int] | None:
    try:
        info = path.stat()
        return info.st_mtime_ns, info.st_size
    except OSError:
        return None


def load_settings(path: Path | None = None) -> RansomSettings:
    path = path if path is not None else default_settings_path()
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return DEFAULT_SETTINGS
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported settings file format.")
        return RansomSettings.from_values(
            data["required_coins"], data["min_spawn_seconds"], data["max_spawn_seconds"],
            data.get("stop_grace_seconds", DEFAULT_SETTINGS.stop_grace_seconds),
            data.get("trigger_hotkey", "+"), data.get("restore_hotkey", "-"), data.get("exit_hotkey", "*"),
            data.get("honeypot_chance_percent", 1.0), data.get("honeypot_value", 500),
            data.get("ransom_seconds", DEFAULT_SETTINGS.ransom_seconds),
            data.get("popup_scale_percent", DEFAULT_SETTINGS.popup_scale_percent),
            data.get("failure_command", DEFAULT_SETTINGS.failure_command),
        )
    except (json.JSONDecodeError, KeyError):
        raise ValueError("Invalid settings file. Check the values and save again.") from None


def save_settings(settings: RansomSettings, path: Path | None = None) -> None:
    settings = settings.validated()  # validate before touching the saved file
    path = path if path is not None else default_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="settings-", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            json.dump({"version": 1, **asdict(settings)}, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

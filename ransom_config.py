"""Validated settings shared by the encounter and its standalone editor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True)
class RansomSettings:
    required_coins: int = 500
    min_spawn_seconds: float = 60.0
    max_spawn_seconds: float = 180.0
    stop_grace_seconds: float = 0.25

    @classmethod
    def from_values(cls, coins: object, minimum: object, maximum: object,
                    stop_grace: object = 0.25) -> RansomSettings:
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
        return cls(int(coin_number), lo, hi, grace)

    def validated(self) -> RansomSettings:
        return self.from_values(self.required_coins, self.min_spawn_seconds,
                                self.max_spawn_seconds, self.stop_grace_seconds)


DEFAULT_SETTINGS = RansomSettings()


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

"""Generate the original, copyright-safe sound set used by the simulator."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
OUTPUT_DIR = Path(__file__).resolve().parent / "sounds"


def clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def write_wave(name: str, seconds: float, sample_fn) -> None:
    frames = bytearray()
    sample_count = int(SAMPLE_RATE * seconds)
    for index in range(sample_count):
        time_s = index / SAMPLE_RATE
        value = clamp(sample_fn(time_s, index, sample_count))
        frames.extend(struct.pack("<h", int(value * 32_767)))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUTPUT_DIR / name), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(frames)


def fade_envelope(index: int, sample_count: int, attack: float = 0.03) -> float:
    position = index / max(1, sample_count - 1)
    attack_gain = min(1.0, position / max(attack, 0.0001))
    release_gain = min(1.0, (1.0 - position) / 0.08)
    return max(0.0, min(attack_gain, release_gain))


def main() -> None:
    rng = random.Random(90)

    def stop_sound(t: float, i: int, count: int) -> float:
        noise = rng.uniform(-1.0, 1.0)
        pulse = 1.0 if int(t * 30) % 2 == 0 else -0.55
        tone = math.sin(2 * math.pi * (94 + 26 * math.sin(t * 18)) * t)
        return (noise * 0.48 + pulse * tone * 0.42) * fade_envelope(i, count)

    write_wave("stop_static.wav", 0.48, stop_sound)

    rng = random.Random(500)

    def attack_sound(t: float, i: int, count: int) -> float:
        progress = i / count
        frequency = 1_300 - 980 * progress + 120 * math.sin(t * 37)
        carrier = math.sin(2 * math.pi * frequency * t)
        distorted = math.tanh(carrier * 5.5)
        noise = rng.uniform(-1.0, 1.0) * (0.35 + progress * 0.4)
        stutter = 1.0 if int(t * 47) % 5 else 0.2
        return (distorted * 0.64 + noise * 0.36) * stutter * fade_envelope(i, count, 0.006)

    write_wave("attack.wav", 0.88, attack_sound)

    rng = random.Random(1337)

    def ambience(t: float, i: int, count: int) -> float:
        hum = math.sin(2 * math.pi * 46 * t) * 0.21
        second = math.sin(2 * math.pi * 73 * t + math.sin(t * 2.1)) * 0.12
        noise = rng.uniform(-1.0, 1.0) * 0.10
        glitch_gate = 1.0
        phase = t % 1.7
        if 0.92 < phase < 1.03 or 1.29 < phase < 1.34:
            glitch_gate = 3.0 if int(t * 75) % 2 else 0.15
        tick = 0.0
        tick_phase = t % 1.0
        if tick_phase < 0.035:
            tick = math.sin(2 * math.pi * 1_650 * t) * (1.0 - tick_phase / 0.035) * 0.28
        return (hum + second + noise * glitch_gate + tick) * fade_envelope(i, count, 0.08)

    write_wave("ransom_loop.wav", 6.0, ambience)

    coin_rng = random.Random(777)

    def coin(t: float, i: int, count: int) -> float:
        # Brighter arcade pickup: metallic click followed by a two-step chime.
        click = coin_rng.uniform(-1.0, 1.0) * max(0.0, 1.0 - t / 0.018) * 0.34
        first_t = min(t, 0.075)
        first = math.sin(2 * math.pi * 920 * first_t) * math.exp(-t * 15.0)
        second_local = max(0.0, t - 0.055)
        second = math.sin(2 * math.pi * 1_440 * second_local) * math.exp(-second_local * 17.0)
        metal = math.sin(2 * math.pi * 2_850 * t) * math.exp(-t * 24.0)
        return click + first * 0.44 + second * 0.48 + metal * 0.18

    write_wave("coin.wav", 0.28, coin)

    rng = random.Random(404)

    def failure(t: float, i: int, count: int) -> float:
        progress = i / count
        base = math.sin(2 * math.pi * (210 - 120 * progress) * t)
        upper = math.sin(2 * math.pi * (880 + 420 * math.sin(t * 11)) * t)
        noise = rng.uniform(-1.0, 1.0)
        return math.tanh(base * 2.8 + upper * 1.5 + noise * 1.1) * fade_envelope(i, count, 0.004) * 0.82

    write_wave("failure.wav", 1.25, failure)
    print(f"Generated sound files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

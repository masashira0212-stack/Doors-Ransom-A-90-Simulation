"""Validate the late-start timing while keeping the original compressed MP3."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sounds" / "ransom_ost_to_jumpscare.mp3"
LEGACY_OUTPUTS = (
    ROOT / "sounds" / "ransom_ost_90.wav",
    ROOT / "sounds" / "ransom_ost_147.wav",
)
JUMPSCARE1_SOURCE = ROOT / "sounds" / "jumpscare1.mp3"
LEGACY_JUMPSCARE1_OUTPUTS = (
    ROOT / "sounds" / "jumpscare1_full_declicked.wav",
    ROOT / "sounds" / "jumpscare1_ready.wav",
)
RATE = 44_100
RANSOM_SECONDS = 90.0
FINAL_JUMP_START_SECONDS = 101.55


def stereo(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        samples = np.column_stack((samples, samples))
    return samples.astype(np.int16, copy=False)


def main() -> int:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    pygame.mixer.pre_init(RATE, -16, 2, 1024)
    pygame.mixer.init()
    sound = pygame.mixer.Sound(str(SOURCE))
    samples = stereo(pygame.sndarray.array(sound))
    pygame.mixer.quit()

    # jumpscare1 must remain the exact supplied MP3. Remove older generated
    # variants so they cannot accidentally be included or selected again.
    if not JUMPSCARE1_SOURCE.is_file():
        raise RuntimeError("Missing original jumpscare1.mp3")
    for legacy_path in LEGACY_JUMPSCARE1_OUTPUTS:
        legacy_path.unlink(missing_ok=True)

    tail_start = int(FINAL_JUMP_START_SECONDS * RATE)
    target_music_frames = int(RANSOM_SECONDS * RATE)
    if len(samples) <= tail_start:
        raise RuntimeError("Unexpected source duration for 90-second soundtrack preparation")

    # Start from the later part of the original OST.  The sample immediately
    # before the supplied final jump remains the sample at 01:30, so the timer
    # and the soundtrack climax meet without looping or crossfading.
    music_start = tail_start - target_music_frames
    if music_start < 0:
        raise RuntimeError("Source music is too short to provide its final 90 seconds")
    tail = samples[tail_start:]
    if tail_start - music_start != target_music_frames:
        raise RuntimeError("Prepared music did not land on the 90-second boundary")

    # The app seeks directly inside the original MP3, avoiding a 16 MB PCM WAV.
    for legacy_path in LEGACY_OUTPUTS:
        legacy_path.unlink(missing_ok=True)
    print(f"Using compressed source directly: {SOURCE}")
    print(
        f"Music: source {music_start / RATE:.2f}s-{FINAL_JUMP_START_SECONDS:.2f}s "
        f"/ final jump at {RANSOM_SECONDS:.2f}s / tail {len(tail) / RATE:.2f}s"
    )
    print(f"Unmodified: {JUMPSCARE1_SOURCE} (direct MP3 playback)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

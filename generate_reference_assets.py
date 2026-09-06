"""Validate the user-supplied high-resolution RANSOM coin asset."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
TEMPLATE = ASSETS / "ransom_note_template.png"
COIN = ASSETS / "coin_token.png"


def main() -> int:
    if not COIN.is_file():
        raise RuntimeError("Missing user-supplied coin_token.png")
    TEMPLATE.unlink(missing_ok=True)
    coin = Image.open(COIN).convert("RGBA")
    if coin.size != (500, 500):
        raise RuntimeError(f"Unexpected coin size: {coin.size}")
    if coin.getchannel("A").getextrema() != (0, 255):
        raise RuntimeError("Coin must contain both transparent and opaque pixels")
    print(f"Validated: {COIN} ({coin.size[0]}x{coin.size[1]} RGBA)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

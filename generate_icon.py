"""Generate a crisp multi-resolution red-folder Windows icon."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "assets" / "ransom.ico"


def save_cursor(image: Image.Image, path: Path, hotspot: tuple[int, int] = (2, 2)) -> None:
    buffer = io.BytesIO()
    image.resize((48, 48), Image.Resampling.LANCZOS).save(buffer, format="ICO", sizes=[(48, 48)])
    data = bytearray(buffer.getvalue())
    data[2:4] = (2).to_bytes(2, "little")
    data[10:12] = hotspot[0].to_bytes(2, "little")
    data[12:14] = hotspot[1].to_bytes(2, "little")
    path.write_bytes(data)


def save_effect_assets() -> None:
    assets = ROOT / "assets"
    source_names = ["stop.png", "stop_reference.png"] + [f"glitch_{index}.png" for index in range(1, 7)]
    for name in source_names:
        source = Image.open(assets / name).convert("RGBA")
        stem = Path(name).stem
        source.save(
            assets / f"system_{stem}.ico",
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        save_cursor(source, assets / f"system_{stem}.cur")
    cursor = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    cursor_draw = ImageDraw.Draw(cursor)
    arrow = [(5, 3), (5, 51), (18, 39), (29, 59), (40, 53), (29, 34), (48, 34)]
    cursor_draw.polygon(arrow, fill="#170000", outline="#000000")
    inner = [(9, 10), (9, 42), (19, 32), (31, 53), (34, 51), (23, 29), (40, 29)]
    cursor_draw.polygon(inner, fill="#ff1515", outline="#9b0000")
    save_cursor(cursor, assets / "red_cursor.cur", hotspot=(6, 5))
    Image.new("RGB", (64, 64), (118, 0, 0)).save(assets / "red_wallpaper.bmp", format="BMP")


def main() -> int:
    scale = 4
    size = 256
    canvas = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    def box(values: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        return tuple(value * scale for value in values)  # type: ignore[return-value]

    draw.rounded_rectangle(box((16, 55, 240, 224)), radius=18 * scale, fill="#690007", outline="#ff4a51", width=5 * scale)
    draw.rounded_rectangle(box((24, 36, 124, 88)), radius=13 * scale, fill="#d50916", outline="#ff666b", width=4 * scale)
    draw.polygon(
        [(25 * scale, 75 * scale), (231 * scale, 75 * scale), (214 * scale, 218 * scale), (40 * scale, 218 * scale)],
        fill="#e30a18",
    )
    draw.line(box((33, 92, 222, 92)), fill="#ff5d65", width=5 * scale)
    draw.line(box((48, 204, 207, 204)), fill="#97000a", width=7 * scale)
    canvas = canvas.resize((size, size), Image.Resampling.LANCZOS)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    save_effect_assets()
    print(f"Generated: {OUTPUT}")
    print("Generated: reversible cursor/icon variants and red wallpaper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

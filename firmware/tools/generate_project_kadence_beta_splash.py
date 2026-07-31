#!/usr/bin/env python3
"""Generate the Project Kadence Beta 320 x 240 boot splash."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

WIDTH = 320
HEIGHT = 240
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "project-kadence" / "beta_splash.png"


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = (
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def centred(draw: ImageDraw.ImageDraw, y: int, text: str, face: ImageFont.ImageFont, fill: tuple[int, int, int, int]) -> None:
    box = draw.textbbox((0, 0), text, font=face)
    x = (WIDTH - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=face, fill=fill)


def main() -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for radius, alpha in ((74, 12), (58, 20), (43, 30), (30, 48)):
        glow_draw.ellipse(
            (160 - radius, 67 - radius, 160 + radius, 67 + radius),
            fill=(255, 0, 0, alpha),
        )
    image = Image.alpha_composite(image, glow.filter(ImageFilter.GaussianBlur(15)))
    draw = ImageDraw.Draw(image)

    centre = (160, 67)
    for radius, width, shade in (
        (58, 3, 32),
        (51, 2, 47),
        (44, 2, 62),
        (36, 2, 82),
        (28, 2, 105),
    ):
        draw.ellipse(
            (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
            outline=(shade, shade, shade, 255),
            width=width,
        )

    for index in range(12):
        angle = math.radians(index * 30)
        outer = 55
        inner = 45
        x1 = centre[0] + int(math.cos(angle) * inner)
        y1 = centre[1] + int(math.sin(angle) * inner)
        x2 = centre[0] + int(math.cos(angle) * outer)
        y2 = centre[1] + int(math.sin(angle) * outer)
        draw.line((x1, y1, x2, y2), fill=(75, 75, 75, 255), width=2)

    for radius, colour in (
        (27, (75, 0, 0, 255)),
        (22, (130, 0, 0, 255)),
        (17, (235, 16, 16, 255)),
        (11, (255, 68, 45, 255)),
    ):
        draw.ellipse(
            (centre[0] - radius, centre[1] - radius, centre[0] + radius, centre[1] + radius),
            fill=colour,
        )
    draw.ellipse((154, 61, 166, 73), fill=(20, 0, 0, 255))
    draw.ellipse((157, 62, 161, 66), fill=(255, 190, 170, 220))

    centred(draw, 154, "PROJECT KADENCE", font(25), (240, 240, 240, 255))
    centred(draw, 188, "BETA", font(18), (255, 30, 30, 255))

    draw.line((42, 224, 278, 224), fill=(70, 70, 70, 255), width=1)
    draw.rectangle((42, 219, 45, 222), fill=(255, 255, 255, 255))
    draw.rectangle((275, 219, 278, 222), fill=(255, 255, 255, 255))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(OUTPUT, "PNG", optimize=True)
    with Image.open(OUTPUT) as check:
        if check.size != (WIDTH, HEIGHT):
            raise RuntimeError(f"unexpected splash dimensions: {check.size}")
    print(f"wrote {OUTPUT} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()

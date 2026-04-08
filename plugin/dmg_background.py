"""Generate a DMG background image for the scheMAGIC installer.

Creates a 660x400 image with a dark gradient, arrow, and
"Drag to Applications" text. Falls back to a solid colour
if Pillow is not installed.
"""

import os
import struct
import zlib


def generate_dmg_background(output_dir: str) -> str:
    """Generate DMG background PNG and return its path."""
    output_path = os.path.join(output_dir, "dmg_background.png")

    try:
        from PIL import Image, ImageDraw, ImageFont

        _generate_with_pillow(output_path)
    except ImportError:
        print("  Pillow not installed, using solid background")
        _generate_fallback(output_path)

    return output_path


def _generate_with_pillow(output_path: str):
    from PIL import Image, ImageDraw, ImageFont

    width, height = 660, 400
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # Dark gradient background
    for y in range(height):
        r = int(26 + (22 - 26) * y / height)
        g = int(26 + (33 - 26) * y / height)
        b = int(46 + (62 - 46) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Arrow from app position (170) to Applications position (490)
    arrow_y = 260
    arrow_start = 230
    arrow_end = 430
    arrow_colour = (180, 180, 180)

    # Dashed line
    dash_len = 12
    gap_len = 8
    x = arrow_start
    while x < arrow_end - 20:
        x2 = min(x + dash_len, arrow_end - 20)
        draw.line([(x, arrow_y), (x2, arrow_y)], fill=arrow_colour, width=2)
        x += dash_len + gap_len

    # Arrowhead
    head_x = arrow_end
    draw.polygon([
        (head_x, arrow_y),
        (head_x - 14, arrow_y - 8),
        (head_x - 14, arrow_y + 8),
    ], fill=arrow_colour)

    # Text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text = "Drag to Applications"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(
        ((width - text_w) / 2, arrow_y + 20),
        text,
        fill=(160, 160, 160),
        font=font,
    )

    img.save(output_path, "PNG")


def _generate_fallback(output_path: str):
    """Create a minimal 660x400 solid-colour PNG without Pillow."""
    width, height = 660, 400
    # Dark background RGB(26, 26, 46)
    r, g, b = 26, 26, 46

    # Build raw image data (one filter byte + RGB per pixel per row)
    raw_data = b""
    row = b"\x00" + bytes([r, g, b]) * width
    for _ in range(height):
        raw_data += row

    compressed = zlib.compress(raw_data)

    def _chunk(chunk_type, data):
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    with open(output_path, "wb") as f:
        # PNG signature
        f.write(b"\x89PNG\r\n\x1a\n")
        # IHDR
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        f.write(_chunk(b"IHDR", ihdr_data))
        # IDAT
        f.write(_chunk(b"IDAT", compressed))
        # IEND
        f.write(_chunk(b"IEND", b""))

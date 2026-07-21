"""Generate PhishGuard PNG icons using only Python stdlib (no Pillow needed).

Run once from the browser_extension/ directory:
    python generate_icons.py

Creates: icons/icon16.png, icons/icon48.png, icons/icon128.png
"""

import math
import os
import struct
import zlib


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def make_png(width: int, height: int, pixels: list) -> bytes:
    """Build a minimal RGBA PNG from a flat list of (R, G, B, A) tuples."""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw += b"\x00"          # filter byte per row
        for x in range(width):
            raw += bytes(pixels[y * width + x])
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _chunk(b"IEND", b"")
    )


def draw_icon(size: int) -> list:
    """
    Purple shield with a white checkmark centre.

    Shield shape:
      - Stays inside a circle of radius 0.9 * (size/2)
      - Width tapers linearly from 0.85 at the top to 0 at the bottom point
    """
    PURPLE = (108, 33, 255, 255)
    WHITE  = (255, 255, 255, 255)
    TRANS  = (0, 0, 0, 0)

    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    r  = size / 2.0

    pixels = []
    for y in range(size):
        for x in range(size):
            nx = (x - cx) / r   # [-1, 1]
            ny = (y - cy) / r   # [-1, 1]  (positive = down)

            # Shield boundary
            in_circle  = nx * nx + ny * ny <= 0.90 ** 2
            half_width = 0.85 * (1.0 - max(0.0, ny + 0.2) * 0.72)
            in_shield  = in_circle and abs(nx) <= half_width and ny <= 0.82

            if not in_shield:
                pixels.append(TRANS)
                continue

            # Checkmark path (only for icons >= 48px)
            if size >= 48:
                # Left arm:  from (-0.35, 0.10) to (-0.02, 0.42)
                # Right arm: from (-0.02, 0.42) to ( 0.42, -0.22)
                stroke = 0.10 if size >= 128 else 0.13

                def dist_to_segment(px, py, ax, ay, bx, by):
                    dx, dy = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx*dx + dy*dy)))
                    return math.hypot(px - (ax + t*dx), py - (ay + t*dy))

                d1 = dist_to_segment(nx, ny, -0.35, 0.10, -0.02, 0.42)
                d2 = dist_to_segment(nx, ny, -0.02, 0.42,  0.45, -0.22)
                if d1 <= stroke or d2 <= stroke:
                    pixels.append(WHITE)
                    continue

            pixels.append(PURPLE)

    return pixels


def main() -> None:
    os.makedirs("icons", exist_ok=True)
    for size in (16, 48, 128):
        pixels = draw_icon(size)
        data   = make_png(size, size, pixels)
        path   = f"icons/icon{size}.png"
        with open(path, "wb") as f:
            f.write(data)
        print(f"  Created {path}  ({len(data):,} bytes)")
    print("Done. Load the extension in Chrome at chrome://extensions (Developer mode).")


if __name__ == "__main__":
    main()

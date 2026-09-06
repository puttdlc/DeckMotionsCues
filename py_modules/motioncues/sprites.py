"""Dot rasterisation.

Dots are drawn once into a small premultiplied-ARGB tile and then blitted, so
per-frame work is a handful of memory copies instead of any geometry.

Two details matter for correctness on a compositor:

* **Premultiplied alpha.**  X11 32-bit ARGB visuals (and the Wayland buffers
  Xwayland hands to gamescope) expect colour channels already multiplied by
  alpha.  Storing straight alpha produces bright halos around soft edges.
* **Tile padding.**  Each tile is padded by at least the largest per-frame
  movement, so redrawing a dot's tile also erases wherever it was last frame.
  That turns "clear the old dot, draw the new dot" into a single blit and
  removes any chance of a half-erased frame being composited.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Sequence, Tuple

# 4x4 supersampling: enough to make a 6 px dot look round, cheap enough that
# rebuilding the sprite on a settings change is imperceptible.
SUPERSAMPLE = 4


def _coverage_circle(dx: float, dy: float, radius: float) -> bool:
    return dx * dx + dy * dy <= radius * radius


def _coverage_square(dx: float, dy: float, radius: float) -> bool:
    return abs(dx) <= radius and abs(dy) <= radius


def _coverage_diamond(dx: float, dy: float, radius: float) -> bool:
    return abs(dx) + abs(dy) <= radius


def _coverage_ring(dx: float, dy: float, radius: float) -> bool:
    distance = math.hypot(dx, dy)
    inner = radius * 0.55
    return inner <= distance <= radius


COVERAGE = {
    "circle": _coverage_circle,
    "square": _coverage_square,
    "diamond": _coverage_diamond,
    "ring": _coverage_ring,
}


class Sprite:
    """A premultiplied ARGB tile with the dot centred inside it."""

    __slots__ = ("width", "height", "data", "center_x", "center_y")

    def __init__(self, width: int, height: int, data: bytearray,
                 center_x: float, center_y: float) -> None:
        self.width = width
        self.height = height
        self.data = data
        self.center_x = center_x
        self.center_y = center_y

    @property
    def stride(self) -> int:
        return self.width * 4


def render_sprite(size: float, shape: str, color: Tuple[int, int, int],
                  opacity: float, padding: int = 2,
                  outline: float = 0.0,
                  outline_color: Tuple[int, int, int] = (0, 0, 0)) -> Sprite:
    """Rasterise one dot.

    ``size`` is the dot's diameter in pixels; ``padding`` is extra transparent
    border used both for antialiasing headroom and to cover the previous
    frame's position.
    """

    radius = max(0.5, size * 0.5)
    outline = max(0.0, outline)
    extent = radius + outline
    dimension = int(math.ceil(extent * 2.0)) + padding * 2
    if dimension % 2:
        dimension += 1
    center = dimension / 2.0

    coverage_fn = COVERAGE.get(shape, _coverage_circle)
    data = bytearray(dimension * dimension * 4)

    red, green, blue = color
    outline_red, outline_green, outline_blue = outline_color
    samples = SUPERSAMPLE * SUPERSAMPLE
    step = 1.0 / SUPERSAMPLE
    offset = step * 0.5

    for py in range(dimension):
        row = py * dimension * 4
        for px in range(dimension):
            inside = 0
            edge = 0
            for sy in range(SUPERSAMPLE):
                dy = (py + offset + sy * step) - center
                for sx in range(SUPERSAMPLE):
                    dx = (px + offset + sx * step) - center
                    if coverage_fn(dx, dy, radius):
                        inside += 1
                    elif outline > 0.0 and coverage_fn(dx, dy, extent):
                        edge += 1

            if not inside and not edge:
                continue

            fill_alpha = (inside / samples) * opacity
            edge_alpha = (edge / samples) * opacity

            # Composite the outline underneath the fill.
            total_alpha = fill_alpha + edge_alpha * (1.0 - fill_alpha)
            if total_alpha <= 0.0:
                continue
            src_r = (red * fill_alpha + outline_red * edge_alpha * (1.0 - fill_alpha))
            src_g = (green * fill_alpha + outline_green * edge_alpha * (1.0 - fill_alpha))
            src_b = (blue * fill_alpha + outline_blue * edge_alpha * (1.0 - fill_alpha))

            index = row + px * 4
            # Little-endian ZPixmap on an ARGB32 visual: B, G, R, A.
            # Values are premultiplied, which is what the source alphas above
            # already produce.
            data[index] = int(src_b + 0.5)
            data[index + 1] = int(src_g + 0.5)
            data[index + 2] = int(src_r + 0.5)
            data[index + 3] = int(total_alpha * 255.0 + 0.5)

    return Sprite(dimension, dimension, data, center, center)


def scale_sprite_alpha(sprite: Sprite, factor: float) -> Sprite:
    """Return a copy of ``sprite`` with alpha (and therefore colour) scaled.

    Used for the fade in/out envelope in Automatic mode.  Because the tile is
    premultiplied, every channel scales by the same factor.
    """

    if factor >= 0.999:
        return sprite
    factor = max(0.0, factor)
    data = bytearray(len(sprite.data))
    source = sprite.data
    for index in range(0, len(source), 4):
        alpha = source[index + 3]
        if not alpha:
            continue
        data[index] = int(source[index] * factor)
        data[index + 1] = int(source[index + 1] * factor)
        data[index + 2] = int(source[index + 2] * factor)
        data[index + 3] = int(alpha * factor)
    return Sprite(sprite.width, sprite.height, data, sprite.center_x, sprite.center_y)


def sprite_for(appearance: Dict[str, Any], padding: int = 3) -> Sprite:
    """Build the sprite described by an appearance config block."""

    from .config import hex_to_rgb

    return render_sprite(
        size=float(appearance["size"]),
        shape=appearance["shape"],
        color=hex_to_rgb(appearance["color"]),
        opacity=float(appearance["opacity"]),
        padding=padding,
        outline=float(appearance["outline"]),
        outline_color=hex_to_rgb(appearance["outline_color"]),
    )


# --------------------------------------------------------------------------
# PNG export - used by the test tooling to eyeball what will be drawn
# --------------------------------------------------------------------------

def compose_preview(width: int, height: int, points: Sequence[Tuple[float, float]],
                    sprite: Sprite,
                    background: Tuple[int, int, int] = (24, 26, 32),
                    buffer: "bytearray | None" = None) -> bytearray:
    """Composite sprites over a solid background into an RGB buffer.

    Pass an existing ``buffer`` to draw several sprite types onto one canvas.
    """

    if buffer is None:
        buffer = bytearray()
        for _ in range(width * height):
            buffer.extend(background)

    for x, y in points:
        left = int(round(x - sprite.center_x))
        top = int(round(y - sprite.center_y))
        for row in range(sprite.height):
            py = top + row
            if py < 0 or py >= height:
                continue
            for col in range(sprite.width):
                px = left + col
                if px < 0 or px >= width:
                    continue
                index = (row * sprite.width + col) * 4
                alpha = sprite.data[index + 3]
                if not alpha:
                    continue
                # Premultiplied source over opaque destination.
                inverse = (255 - alpha) / 255.0
                out = (py * width + px) * 3
                buffer[out] = min(255, int(sprite.data[index + 2] + buffer[out] * inverse))
                buffer[out + 1] = min(255, int(sprite.data[index + 1] + buffer[out + 1] * inverse))
                buffer[out + 2] = min(255, int(sprite.data[index] + buffer[out + 2] * inverse))
    return buffer


def write_png(path: str, width: int, height: int, rgb: bytearray) -> None:
    """Minimal PNG writer so previews need no third-party imaging library."""

    import struct
    import zlib

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type 0
        raw.extend(rgb[y * stride:(y + 1) * stride])

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as handle:
        handle.write(png)

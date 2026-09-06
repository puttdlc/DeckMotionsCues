"""Where the dots sit when nothing is moving.

Positions are computed once per (screen size, appearance) pair and then simply
translated by the motion engine's displacement, so the per-frame cost stays
proportional to the number of dots rather than to the screen area.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

Point = Tuple[float, float]


def _spread(count: int, margin: float, layout: str) -> List[float]:
    """Return ``count`` normalised positions in 0..1 along an edge."""

    if count <= 0:
        return []
    usable_start = margin
    usable_end = 1.0 - margin
    span = max(1e-6, usable_end - usable_start)

    if count == 1:
        return [usable_start + span * 0.5]

    if layout == "corners":
        # Two clusters, one at each end of the edge.
        half = count // 2
        extra = count - half * 2
        cluster = span * 0.28
        positions: List[float] = []
        for group in range(2):
            n = half + (extra if group == 0 else 0)
            if n <= 0:
                continue
            base = usable_start if group == 0 else usable_end - cluster
            step = cluster / max(1, n - 1) if n > 1 else 0.0
            positions.extend(base + step * index for index in range(n))
        return sorted(positions)

    if layout == "clustered":
        # Denser toward the middle of the edge: ease the even spacing through
        # a smoothstep so the centre gets more dots than the ends.
        positions = []
        for index in range(count):
            t = (index + 0.5) / count
            eased = t * t * (3.0 - 2.0 * t)
            positions.append(usable_start + span * eased)
        return positions

    # "even"
    return [usable_start + span * ((index + 0.5) / count) for index in range(count)]


def dot_positions(width: int, height: int, appearance: Dict[str, Any]) -> List[Point]:
    """Base (unmoved) dot centres for a screen of ``width`` x ``height``."""

    count = int(appearance["count"])
    padding = float(appearance["edge_padding"])
    margin = float(appearance["margin_fraction"])
    layout = appearance["layout"]
    edges = appearance["edges"]

    points: List[Point] = []
    for edge in edges:
        fractions = _spread(count, margin, layout)
        if edge == "left":
            points.extend((padding, t * height) for t in fractions)
        elif edge == "right":
            points.extend((width - padding, t * height) for t in fractions)
        elif edge == "top":
            points.extend((t * width, padding) for t in fractions)
        elif edge == "bottom":
            points.extend((t * width, height - padding) for t in fractions)
    return points


def bounding_box(points: List[Point], radius: float) -> Tuple[float, float, float, float]:
    """Axis-aligned bounds of all dots, expanded by ``radius``."""

    if not points:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (min(xs) - radius, min(ys) - radius, max(xs) + radius, max(ys) + radius)

from __future__ import annotations

import math

import numpy as np

from ..scene import Mesh
from .registry import ObjectSpec, Param, register

__all__ = ["NULL", "NULL_DISPLAYS", "NULL_ORIENTATIONS", "null_segments"]

NULL_DISPLAYS = ("None", "Dot", "Point", "Circle", "Rectangle", "Diamond", "Hexagon", "Pyramid", "Cube")
NULL_ORIENTATIONS = ("Camera", "XY", "ZY", "XZ")
NULL_CIRCLE_STEPS = 48


def _loop(points: list[tuple[float, float, float]]) -> list[tuple[tuple, tuple]]:
    return [(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def null_segments(display: str, radius: float, aspect: float) -> np.ndarray:
    r = float(radius)
    h = r * float(aspect)
    if r <= 0.0 or display not in NULL_DISPLAYS or display in ("None", "Dot", "Point"):
        return np.zeros((0, 2, 3))
    segs: list[tuple[tuple, tuple]] = []
    if display == "Circle":
        ring = [(r * math.cos(2 * math.pi * i / NULL_CIRCLE_STEPS),
                 h * math.sin(2 * math.pi * i / NULL_CIRCLE_STEPS), 0.0)
                for i in range(NULL_CIRCLE_STEPS)]
        segs = _loop(ring)
    elif display == "Rectangle":
        segs = _loop([(-r, -h, 0.0), (r, -h, 0.0), (r, h, 0.0), (-r, h, 0.0)])
    elif display == "Diamond":
        segs = _loop([(r, 0.0, 0.0), (0.0, h, 0.0), (-r, 0.0, 0.0), (0.0, -h, 0.0)])
    elif display == "Hexagon":
        segs = _loop([(r * math.cos(math.pi * i / 3), h * math.sin(math.pi * i / 3), 0.0)
                      for i in range(6)])
    elif display == "Pyramid":
        base = [(-r, -h, 0.0), (r, -h, 0.0), (r, h, 0.0), (-r, h, 0.0)]
        segs = _loop(base)
        apex = (0.0, 0.0, r)
        segs += [(corner, apex) for corner in base]
    elif display == "Cube":
        lo = [(-r, -h, -r), (r, -h, -r), (r, h, -r), (-r, h, -r)]
        hi = [(x, y, r) for x, y, _z in lo]
        segs = _loop(lo) + _loop(hi) + list(zip(lo, hi))
    return np.asarray(segs, float).reshape(-1, 2, 3)


def _build_null(_p: dict, _inputs: list) -> Mesh:
    return Mesh.empty()


NULL = register(ObjectSpec(
    id="null",
    label="Null",
    category="null",
    build=_build_null,
    params=(
        Param("display", "Display", "choice", "Dot", choices=NULL_DISPLAYS, group="Object"),
        Param("radius", "Radius", "distance", 10.0, minimum=0.0, group="Object"),
        Param("aspect_ratio", "Aspect Ratio", "float", 1.0, minimum=0.0, step=0.1, group="Object"),
        Param("orientation", "Orientation", "choice", "Camera", choices=NULL_ORIENTATIONS,
              group="Object"),
    ),
    inputs="none",
    icon="null",
    description="Empty object that groups its children without changing them",
))

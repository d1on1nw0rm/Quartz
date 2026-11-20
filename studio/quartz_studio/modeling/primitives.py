from __future__ import annotations

import math
from typing import Callable

import numpy as np

from ..scene import Mesh
from .meshkit import clean_polygons

__all__ = [
    "PRIMITIVES",
    "capsule",
    "cone",
    "cube",
    "cylinder",
    "disc",
    "oil_tank",
    "platonic",
    "plane",
    "pyramid",
    "sphere",
    "torus",
    "tube",
]

TAU = 2.0 * math.pi
PHI = (1.0 + 5.0 ** 0.5) / 2.0

Vec = tuple[float, float, float]


class _Builder:

    def __init__(self) -> None:
        self.points: list[Vec] = []
        self.index: dict[Vec, int] = {}
        self.polygons: list[tuple[int, ...]] = []

    def vertex(self, x: float, y: float, z: float) -> int:
        key = (round(x, 9), round(y, 9), round(z, 9))
        found = self.index.get(key)
        if found is None:
            found = len(self.points)
            self.index[key] = found
            self.points.append((float(x), float(y), float(z)))
        return found

    def face(self, corners: list[int], hint: Vec | None = None) -> None:
        pts = np.array([self.points[i] for i in corners], float)
        nxt = np.roll(pts, -1, axis=0)
        normal = np.array([
            np.sum((pts[:, 1] - nxt[:, 1]) * (pts[:, 2] + nxt[:, 2])),
            np.sum((pts[:, 2] - nxt[:, 2]) * (pts[:, 0] + nxt[:, 0])),
            np.sum((pts[:, 0] - nxt[:, 0]) * (pts[:, 1] + nxt[:, 1])),
        ])
        target = pts.mean(axis=0) if hint is None else np.asarray(hint, float)
        ring = tuple(corners)
        if float(normal @ target) < 0.0:
            ring = tuple(reversed(ring))
        self.polygons.append(ring)

    def mesh(self) -> Mesh:
        return Mesh(np.array(self.points, float).reshape(-1, 3), clean_polygons(self.polygons))


def _ring(b: _Builder, y: float, radius: float, rot: int) -> list[int]:
    return [b.vertex(radius * math.cos(TAU * j / rot), y, radius * math.sin(TAU * j / rot))
            for j in range(rot)]


def _strip(b: _Builder, first: list[int], second: list[int], sign: float = 0.0) -> None:
    n = len(first)
    for j in range(n):
        k = (j + 1) % n
        hint = None
        if sign:
            mid = TAU * (j + 0.5) / n
            hint = (sign * math.cos(mid), 0.0, sign * math.sin(mid))
        b.face([first[j], first[k], second[k], second[j]], hint)


def _planar(b: _Builder, y: float, inner: float, outer: float, rot: int, segs: int, up: bool) -> None:
    radii = [inner + (outer - inner) * k / segs for k in range(segs + 1)]
    center = radii[0] <= 0.0
    if center:
        radii = radii[1:]
    rings = [_ring(b, y, r, rot) for r in radii]
    hint = (0.0, 1.0 if up else -1.0, 0.0)
    if center:
        b.face(rings[0], hint)
    for lo, hi in zip(rings, rings[1:]):
        for j in range(rot):
            k = (j + 1) % rot
            b.face([lo[j], lo[k], hi[k], hi[j]], hint)


def _capped_body(radius: float, bottom_eq: float, top_eq: float, dome_bottom: float, dome_top: float,
                 body_segs: int, cap_segs: int, rot: int) -> Mesh:
    b = _Builder()
    levels: list[tuple[float, float]] = [(bottom_eq - dome_bottom, 0.0)]
    for i in range(cap_segs - 1, 0, -1):
        beta = (math.pi / 2.0) * i / cap_segs
        levels.append((bottom_eq - dome_bottom * math.sin(beta), radius * math.cos(beta)))
    for k in range(body_segs + 1):
        levels.append((bottom_eq + (top_eq - bottom_eq) * k / body_segs, radius))
    for i in range(1, cap_segs):
        beta = (math.pi / 2.0) * i / cap_segs
        levels.append((top_eq + dome_top * math.sin(beta), radius * math.cos(beta)))
    levels.append((top_eq + dome_top, 0.0))
    rings = [_ring(b, y, rho, rot) for y, rho in levels]
    for lo, hi in zip(rings, rings[1:]):
        _strip(b, lo, hi)
    return b.mesh()


def _torus_point(big: float, small: float, theta: float, phi: float) -> Vec:
    rho = big + small * math.cos(phi)
    return (rho * math.cos(theta), small * math.sin(phi), rho * math.sin(theta))


def plane(width: float = 400.0, height: float = 400.0, width_segments: int = 10,
          height_segments: int = 10) -> Mesh:
    w = max(0.0, float(width))
    d = max(0.0, float(height))
    ws = max(1, int(width_segments))
    hs = max(1, int(height_segments))
    b = _Builder()
    grid = [[b.vertex(-w / 2.0 + w * i / ws, 0.0, -d / 2.0 + d * j / hs) for i in range(ws + 1)]
            for j in range(hs + 1)]
    hint = (0.0, 1.0, 0.0)
    for j in range(hs):
        for i in range(ws):
            b.face([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]], hint)
    return b.mesh()


def disc(inner_radius: float = 0.0, outer_radius: float = 100.0, disc_segments: int = 1,
         rotation_segments: int = 16) -> Mesh:
    inner = max(0.0, float(inner_radius))
    outer = float(outer_radius)
    if outer <= inner:
        return Mesh.empty()
    b = _Builder()
    _planar(b, 0.0, inner, outer, max(3, int(rotation_segments)), max(1, int(disc_segments)), True)
    return b.mesh()


def sphere(radius: float = 100.0, segments: int = 16) -> Mesh:
    r = max(0.0, float(radius))
    seg = max(3, int(segments))
    rings = max(2, seg // 2)
    b = _Builder()
    levels: list[list[int]] = []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        rho = r * math.sin(phi) if 0 < i < rings else 0.0
        levels.append(_ring(b, r * math.cos(phi), rho, seg))
    for lo, hi in zip(levels, levels[1:]):
        _strip(b, lo, hi)
    return b.mesh()


def cylinder(radius: float = 50.0, height: float = 200.0, height_segments: int = 4,
             rotation_segments: int = 16, caps: bool = True, cap_segments: int = 1) -> Mesh:
    r = max(0.0, float(radius))
    if r <= 0.0:
        return Mesh.empty()
    h = max(0.0, float(height))
    hs = max(1, int(height_segments))
    rot = max(3, int(rotation_segments))
    cs = max(1, int(cap_segments))
    b = _Builder()
    rings = [_ring(b, -h / 2.0 + h * k / hs, r, rot) for k in range(hs + 1)]
    for lo, hi in zip(rings, rings[1:]):
        _strip(b, lo, hi)
    if caps and r > 0.0:
        _planar(b, -h / 2.0, 0.0, r, rot, cs, False)
        _planar(b, h / 2.0, 0.0, r, rot, cs, True)
    return b.mesh()


def cone(top_radius: float = 0.0, bottom_radius: float = 100.0, height: float = 200.0,
         height_segments: int = 4, rotation_segments: int = 16, caps: bool = True) -> Mesh:
    top = max(0.0, float(top_radius))
    bottom = max(0.0, float(bottom_radius))
    h = max(0.0, float(height))
    hs = max(1, int(height_segments))
    rot = max(3, int(rotation_segments))
    b = _Builder()
    rings = [_ring(b, -h / 2.0 + h * k / hs, bottom + (top - bottom) * k / hs, rot)
             for k in range(hs + 1)]
    for lo, hi in zip(rings, rings[1:]):
        _strip(b, lo, hi)
    if caps:
        if bottom > 0.0:
            _planar(b, -h / 2.0, 0.0, bottom, rot, 1, False)
        if top > 0.0:
            _planar(b, h / 2.0, 0.0, top, rot, 1, True)
    return b.mesh()


def tube(inner_radius: float = 50.0, outer_radius: float = 100.0, height: float = 100.0,
         rotation_segments: int = 16, cap_segments: int = 1, height_segments: int = 1) -> Mesh:
    outer = max(0.0, float(outer_radius))
    inner = max(0.0, float(inner_radius))
    if outer <= inner:
        return Mesh.empty()
    h = max(0.0, float(height))
    rot = max(3, int(rotation_segments))
    cs = max(1, int(cap_segments))
    hs = max(1, int(height_segments))
    b = _Builder()
    outs = [_ring(b, -h / 2.0 + h * k / hs, outer, rot) for k in range(hs + 1)]
    ins = [_ring(b, -h / 2.0 + h * k / hs, inner, rot) for k in range(hs + 1)] if inner > 0.0 else []
    for k in range(hs):
        _strip(b, outs[k], outs[k + 1], 1.0)
        if ins:
            _strip(b, ins[k], ins[k + 1], -1.0)
    _planar(b, -h / 2.0, inner, outer, rot, cs, False)
    _planar(b, h / 2.0, inner, outer, rot, cs, True)
    return b.mesh()


def torus(ring_radius: float = 100.0, ring_segments: int = 16, pipe_radius: float = 50.0,
          pipe_segments: int = 8) -> Mesh:
    big = max(0.0, float(ring_radius))
    small = max(0.0, float(pipe_radius))
    rs = max(3, int(ring_segments))
    ps = max(3, int(pipe_segments))
    b = _Builder()
    grid = [[b.vertex(*_torus_point(big, small, TAU * i / rs, TAU * j / ps)) for j in range(ps)]
            for i in range(rs)]
    for i in range(rs):
        i2 = (i + 1) % rs
        theta = TAU * (i + 0.5) / rs
        for j in range(ps):
            j2 = (j + 1) % ps
            phi = TAU * (j + 0.5) / ps
            hint = (math.cos(phi) * math.cos(theta), math.sin(phi), math.cos(phi) * math.sin(theta))
            b.face([grid[i][j], grid[i2][j], grid[i2][j2], grid[i][j2]], hint)
    return b.mesh()


def pyramid(size: tuple[float, float, float] = (200.0, 200.0, 200.0), segments: int = 1) -> Mesh:
    sx, sy, sz = (max(0.0, float(v)) for v in size)
    s = max(1, int(segments))
    hx, hy, hz = sx / 2.0, sy / 2.0, sz / 2.0
    b = _Builder()
    grid = [[b.vertex(-hx + sx * i / s, -hy, -hz + sz * j / s) for i in range(s + 1)]
            for j in range(s + 1)]
    for j in range(s):
        for i in range(s):
            b.face([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]], (0.0, -1.0, 0.0))
    corners = [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]
    apex = (0.0, hy, 0.0)
    for c in range(4):
        a0 = corners[c]
        a1 = corners[(c + 1) % 4]
        rows: list[list[int]] = []
        for t in range(s + 1):
            f = t / s
            row = []
            for a in range(s + 1):
                u = a / s
                row.append(b.vertex(*[(1.0 - f) * (a0[q] + (a1[q] - a0[q]) * u) + f * apex[q]
                                      for q in range(3)]))
            rows.append(row)
        for t in range(s):
            for a in range(s):
                b.face([rows[t][a], rows[t][a + 1], rows[t + 1][a + 1], rows[t + 1][a]])
    return b.mesh()


def capsule(radius: float = 50.0, height: float = 200.0, height_segments: int = 4,
            cap_segments: int = 4, rotation_segments: int = 16) -> Mesh:
    r = max(0.0, float(radius))
    h = max(0.0, float(height))
    return _capped_body(r, -h / 2.0, h / 2.0, r, r, max(1, int(height_segments)),
                        max(1, int(cap_segments)), max(3, int(rotation_segments)))


def oil_tank(radius: float = 50.0, height: float = 200.0, height_segments: int = 4,
             cap_height: float = 25.0, cap_segments: int = 4, rotation_segments: int = 16) -> Mesh:
    r = max(0.0, float(radius))
    h = max(0.0, float(height))
    cap = min(max(0.0, float(cap_height)), h / 2.0)
    return _capped_body(r, -h / 2.0 + cap, h / 2.0 - cap, cap, cap, max(1, int(height_segments)),
                        max(1, int(cap_segments)), max(3, int(rotation_segments)))


_SOLIDS: dict[str, list[tuple[float, float, float]]] = {
    "Tetrahedron": [(1.0, 1.0, 1.0), (1.0, -1.0, -1.0), (-1.0, 1.0, -1.0), (-1.0, -1.0, 1.0)],
    "Hexahedron": [(x, y, z) for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)],
    "Octahedron": [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, -1.0, 0.0),
                   (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)],
    "Dodecahedron": [(x, y, z) for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)]
    + [(0.0, sy / PHI, sz * PHI) for sy in (-1.0, 1.0) for sz in (-1.0, 1.0)]
    + [(sx / PHI, sy * PHI, 0.0) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
    + [(sx * PHI, 0.0, sz / PHI) for sx in (-1.0, 1.0) for sz in (-1.0, 1.0)],
    "Icosahedron": [(0.0, sy, sz * PHI) for sy in (-1.0, 1.0) for sz in (-1.0, 1.0)]
    + [(sx, sy * PHI, 0.0) for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
    + [(sx * PHI, 0.0, sz) for sx in (-1.0, 1.0) for sz in (-1.0, 1.0)],
}


def _facets(points: np.ndarray) -> list[list[int]]:
    found: dict[frozenset[int], None] = {}
    count = len(points)
    for i in range(count):
        for j in range(i + 1, count):
            for k in range(j + 1, count):
                normal = np.cross(points[j] - points[i], points[k] - points[i])
                length = float(np.linalg.norm(normal))
                if length < 1e-9:
                    continue
                normal = normal / length
                offset = points @ normal - float(points[i] @ normal)
                if np.all(offset <= 1e-9) or np.all(offset >= -1e-9):
                    found[frozenset(np.flatnonzero(np.abs(offset) <= 1e-9).tolist())] = None
    faces: list[list[int]] = []
    for members in found:
        idx = sorted(members)
        center = points[idx].mean(axis=0)
        outward = center / np.linalg.norm(center)
        u = points[idx[0]] - center
        u = u / np.linalg.norm(u)
        v = np.cross(outward, u)
        angles = [math.atan2(float((points[i] - center) @ v), float((points[i] - center) @ u))
                  for i in idx]
        faces.append([idx[m] for m in sorted(range(len(idx)), key=lambda m: angles[m])])
    return faces


def platonic(radius: float = 100.0, kind: str = "Icosahedron") -> Mesh:
    r = max(0.0, float(radius))
    if r <= 0.0:
        return Mesh.empty()
    name = str(kind) if str(kind) in _SOLIDS else "Icosahedron"
    raw = np.array(_SOLIDS[name], float)
    unit = raw / np.linalg.norm(raw, axis=1)[:, None]
    b = _Builder()
    ids = [b.vertex(*(unit[i] * r)) for i in range(len(unit))]
    for face in _facets(unit):
        b.face([ids[i] for i in face])
    return b.mesh()


def cube(size: tuple[float, float, float] = (200.0, 200.0, 200.0),
         segments: tuple[int, int, int] = (1, 1, 1)) -> Mesh:
    dims = [max(0.0, float(v)) for v in size]
    segs = [max(1, int(v)) for v in segments]
    b = _Builder()
    for axis in range(3):
        u = (axis + 1) % 3
        v = (axis + 2) % 3
        for sign in (-1.0, 1.0):
            grid: list[list[int]] = []
            for j in range(segs[v] + 1):
                row = []
                for i in range(segs[u] + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis] = sign * dims[axis] / 2.0
                    p[u] = -dims[u] / 2.0 + dims[u] * i / segs[u]
                    p[v] = -dims[v] / 2.0 + dims[v] * j / segs[v]
                    row.append(b.vertex(*p))
                grid.append(row)
            hint = [0.0, 0.0, 0.0]
            hint[axis] = sign
            for j in range(segs[v]):
                for i in range(segs[u]):
                    b.face([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]], tuple(hint))
    return b.mesh()


PRIMITIVES: dict[str, tuple[str, Callable[[], Mesh]]] = {
    "Plane": ("Plane", plane),
    "Disc": ("Disc", disc),
    "Sphere": ("Sphere", sphere),
    "Cylinder": ("Cylinder", cylinder),
    "Cone": ("Cone", cone),
    "Tube": ("Tube", tube),
    "Torus": ("Torus", torus),
    "Pyramid": ("Pyramid", pyramid),
    "Capsule": ("Capsule", capsule),
    "Oil Tank": ("Oil Tank", oil_tank),
    "Platonic": ("Platonic", platonic),
}

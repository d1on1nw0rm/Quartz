from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

import numpy as np

from ..scene import Mesh
from .meshkit import (OpResult, Selection, clone, compact, edge_faces, edge_key, face_groups,
                      face_normals, point_faces, point_normals_for_faces, region_boundary)
from .registry import Param, ToolSpec, register

__all__ = ["bevel"]

_EPS = 1e-9


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > _EPS else np.zeros(3)


class _Points:

    def __init__(self, base: np.ndarray) -> None:
        self.base = np.array(base, float).reshape(-1, 3)
        self.extra: list[np.ndarray] = []

    def __len__(self) -> int:
        return len(self.base) + len(self.extra)

    def add(self, pos) -> int:
        self.extra.append(np.array(pos, float))
        return len(self) - 1

    def get(self, i: int) -> np.ndarray:
        n = len(self.base)
        return self.base[i] if i < n else self.extra[i - n]

    def set(self, i: int, pos) -> None:
        n = len(self.base)
        if i < n:
            self.base[i] = pos
        else:
            self.extra[i - n] = np.array(pos, float)

    def array(self) -> np.ndarray:
        if not self.extra:
            return self.base.copy()
        return np.vstack([self.base, np.array(self.extra)])


@dataclass
class _Shape:
    segments: int
    solid: bool
    flat: bool
    exponent: float
    depth: float

    def profile(self, s: np.ndarray, e: np.ndarray, k: np.ndarray) -> list[np.ndarray]:
        if self.solid:
            return self._solid(s, e, k)
        n = self.segments
        c = s + e - k
        out = []
        for j in range(n + 1):
            t = j / n
            flat = s + (e - s) * t
            if self.flat or self.depth == 0.0:
                out.append(flat)
                continue
            theta = t * math.pi / 2.0
            x = max(math.cos(theta), 0.0) ** (2.0 / self.exponent)
            y = max(math.sin(theta), 0.0) ** (2.0 / self.exponent)
            shaped = c + (s - c) * x + (e - c) * y
            out.append(flat + (shaped - flat) * self.depth)
        out[0] = np.array(s, float)
        out[-1] = np.array(e, float)
        return out

    def _solid(self, s: np.ndarray, e: np.ndarray, k: np.ndarray) -> list[np.ndarray]:
        half = self.segments // 2
        first = [s + (k - s) * (j / half) for j in range(half + 1)]
        second = [k + (e - k) * (j / half) for j in range(1, half + 1)]
        return first + second

    def rounded(self) -> bool:
        return not self.solid and not self.flat and abs(self.depth) > _EPS and abs(self.exponent - 1.0) > 1e-6


def _shape(p: dict, solid: bool) -> _Shape:
    sub = max(0, int(p["subdivision"]))
    segments = 2 * (sub + 1) if solid else sub + 1
    return _Shape(segments, solid, p["shape"] != "Round",
                  2.0 ** (float(p["tension"]) / 100.0), float(p["depth"]) / 100.0)


def _variations(p: dict, count: int) -> list[float]:
    amount = max(0.0, float(p.get("variance", 0.0))) / 100.0
    if amount <= 0.0:
        return [1.0] * count
    rng = random.Random(int(p.get("seed", 12345)))
    return [max(0.0, 1.0 + amount * rng.uniform(-1.0, 1.0)) for _ in range(count)]


def _owners(mesh: Mesh) -> dict[tuple[int, int], int]:
    out: dict[tuple[int, int], int] = {}
    for k, poly in enumerate(mesh.polygons):
        for a, b in zip(poly, poly[1:] + poly[:1]):
            out[(a, b)] = k
    return out


def _fan(mesh: Mesh, v: int, owner: dict, faces: list[int]):
    corners = {}
    for f in faces:
        poly = mesh.polygons[f]
        if poly.count(v) != 1:
            return None
        i = poly.index(v)
        corners[f] = (poly[i - 1], poly[(i + 1) % len(poly)])
    if not corners:
        return None
    start = next((f for f in sorted(corners) if (v, corners[f][0]) not in owner), None)
    closed = start is None
    if closed:
        start = min(corners)
    order: list[int] = []
    seen: set[int] = set()
    f = start
    while f is not None and f not in seen and f in corners:
        order.append(f)
        seen.add(f)
        f = owner.get((corners[f][1], v))
    if len(order) != len(corners) or (closed and f != start):
        return None
    return [(g, corners[g][0], corners[g][1]) for g in order], closed


def _dedup(seq: list[int], closed: bool) -> list[int]:
    out: list[int] = []
    for i in seq:
        if not out or out[-1] != i:
            out.append(i)
    while closed and len(out) > 1 and out[0] == out[-1]:
        out.pop()
    return out


def _degenerate(cycle: list[int]) -> bool:
    if len(set(cycle)) < 3:
        return True
    counts = Counter(edge_key(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle)))
    return all(c >= 2 for c in counts.values())


def _sphere(points: list[np.ndarray]):
    pts = np.asarray(points, float)
    if len(pts) < 4:
        return None
    mean = pts.mean(axis=0)
    local = pts - mean
    size = float(np.linalg.norm(local.max(axis=0) - local.min(axis=0)))
    if size < _EPS:
        return None
    a = np.hstack([2.0 * local, np.ones((len(local), 1))])
    b = (local * local).sum(axis=1)
    sol, _, rank, sv = np.linalg.lstsq(a, b, rcond=None)
    if rank < 4 or sv[-1] < 1e-7 * sv[0]:
        return None
    center = sol[:3]
    r2 = float(sol[3] + center @ center)
    if r2 <= 0.0:
        return None
    radius = math.sqrt(r2)
    if radius > 50.0 * size:
        return None
    if float(np.abs(np.linalg.norm(local - center, axis=1) - radius).max()) > 0.2 * radius:
        return None
    return center + mean, radius


def _project(x: np.ndarray, sphere) -> np.ndarray:
    center, radius = sphere
    d = x - center
    length = float(np.linalg.norm(d))
    if length < _EPS:
        return x
    return center + d / length * radius


def _along(positions: list[np.ndarray], f: float) -> np.ndarray:
    u = f * (len(positions) - 1)
    i = min(int(math.floor(u)), len(positions) - 2)
    t = u - i
    return positions[i] + (positions[i + 1] - positions[i]) * t


def _rings(pts: _Points, sides: list[list[int]], center: np.ndarray):
    n = len(sides)
    side_pos = [[pts.get(i) for i in side] for side in sides]
    total = (len(sides[0]) - 1) / 2.0
    outer = [list(side) for side in sides]
    faces: list[tuple[int, ...]] = []
    inner_ids: list[int] = []
    r = 0
    while True:
        size = len(outer[0]) - 1
        if size <= 1:
            faces.append(tuple(side[0] for side in outer))
            return faces, inner_ids
        if size == 2:
            c = pts.add(center)
            inner_ids.append(c)
            for k in range(n):
                faces.append((outer[k - 1][1], outer[k][0], outer[k][1], c))
            return faces, inner_ids
        r += 1
        t = r / total
        inner_size = size - 2
        inner = []
        for k in range(n):
            row = []
            for j in range(inner_size):
                anchor = _along(side_pos[k], j / inner_size)
                idx = pts.add(anchor + (center - anchor) * t)
                row.append(idx)
                inner_ids.append(idx)
            inner.append(row)
        for k in range(n):
            inner[k].append(inner[(k + 1) % n][0])
        for k in range(n):
            faces.append((outer[k - 1][size - 1], outer[k][0], outer[k][1], inner[k][0]))
            for j in range(inner_size):
                faces.append((outer[k][j + 1], outer[k][j + 2], inner[k][j + 1], inner[k][j]))
        outer = inner


def _radial(pts: _Points, cycle: list[int], center: np.ndarray, segments: int):
    count = len(cycle)
    loops = (segments - 1) // 2
    base = [pts.get(i) for i in cycle]
    prev = list(cycle)
    faces: list[tuple[int, ...]] = []
    inner_ids: list[int] = []
    for r in range(1, loops + 1):
        t = r / (loops + 1)
        ring = [pts.add(base[i] + (center - base[i]) * t) for i in range(count)]
        inner_ids.extend(ring)
        for i in range(count):
            j = (i + 1) % count
            faces.append((prev[i], prev[j], ring[j], ring[i]))
        prev = ring
    c = pts.add(center)
    inner_ids.append(c)
    for i in range(count):
        faces.append((prev[i], prev[(i + 1) % count], c))
    return faces, inner_ids


def _tri_grid(pts: _Points, sides: list[list[int]]):
    s = len(sides[0]) - 1
    ca, cb, cc = (pts.get(side[0]) for side in sides)
    grid: dict[tuple[int, int], int] = {}
    inner_ids: list[int] = []
    for a in range(s + 1):
        for b in range(s + 1 - a):
            i = s - a - b
            if b == 0:
                grid[(a, b)] = sides[0][a]
            elif i == 0:
                grid[(a, b)] = sides[1][b]
            elif a == 0:
                grid[(a, b)] = sides[2][s - b]
            else:
                idx = pts.add((ca * i + cb * a + cc * b) / s)
                grid[(a, b)] = idx
                inner_ids.append(idx)
    faces: list[tuple[int, ...]] = []
    for a in range(s):
        for b in range(s - a):
            faces.append((grid[(a, b)], grid[(a + 1, b)], grid[(a, b + 1)]))
            if a + b <= s - 2:
                faces.append((grid[(a + 1, b)], grid[(a + 1, b + 1)], grid[(a, b + 1)]))
    return faces, inner_ids


def _relax(pts: _Points, faces: list[tuple[int, ...]], inner: list[int], iterations: int = 40) -> None:
    neighbors: dict[int, set[int]] = {i: set() for i in inner}
    for poly in faces:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if a in neighbors:
                neighbors[a].add(b)
            if b in neighbors:
                neighbors[b].add(a)
    for _ in range(iterations):
        moved = {i: np.mean([pts.get(j) for j in ns], axis=0) for i, ns in neighbors.items() if ns}
        for i, pos in moved.items():
            pts.set(i, pos)


def _round_points(pts: _Points, inner: list[int], boundary: list[int]) -> None:
    if not inner:
        return
    sphere = _sphere([pts.get(i) for i in dict.fromkeys(boundary)])
    if sphere is None:
        return
    for i in inner:
        pts.set(i, _project(pts.get(i), sphere))


def _fill_corner(pts: _Points, sides: list[list[int]], p: dict, rounded: bool,
                 center: np.ndarray | None) -> list[tuple[int, ...]]:
    s = len(sides[0]) - 1
    cycle = [side[k] for side in sides for k in range(s)]
    mode = p["mitering"]
    if p["corner_ngons"] or (s == 1 and mode != "Radial"):
        return [tuple(cycle)]
    if center is None:
        center = np.mean([pts.get(i) for i in cycle], axis=0)
    if mode == "Radial":
        faces, inner = _radial(pts, cycle, center, s)
    elif mode == "Uniform" and len(sides) == 3:
        faces, inner = _tri_grid(pts, sides)
    else:
        faces, inner = _rings(pts, sides, center)
    if mode == "Patch" or (mode == "Uniform" and len(sides) == 3):
        _relax(pts, faces, inner)
    if rounded:
        _round_points(pts, inner, cycle)
    return faces


def _planar(pts: _Points, cycle: list[int]) -> bool:
    arr = np.array([pts.get(i) for i in cycle], float)
    local = arr - arr.mean(axis=0)
    size = float(np.linalg.norm(arr.max(axis=0) - arr.min(axis=0)))
    if size < _EPS:
        return False
    _, _, vt = np.linalg.svd(local, full_matrices=False)
    return float(np.abs(local @ vt[2]).max()) <= 1e-7 * size


def _flat_cycle(pts: _Points, cycle: list[int]) -> bool:
    arr = np.array([pts.get(i) for i in cycle], float)
    size = float(np.linalg.norm(arr.max(axis=0) - arr.min(axis=0)))
    if size < _EPS:
        return True
    area = np.cross(arr, np.roll(arr, -1, axis=0)).sum(axis=0)
    return float(np.linalg.norm(area)) <= 1e-9 * size * size


def _seam(polys: list[tuple[int, ...]], pts: _Points, joints: set[int]) -> list[tuple[int, ...]]:
    if not joints:
        return polys
    ids = sorted(joints)
    xyz = np.array([pts.get(i) for i in ids], float)
    out: list[tuple[int, ...]] = []
    for poly in polys:
        ring: list[int] = []
        for a, b in zip(poly, poly[1:] + poly[:1]):
            ring.append(a)
            pa, pb = pts.get(a), pts.get(b)
            d = pb - pa
            length2 = float(d @ d)
            if length2 < _EPS:
                continue
            t = (xyz - pa) @ d / length2
            off = np.linalg.norm(pa + np.outer(t, d) - xyz, axis=1)
            hit = np.flatnonzero((t > 1e-9) & (t < 1.0 - 1e-9) & (off <= 1e-7 * math.sqrt(length2)))
            found = sorted((float(t[k]), ids[k]) for k in hit if ids[k] not in (a, b))
            ring.extend(i for _, i in found)
        out.append(tuple(ring))
    return out


def _fill_partial(pts: _Points, cycle: list[int], p: dict, rounded: bool) -> list[tuple[int, ...]]:
    if p["corner_ngons"] or len(cycle) <= 4 or _planar(pts, cycle):
        return [tuple(cycle)]
    center = np.mean([pts.get(i) for i in cycle], axis=0)
    c = pts.add(center)
    if rounded:
        _round_points(pts, [c], cycle)
    return [(cycle[i], cycle[(i + 1) % len(cycle)], c) for i in range(len(cycle))]


def _orient(faces: list[tuple[int, ...]], directed: set[tuple[int, int]]) -> list[tuple[int, ...]]:
    for poly in faces:
        for a, b in zip(poly, poly[1:] + poly[:1]):
            if (a, b) in directed:
                return [tuple(reversed(q)) for q in faces]
    return faces


def _splice(poly: tuple[int, ...], patch: tuple[int, ...]) -> tuple[int, ...] | None:
    m = len(patch)
    where = {(patch[i], patch[(i + 1) % m]): i for i in range(m)}
    for i in range(len(poly)):
        x, y = poly[i], poly[(i + 1) % len(poly)]
        j = where.get((y, x))
        if j is not None:
            path = [patch[(j + 1 + k) % m] for k in range(m)]
            return tuple(poly[:i + 1]) + tuple(path[1:-1]) + tuple(poly[i + 1:])
    return None


def _directed(polys) -> set[tuple[int, int]]:
    return {(a, b) for poly in polys for a, b in zip(poly, poly[1:] + poly[:1])}


def _strip(first: list[int], second: list[int], ngon: bool) -> list[tuple[int, ...]]:
    if ngon and len(first) > 2:
        return [tuple(first) + tuple(reversed(second))]
    return [(first[j], first[j + 1], second[j + 1], second[j]) for j in range(len(first) - 1)]


def _weld_targets(arr: np.ndarray, first_new: int) -> dict[int, int]:
    if len(arr) == 0:
        return {}
    span = float(np.linalg.norm(arr.max(axis=0) - arr.min(axis=0)))
    tol = 1e-6 * max(span, 1.0)
    cells: dict[tuple[int, int, int], list[int]] = {}
    keys = np.floor(arr / tol).astype(np.int64)
    root: dict[int, int] = {}
    for i in range(len(arr)):
        kx, ky, kz = (int(x) for x in keys[i])
        if i >= first_new:
            hit = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for j in cells.get((kx + dx, ky + dy, kz + dz), ()):
                            if float(np.linalg.norm(arr[i] - arr[j])) <= tol and (hit is None or j < hit):
                                hit = j
            if hit is not None:
                root[i] = hit
                continue
        cells.setdefault((kx, ky, kz), []).append(i)
    return root


def _clean_ring(ring) -> tuple[int, ...] | None:
    out = _dedup(list(ring), True)
    if len(out) < 3 or len(set(out)) != len(out):
        return None
    return tuple(out)


def _finish(mesh: Mesh, pts: _Points, polys: list[tuple[int, ...]],
            removable: set[int]) -> tuple[Mesh, dict[int, int], dict[int, int]]:
    n = len(mesh.points)
    arr = pts.array()
    root = _weld_targets(arr, n)
    kept: list[tuple[int, ...]] = []
    poly_map: dict[int, int] = {}
    for k, poly in enumerate(polys):
        ring = _clean_ring(root.get(i, i) for i in poly)
        if ring is not None:
            poly_map[k] = len(kept)
            kept.append(ring)
    out = Mesh(arr, kept, mesh.loose_edges)
    keep = [i for i in range(n) if i not in removable]
    compacted, remap = compact(out, keep)
    full = {i: remap[root.get(i, i)] for i in range(len(arr)) if root.get(i, i) in remap}
    return compacted, full, poly_map


def _side_limit(mesh: Mesh, f: int, a: int, b: int) -> float:
    poly = mesh.polygons[f]
    i = poly.index(a)
    pa, pb = mesh.points[a], mesh.points[b]
    along = _unit(pb - pa)
    best = math.inf
    for x, y in ((a, poly[i - 1]), (b, poly[(i + 2) % len(poly)])):
        side = mesh.points[y] - mesh.points[x]
        length = float(np.linalg.norm(side))
        sin = float(np.linalg.norm(np.cross(along, _unit(side))))
        best = min(best, length * max(sin, 0.05))
    return best


def _side_length(mesh: Mesh, f: int, a: int, b: int) -> float:
    poly = mesh.polygons[f]
    i = poly.index(a)
    lengths = [float(np.linalg.norm(mesh.points[poly[i - 1]] - mesh.points[a])),
               float(np.linalg.norm(mesh.points[poly[(i + 2) % len(poly)]] - mesh.points[b]))]
    return min(lengths)


def _edge_offsets(mesh: Mesh, bev: set, owner: dict, normals: np.ndarray, p: dict) -> dict:
    mode = p["offset_mode"]
    value = max(0.0, float(p["offset"]))
    out = {}
    ordered = sorted(bev)
    for (a, b), scale in zip(ordered, _variations(p, len(ordered))):
        f1, f2 = owner[(a, b)], owner[(b, a)]
        if mode == "Radial":
            cos = float(np.clip(normals[f1] @ normals[f2], -1.0, 1.0))
            beta = min(math.acos(cos), math.radians(179.0))
            d = value * math.tan(beta / 2.0)
        elif mode == "Proportional":
            side = min(_side_length(mesh, f1, a, b), _side_length(mesh, f2, b, a))
            d = min(value, 100.0) / 100.0 * 0.5 * side
        else:
            d = value
        d *= scale
        if p["limit"]:
            d = min(d, 0.5 * min(_side_limit(mesh, f1, a, b), _side_limit(mesh, f2, b, a)))
        out[(a, b)] = d
    return out


class _EdgeBevel:

    def __init__(self, mesh: Mesh, bev: set, owner: dict, p: dict) -> None:
        self.mesh = mesh
        self.bev = bev
        self.owner = owner
        self.p = p
        self.pts = _Points(mesh.points)
        self.normals = face_normals(mesh)
        self.shape = _shape(p, p["bevel_mode"] == "Solid")
        self.offsets = _edge_offsets(mesh, bev, owner, self.normals, p)
        self.verts = {i for e in bev for i in e}
        self.rep: dict[tuple[int, int], list[int]] = {}
        self.rail: dict[tuple[int, int], int] = {}
        self.slides: set[int] = set()
        self.arcs: dict = {}
        self.joints: set[int] = set()

    def bevel_count(self, v: int, corners) -> int:
        edges = {edge_key(u, v) for _, u, _ in corners} | {edge_key(v, w) for _, _, w in corners}
        return len(edges & self.bev)

    def build_corners(self, v: int, fan) -> None:
        corners, _ = fan
        nb = self.bevel_count(v, corners)
        if nb == 1 and self.p["ending"] == "Inset":
            self.inset_corners(v, corners)
            return
        self.slide_corners(v, corners, nb == 1 and self.p["ending"] == "Default")

    def frame(self, f: int, u: int, v: int, w: int):
        n = self.normals[f]
        pv = self.pts.get(v)
        in_in = _unit(np.cross(n, pv - self.pts.get(u)))
        in_out = _unit(np.cross(n, self.pts.get(w) - pv))
        return pv, in_in, in_out

    def slide_distance(self, pv: np.ndarray, other: int, inward: np.ndarray, offset: float, along: bool) -> float:
        if along:
            return offset
        d = _unit(self.pts.get(other) - pv)
        s = float(d @ inward)
        return offset / s if s > 0.05 else offset

    def slide_corners(self, v: int, corners, along: bool) -> None:
        cand: dict[tuple[int, int], list[float]] = {}
        for f, u, w in corners:
            ein, eout = edge_key(u, v), edge_key(v, w)
            pv, in_in, in_out = self.frame(f, u, v, w)
            if ein in self.bev and eout not in self.bev:
                cand.setdefault(eout, []).append(self.slide_distance(pv, w, in_in, self.offsets[ein], along))
            if eout in self.bev and ein not in self.bev:
                cand.setdefault(ein, []).append(self.slide_distance(pv, u, in_out, self.offsets[eout], along))
        pv = self.pts.get(v)
        slide = {}
        for e, ds in cand.items():
            other = e[0] if e[1] == v else e[1]
            direction = self.pts.get(other) - pv
            length = float(np.linalg.norm(direction))
            d = float(np.mean(ds))
            if self.p["limit"]:
                d = min(d, length * (0.5 if other in self.verts else 0.99))
            idx = self.pts.add(pv + _unit(direction) * d)
            slide[e] = idx
            self.slides.add(idx)
        for f, u, w in corners:
            ein, eout = edge_key(u, v), edge_key(v, w)
            if ein in self.bev and eout in self.bev:
                idx = self.pts.add(self.miter_point(f, u, v, w))
                self.rep[(f, v)] = [idx]
                self.rail[(f, v)] = idx
            elif ein in self.bev or eout in self.bev:
                idx = slide[eout] if ein in self.bev else slide[ein]
                self.rep[(f, v)] = [idx]
                self.rail[(f, v)] = idx
            else:
                self.rep[(f, v)] = _dedup([slide.get(ein, v), slide.get(eout, v)], False)

    def miter_point(self, f: int, u: int, v: int, w: int) -> np.ndarray:
        pv, in_in, in_out = self.frame(f, u, v, w)
        o_in = self.offsets[edge_key(u, v)]
        o_out = self.offsets[edge_key(v, w)]
        c = float(in_in @ in_out)
        det = 1.0 - c * c
        if det < 1e-9:
            return pv + in_in * o_in
        alpha = (o_in - c * o_out) / det
        beta = (o_out - c * o_in) / det
        return pv + in_in * alpha + in_out * beta

    def inset_corners(self, v: int, corners) -> None:
        pv = self.pts.get(v)
        for f, u, w in corners:
            ein, eout = edge_key(u, v), edge_key(v, w)
            n = self.normals[f]
            if ein in self.bev or eout in self.bev:
                other, e = (u, ein) if ein in self.bev else (w, eout)
                po = self.pts.get(other)
                o = self.offsets[e]
                step = o
                if self.p["limit"]:
                    step = min(step, 0.45 * float(np.linalg.norm(po - pv)))
                perp = _unit(np.cross(n, pv - po)) if ein in self.bev else _unit(np.cross(n, po - pv))
                idx = self.pts.add(pv + _unit(po - pv) * step + perp * o)
                self.rep[(f, v)] = [idx, v] if ein in self.bev else [v, idx]
                self.rail[(f, v)] = idx
            else:
                self.rep[(f, v)] = [v]

    def arc(self, v: int, s: int, e: int, other: int) -> list[int]:
        key = (v, frozenset((s, e)))
        hit = self.arcs.get(key)
        if hit is not None:
            return list(hit) if hit[0] == s else list(reversed(hit))
        pv, ps, pe = self.pts.get(v), self.pts.get(s), self.pts.get(e)
        if s in self.slides or e in self.slides:
            k = pv
        else:
            d = _unit(self.pts.get(other) - pv)
            k = pv + d * max(0.0, min(float((ps - pv) @ d), float((pe - pv) @ d)))
        prof = self.shape.profile(ps, pe, k)
        chain = [s] + [self.pts.add(x) for x in prof[1:-1]] + [e]
        self.arcs[key] = chain
        return list(chain)

    def strips(self) -> tuple[list[tuple[int, ...]], set]:
        polys: list[tuple[int, ...]] = []
        rails = set()
        for a, b in sorted(self.bev):
            f1, f2 = self.owner[(a, b)], self.owner[(b, a)]
            arc_a = self.arc(a, self.rail[(f1, a)], self.rail[(f2, a)], b)
            arc_b = self.arc(b, self.rail[(f1, b)], self.rail[(f2, b)], a)
            polys.extend(_strip(arc_a, arc_b, self.p["rounding_ngons"]))
            rails.add((self.rail[(f1, a)], self.rail[(f1, b)]))
            rails.add((self.rail[(f2, a)], self.rail[(f2, b)]))
        return polys, rails

    def convex(self, v: int) -> bool:
        for a, b in self.bev:
            if v not in (a, b):
                continue
            f1, f2 = self.owner[(a, b)], self.owner[(b, a)]
            mid = (self.mesh.points[a] + self.mesh.points[b]) / 2.0
            center = self.mesh.points[list(self.mesh.polygons[f2])].mean(axis=0)
            if float((center - mid) @ self.normals[f1]) > 1e-9:
                return False
        return True

    def cycle(self, v: int, corners, closed: bool) -> list[int]:
        out: list[int] = []
        m = len(corners)
        for k, (f, u, w) in enumerate(corners):
            out.extend(self.rep[(f, v)])
            if edge_key(v, w) in self.bev and (closed or k + 1 < m):
                g = corners[(k + 1) % m][0]
                out.extend(self.arc(v, self.rail[(f, v)], self.rail[(g, v)], w)[1:-1])
        return _dedup(out, True)

    def patch(self, v: int, fan):
        corners, closed = fan
        nb = self.bevel_count(v, corners)
        valence = len({edge_key(u, v) for _, u, _ in corners} | {edge_key(v, w) for _, _, w in corners})
        if closed and nb == valence and nb >= 3:
            sides = [self.arc(v, self.rail[(f, v)], self.rail[(corners[(k + 1) % len(corners)][0], v)], w)
                     for k, (f, u, w) in enumerate(corners)]
            center = self.pts.get(v).copy() if self.shape.solid else None
            return _fill_corner(self.pts, sides, self.p, self.shape.rounded(), center), None
        cyc = self.cycle(v, corners, closed)
        if (not closed and v not in cyc) or _degenerate(cyc):
            return [], None
        if _flat_cycle(self.pts, cyc):
            self.joints.update(cyc)
            return [], None
        if nb == 1 and closed and len(corners) == 3 and self.p["ending"] in ("Default", "Extend"):
            end = next(f for f, u, w in corners
                       if edge_key(u, v) not in self.bev and edge_key(v, w) not in self.bev)
            return [tuple(cyc)], end
        mode = self.p["partial_rounding"]
        rounded = self.shape.rounded() and (mode == "Full" or (mode == "Convex" and self.convex(v)))
        return _fill_partial(self.pts, cyc, self.p, rounded), None

    def run(self, fans: dict) -> tuple[list[tuple[int, ...]], set]:
        for v in sorted(fans):
            self.build_corners(v, fans[v])
        strips, rails = self.strips()
        faces: list[tuple[int, ...]] = []
        for f, poly in enumerate(self.mesh.polygons):
            ring: list[int] = []
            for i in poly:
                ring.extend(self.rep.get((f, i), [i]))
            faces.append(tuple(_dedup(ring, True)))
        directed = _directed(faces) | _directed(strips)
        patches: list[tuple[int, ...]] = []
        for v in sorted(fans):
            built, end = self.patch(v, fans[v])
            if not built:
                continue
            built = _orient(built, directed)
            if end is not None:
                merged = _splice(faces[end], built[0])
                if merged is not None:
                    faces[end] = merged
                    continue
            patches.extend(built)
            directed |= _directed(built)
        return _seam(faces + strips + patches, self.pts, self.joints), rails


def _fold_angle(normals: np.ndarray, f1: int, f2: int) -> float:
    c = float(np.clip(normals[f1] @ normals[f2], -1.0, 1.0))
    return math.degrees(math.acos(c))


def _bevel_edges(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    owner = _owners(mesh)
    ef = edge_faces(mesh)
    normals = face_normals(mesh)
    limit = float(p.get("max_angle", 180.0))
    shared = set()
    bev = set()
    for e in sel.edges:
        a, b = edge_key(*e)
        if len(ef.get((a, b), ())) == 2 and (a, b) in owner and (b, a) in owner:
            shared.add((a, b))
            if _fold_angle(normals, owner[(a, b)], owner[(b, a)]) <= limit + 1e-9:
                bev.add((a, b))
    if not shared:
        return OpResult(mesh, sel, False, "Bevel: select edges shared by two polygons")
    if not bev:
        return OpResult(mesh, sel)
    pf = point_faces(mesh)
    fans = {}
    for v in sorted({i for e in bev for i in e}):
        fan = _fan(mesh, v, owner, pf.get(v, []))
        if fan is None:
            return OpResult(mesh, sel, False, f"Bevel: non-manifold geometry at point {v}")
        fans[v] = fan
    job = _EdgeBevel(mesh, bev, owner, p)
    polys, rails = job.run(fans)
    out, remap, _ = _finish(mesh, job.pts, polys, set(fans))
    edges = {edge_key(remap[a], remap[b]) for a, b in rails
             if a in remap and b in remap and remap[a] != remap[b]}
    edges &= set(out.edges)
    return OpResult(out, Selection("edges", edges=edges))


def _point_distance(p: dict, length: float, both: bool) -> float:
    value = max(0.0, float(p["offset"]))
    if p["offset_mode"] == "Proportional":
        d = min(value, 100.0) / 100.0 * 0.5 * length
    else:
        d = value
    if p["limit"]:
        d = min(d, length * (0.5 if both else 0.99))
    return d


def _bevel_points(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    owner = _owners(mesh)
    pf = point_faces(mesh)
    verts = sorted(int(i) for i in sel.points if 0 <= int(i) < len(mesh.points) and pf.get(int(i)))
    if not verts:
        return OpResult(mesh, sel, False, "Bevel: select points that belong to polygons")
    fans = {}
    for v in verts:
        fan = _fan(mesh, v, owner, pf[v])
        if fan is None:
            return OpResult(mesh, sel, False, f"Bevel: non-manifold geometry at point {v}")
        fans[v] = fan
    solid = p["bevel_mode"] == "Solid"
    shape = _shape(p, False)
    if solid:
        shape.flat = True
    pts = _Points(mesh.points)
    chosen = set(verts)
    cut: dict[tuple[int, int], int] = {}
    for v in verts:
        pv = pts.get(v)
        for _, u, w in fans[v][0]:
            for x in (u, w):
                if (v, x) in cut:
                    continue
                direction = pts.get(x) - pv
                d = _point_distance(p, float(np.linalg.norm(direction)), x in chosen)
                cut[(v, x)] = pts.add(pv + _unit(direction) * d)
    rep: dict[tuple[int, int], list[int]] = {}
    for v in verts:
        pv = pts.get(v)
        for f, u, w in fans[v][0]:
            s, e = cut[(v, u)], cut[(v, w)]
            prof = shape.profile(pts.get(s), pts.get(e), pv)
            rep[(f, v)] = [s] + [pts.add(x) for x in prof[1:-1]] + [e]
    faces = []
    for f, poly in enumerate(mesh.polygons):
        ring: list[int] = []
        for i in poly:
            ring.extend(rep.get((f, i), [i]))
        faces.append(tuple(_dedup(ring, True)))
    directed = _directed(faces)
    patches: list[tuple[int, ...]] = []
    outline: set[int] = set()
    for v in verts:
        corners, closed = fans[v]
        for f, _, _ in corners:
            outline.update(rep[(f, v)])
        if not closed:
            continue
        sides = [rep[(f, v)] for f, _, _ in corners]
        center = pts.get(v).copy() if solid else None
        built = _orient(_fill_corner(pts, sides, p, shape.rounded(), center), directed)
        patches.extend(built)
        directed |= _directed(built)
    out, remap, _ = _finish(mesh, pts, faces + patches, chosen)
    return OpResult(out, Selection("points", points={remap[i] for i in outline if i in remap}))


def _polygon_offset(mesh: Mesh, boundary: list[tuple[int, int]], p: dict) -> float:
    value = max(0.0, float(p["offset"]))
    shortest = min(float(np.linalg.norm(mesh.points[a] - mesh.points[b])) for a, b in boundary)
    d = min(value, 100.0) / 100.0 * 0.5 * shortest if p["offset_mode"] == "Proportional" else value
    if p["limit"]:
        d = min(d, 0.5 * shortest)
    return d


def _inset_direction(pts: _Points, normal: np.ndarray, prev: int, b: int, nxt: int) -> np.ndarray:
    pb = pts.get(b)
    left_in = _unit(np.cross(normal, pb - pts.get(prev)))
    left_out = _unit(np.cross(normal, pts.get(nxt) - pb))
    bis = _unit(left_in + left_out)
    if float(np.linalg.norm(bis)) < _EPS:
        return left_in
    c = float(bis @ left_in)
    return bis / c if c > 0.05 else bis


def _polygon_shape(p: dict, height: float) -> _Shape:
    solid = p["bevel_mode"] == "Solid" and abs(height) > _EPS
    shape = _shape(p, solid)
    if abs(height) <= _EPS:
        shape.flat = True
    return shape


def _wedges(mesh: Mesh, owner: dict, gset: set[int], boundary: list[tuple[int, int]]):
    bset = set(boundary)
    out = {}
    for u, b in boundary:
        f = owner[(u, b)]
        faces: list[int] = []
        for _ in range(len(gset) + 1):
            faces.append(f)
            poly = mesh.polygons[f]
            y = poly[(poly.index(b) + 1) % len(poly)]
            if (b, y) in bset:
                out[(u, b)] = (y, faces)
                break
            g = owner.get((y, b))
            if g is None or g not in gset or g in faces:
                return None
            f = g
        else:
            return None
    return out


def _bevel_group(mesh: Mesh, group: list[int], ctx: dict, offset_scale: float) -> bool:
    pts, shape, height, p = ctx["pts"], ctx["shape"], ctx["height"], ctx["p"]
    gset = set(group)
    dirs = point_normals_for_faces(mesh, group)
    boundary = region_boundary(mesh, group)
    if any(mesh.polygons[f].count(i) != 1 for f in group for i in mesh.polygons[f]):
        return False
    wedges = _wedges(mesh, ctx["owner"], gset, boundary)
    if wedges is None:
        return False
    corner_of = {}
    prof: dict[tuple[int, int], list[int]] = {}
    outgoing: dict[tuple[int, int], tuple[int, int]] = {}
    offset = _polygon_offset(mesh, boundary, p) * offset_scale if boundary else 0.0
    for (u, b), (w, faces) in wedges.items():
        pb = pts.get(b)
        normal = _unit(np.sum([ctx["normals"][f] for f in faces], axis=0))
        lift = point_normals_for_faces(mesh, faces)[b]
        inset = _inset_direction(pts, normal, u, b, w)
        k = pb + lift * height
        chain = shape.profile(pb, k + inset * offset, k)
        prof[(u, b)] = [b] + [pts.add(x) for x in chain[1:]]
        outgoing[(b, w)] = (u, b)
        for f in faces:
            corner_of[(f, b)] = prof[(u, b)][-1]
    touched = {b for _, b in wedges}
    for i, d in dirs.items():
        if i not in touched:
            pts.set(i, pts.get(i) + d * height)
    for f in group:
        ctx["polys"][f] = tuple(corner_of.get((f, i), i) for i in mesh.polygons[f])
    for u, w in boundary:
        pu, pw = prof[outgoing[(u, w)]], prof[(u, w)]
        if p["rounding_ngons"] and len(pu) > 2:
            ctx["walls"].append(tuple(pu[:1]) + tuple(pw) + tuple(reversed(pu[1:])))
        else:
            ctx["walls"].extend((pu[j], pw[j], pw[j + 1], pu[j + 1]) for j in range(len(pu) - 1))
    return True


def _bevel_polygons(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    faces = sorted(int(f) for f in sel.polygons if 0 <= int(f) < len(mesh.polygons))
    if not faces:
        return OpResult(mesh, sel, False, "Bevel: no polygons selected")
    height = float(p["extrusion"])
    ctx = {"pts": _Points(mesh.points), "shape": _polygon_shape(p, height), "height": height, "p": p,
           "normals": face_normals(mesh), "owner": _owners(mesh), "polys": list(mesh.polygons), "walls": []}
    groups = face_groups(mesh, faces) if p["preserve_groups"] else [[f] for f in faces]
    scales = _variations(p, len(groups))
    for group, scale in zip(groups, scales):
        if not _bevel_group(mesh, group, ctx, scale):
            return OpResult(mesh, sel, False, "Bevel: non-manifold geometry in the selected polygons")
    out, _, poly_map = _finish(mesh, ctx["pts"], ctx["polys"] + ctx["walls"], set())
    chosen = {poly_map[f] for f in faces if f in poly_map}
    return OpResult(out, Selection("polygons", polygons=chosen))


def bevel(mesh: Mesh, sel: Selection, p: dict) -> OpResult:
    mesh = clone(mesh)
    if sel.mode == "edges":
        return _bevel_edges(mesh, sel, p)
    if sel.mode == "polygons":
        return _bevel_polygons(mesh, sel, p)
    if sel.mode == "points":
        return _bevel_points(mesh, sel, p)
    return OpResult(mesh, sel, False, "Bevel needs points, edges or polygons mode")


register(ToolSpec(
    id="bevel",
    name="Bevel",
    apply=bevel,
    modes=("points", "edges", "polygons"),
    params=(
        Param("bevel_mode", "Bevel Mode", "choice", "Chamfer", choices=("Chamfer", "Solid"),
              group="Tool Options"),
        Param("offset_mode", "Offset Mode", "choice", "Fixed Distance",
              choices=("Fixed Distance", "Radial", "Proportional"), group="Tool Options"),
        Param("offset", "Offset", "distance", 5.0, 0.0, 1e6, 1.0, "cm", group="Tool Options"),
        Param("subdivision", "Subdivision", "int", 0, 0, 100, 1, group="Tool Options"),
        Param("depth", "Depth", "percent", 100.0, -100.0, 100.0, 1.0, "%", group="Tool Options"),
        Param("limit", "Limit", "bool", False, group="Tool Options"),
        Param("max_angle", "Maximum Angle", "angle", 180.0, 0.0, 180.0, 1.0, "°", group="Tool Options",
              modes=("edges",)),
        Param("extrusion", "Extrusion", "distance", 0.0, -1e6, 1e6, 1.0, "cm", group="Tool Options",
              modes=("polygons",)),
        Param("preserve_groups", "Preserve Groups", "bool", True, group="Tool Options", modes=("polygons",)),
        Param("shape", "Shape", "choice", "Round", choices=("Round", "User", "Profile"), group="Shaping"),
        Param("tension", "Tension", "percent", 100.0, -100.0, 100.0, 1.0, "%", group="Shaping"),
        Param("mitering", "Mitering", "choice", "Default", choices=("Default", "Uniform", "Patch", "Radial"),
              group="Topology", modes=("points", "edges")),
        Param("ending", "Ending", "choice", "Default", choices=("Default", "Extend", "Inset"),
              group="Topology", modes=("edges",)),
        Param("partial_rounding", "Partial Rounding", "choice", "None", choices=("None", "Full", "Convex"),
              group="Topology", modes=("edges",)),
        Param("corner_ngons", "Corner N-gons", "bool", False, group="Topology", modes=("points", "edges")),
        Param("rounding_ngons", "Rounding N-gons", "bool", False, group="Topology",
              modes=("edges", "polygons")),
    ),
    interactive=True,
    drag_param="offset",
    drag_kind="distance",
    section="CREATION TOOLS",
    shortcut="M~S",
    description="Bevels the selected points, edges or polygons with chamfer or rounded profiles. Drag in the view to set the offset.",
    extra={
        "offset_units": {"Proportional": "%"},
        "segments": "Chamfer uses Subdivision + 1 segments; Solid uses 2 * (Subdivision + 1) and keeps the original edge.",
        "selection": {"points": "new cut points", "edges": "outline edges of the bevel", "polygons": "the bevelled polygons"},
    },
))

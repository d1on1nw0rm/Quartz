from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np

from ..scene import Mesh, _cross2, _ear_clip, _euler_xyz, _plane_2d, rotation_matrix

SMALL_RING = 64

__all__ = [
    "Node",
    "Document",
    "baked_mesh",
    "triangulate",
    "face_normals",
    "weld",
    "decompose",
    "compose",
    "triangulate_ring",
    "write_atomic",
    "require_finite",
    "to_z_up",
    "from_z_up",
]


@dataclass
class Node:
    name: str
    mesh: Mesh | None = None
    matrix: np.ndarray = field(default_factory=lambda: np.eye(4))
    parent: int | None = None
    kind: str = "polygon"
    params: dict | None = None
    enabled: bool = True
    position: tuple[float, float, float] | None = None
    rotation: tuple[float, float, float] | None = None
    scale: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        self.matrix = np.array(self.matrix, dtype=float).reshape(4, 4)


@dataclass
class Document:
    nodes: list[Node] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def baked_mesh(node: Node) -> Mesh:
    mesh = node.mesh
    if mesh is None:
        return Mesh.empty()
    m = np.asarray(node.matrix, float)
    points = mesh.points @ m[:3, :3].T + m[:3, 3]
    polygons = mesh.polygons
    if float(np.linalg.det(m[:3, :3])) < 0.0:
        polygons = [tuple(reversed(p)) for p in polygons]
    return Mesh(points, polygons, list(mesh.loose_edges))


def _is_convex(flat: np.ndarray) -> bool:
    e1 = np.roll(flat, -1, axis=0) - flat
    e2 = np.roll(e1, -1, axis=0)
    cross = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    if not bool((cross > 1e-12).all()):
        return False
    dot = e1[:, 0] * e2[:, 0] + e1[:, 1] * e2[:, 1]
    turn = float(np.arctan2(cross, dot).sum())
    return abs(turn - 2.0 * math.pi) < 1e-6


def _clip_ears(flat: np.ndarray) -> list[tuple[int, int, int]]:
    active = np.arange(len(flat))
    tris: list[tuple[int, int, int]] = []
    cursor = 0
    misses = 0
    while len(active) > 3:
        count = len(active)
        cursor %= count
        i0, i1, i2 = int(active[cursor - 1]), int(active[cursor]), int(active[(cursor + 1) % count])
        a, b, c = flat[i0], flat[i1], flat[i2]
        ear = _cross2(a, b, c) > 1e-12
        if ear:
            rest = np.delete(active, [(cursor - 1) % count, cursor, (cursor + 1) % count])
            p = flat[rest]
            d1 = (b[0] - a[0]) * (p[:, 1] - a[1]) - (b[1] - a[1]) * (p[:, 0] - a[0])
            d2 = (c[0] - b[0]) * (p[:, 1] - b[1]) - (c[1] - b[1]) * (p[:, 0] - b[0])
            d3 = (a[0] - c[0]) * (p[:, 1] - c[1]) - (a[1] - c[1]) * (p[:, 0] - c[0])
            ear = not bool(((d1 >= 0) & (d2 >= 0) & (d3 >= 0)).any())
        if ear:
            tris.append((i0, i1, i2))
            active = np.delete(active, cursor)
            misses = 0
            cursor -= 1
        else:
            cursor += 1
            misses += 1
            if misses > count:
                ids = [int(v) for v in active]
                tris.extend((ids[0], ids[m], ids[m + 1]) for m in range(1, len(ids) - 1))
                return tris
    if len(active) == 3:
        tris.append((int(active[0]), int(active[1]), int(active[2])))
    return tris


def triangulate_ring(ring: np.ndarray) -> list[tuple[int, int, int]]:
    ring = np.asarray(ring, float).reshape(-1, 3)
    n = len(ring)
    if n < 3:
        return []
    if n == 3:
        return [(0, 1, 2)]
    if n <= SMALL_RING:
        return _ear_clip(ring)
    flat = _plane_2d(ring)
    if _is_convex(flat):
        return [(0, k, k + 1) for k in range(1, n - 1)]
    return _clip_ears(flat)


def triangulate(mesh: Mesh) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(mesh.points, float).reshape(-1, 3).copy()
    tris: list[tuple[int, int, int]] = []
    for poly in mesh.polygons:
        n = len(poly)
        if n < 3:
            continue
        if n == 3:
            tris.append((poly[0], poly[1], poly[2]))
            continue
        for a, b, c in triangulate_ring(points[list(poly)]):
            tris.append((poly[a], poly[b], poly[c]))
    return points, np.array(tris, dtype=np.int64).reshape(-1, 3)


def face_normals(mesh: Mesh, points: np.ndarray | None = None) -> np.ndarray:
    return mesh.polygon_normals(points)


def weld(points: Iterable, tolerance: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    pts = np.asarray(points, float).reshape(-1, 3)
    n = len(pts)
    if n == 0:
        return pts.copy(), np.zeros(0, dtype=np.int64)
    tol = max(float(tolerance), 0.0)
    index = np.zeros(n, dtype=np.int64)
    if tol == 0.0:
        _, first, inverse = np.unique(pts, axis=0, return_index=True, return_inverse=True)
        order = np.argsort(first)
        rank = np.empty(len(first), dtype=np.int64)
        rank[order] = np.arange(len(first))
        return pts[np.sort(first)], rank[np.asarray(inverse).reshape(-1)]
    cells = np.floor(pts / tol).astype(np.int64)
    grid: dict[tuple[int, int, int], list[int]] = {}
    keep: list[int] = []
    offsets = [(i, j, k) for i in (-1, 0, 1) for j in (-1, 0, 1) for k in (-1, 0, 1)]
    for i in range(n):
        cx, cy, cz = int(cells[i, 0]), int(cells[i, 1]), int(cells[i, 2])
        found = -1
        for dx, dy, dz in offsets:
            for u in grid.get((cx + dx, cy + dy, cz + dz), ()):
                if np.linalg.norm(pts[keep[u]] - pts[i]) <= tol:
                    found = u
                    break
            if found >= 0:
                break
        if found < 0:
            found = len(keep)
            keep.append(i)
            grid.setdefault((cx, cy, cz), []).append(found)
        index[i] = found
    return pts[keep], index


def decompose(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = np.asarray(matrix, float).reshape(4, 4)
    lin = m[:3, :3]
    scale = np.linalg.norm(lin, axis=0)
    if np.linalg.det(lin) < 0.0:
        scale[0] = -scale[0]
    safe = np.where(np.abs(scale) > 1e-12, scale, 1.0)
    rotation = _euler_xyz(lin / safe)
    rotation[np.abs(rotation) < 1e-9] = 0.0
    position = m[:3, 3].copy()
    position[np.abs(position) < 1e-9] = 0.0
    return position, rotation, scale.astype(float)


def compose(position: Iterable[float], rotation: Iterable[float], scale: Iterable[float]) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rotation_matrix(rotation) @ np.diag(np.asarray(list(scale), float))
    m[:3, 3] = np.asarray(list(position), float)
    return m


def write_atomic(path: str, data: bytes) -> None:
    target = os.path.abspath(path)
    fd, temp = tempfile.mkstemp(prefix=".quartz-", suffix=".tmp", dir=os.path.dirname(target))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def require_finite(path: str, node: Node, points: np.ndarray) -> None:
    from .registry import FileFormatError

    if len(points) and not bool(np.isfinite(points).all()):
        label = os.path.basename(path)
        raise FileFormatError(f"{label}: {node.name or 'Node'} has coordinates that are not finite numbers")


def to_z_up(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, float).reshape(-1, 3)
    return np.column_stack([pts[:, 0], -pts[:, 2], pts[:, 1]])


def from_z_up(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, float).reshape(-1, 3)
    return np.column_stack([pts[:, 0], pts[:, 2], -pts[:, 1]])
